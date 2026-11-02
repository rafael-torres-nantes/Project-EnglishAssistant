import logging
from typing import Iterator

from config.settings import Settings
from prompt_template.coach_prompts import CoachPrompts
from services.presentation_script_service import PresentationScriptService
from services.speech_analysis_service import SpeechAnalysisService
from utils.audio_helpers import AudioHelpers
from utils.latency_tracker import LatencyTracker
from utils.text_helpers import TextHelpers

logger = logging.getLogger(__name__)


class CoachController:
    """Orquestra o treinador de comunicação: grava o microfone e só depois da fala dá o retorno.

    Não lê `input_data/` nem usa o áudio do sistema: o único insumo é o que a própria pessoa
    disse, digitou ou carregou como roteiro.
    """

    _FILLER_HINT = "Umm, so, like, I mean, you know... Hum, tipo, né, então, assim..."

    def __init__(self, transcription, ai, microphone, analysis=None, script_parser=None, latency_log=Settings.COACH_LATENCY_LOG):
        """
        Função de inicialização do controller do treinador.

        Args:
            transcription: Serviço com `transcribe_segments`.
            ai: Serviço com `stream` e `prewarm`.
            microphone: Serviço com `start`, `stop`, `level` e `is_recording`.
            analysis: Serviço de métricas da fala; None usa o padrão.
            script_parser: Serviço de divisão do roteiro; None usa o padrão.
            latency_log: Arquivo JSONL que recebe as medições.

        Returns:
            None
        """
        self.transcription = transcription
        self.ai = ai
        self.microphone = microphone
        self.analysis = analysis or SpeechAnalysisService()
        self.script_parser = script_parser or PresentationScriptService()
        self.latency_log = latency_log
        self.parts = []
        self.session = None

    def prewarm(self, mode: str) -> None:
        """
        Prepara a CLI para o modo escolhido, antes de o pedido chegar.

        Args:
            mode: Modo do treinador.

        Returns:
            None
        """
        try:
            self.ai.prewarm(CoachPrompts.system_prompt(mode))
        except OSError as error:
            logger.error("Falha ao aquecer a CLI: %s", error)

    def load_script(self, script: str) -> list[dict]:
        """
        Carrega o roteiro da apresentação, que fica só na memória.

        Args:
            script: Texto do roteiro.

        Returns:
            Partes do roteiro.

        Raises:
            ValueError: Se o roteiro estiver vazio.
        """
        self.parts = self.script_parser.parse(script)
        return self.parts

    def start_recording(self, mode: str, language: str | None = None, part_index: int | None = None, target_language: str = "same") -> str:
        """
        Valida o pedido antes de abrir o microfone, para nunca perder uma fala já gravada.

        Args:
            mode: Modo do treinador.
            language: "pt" ou "en"; None detecta o idioma automaticamente.
            part_index: Parte do roteiro, no modo apresentação.
            target_language: Idioma das frases, no modo gestor.

        Returns:
            Nome do microfone em uso.

        Raises:
            ValueError: Se o modo, o idioma ou a parte forem inválidos.
            RuntimeError: Se o microfone não puder ser aberto.
        """
        CoachPrompts.system_prompt(mode)
        if language not in (None, "pt", "en"):
            raise ValueError(f"Idioma desconhecido: {language}")
        if mode == "manager":
            CoachPrompts.manager_request("", target_language)
        if mode == "presentation":
            self.part_for(part_index)
        device = self.microphone.start()
        self.session = {"mode": mode, "language": language, "part_index": part_index, "target_language": target_language}
        self.prewarm(mode)
        return device

    def part_for(self, part_index: int | None) -> dict:
        """
        Localiza uma parte do roteiro carregado.

        Args:
            part_index: Índice da parte.

        Returns:
            A parte do roteiro.

        Raises:
            ValueError: Se não houver roteiro ou o índice for inválido.
        """
        if not isinstance(part_index, int) or not 0 <= part_index < len(self.parts):
            raise ValueError("Carregue o roteiro e escolha uma parte válida.")
        return self.parts[part_index]

    def stop_and_review(self) -> Iterator[dict]:
        """
        Fecha o microfone e gera o retorno da fala.

        Yields:
            Eventos com a chave "event": status, transcript, analysis, ai, latency, error, done.
        """
        session = self.session
        if session is None:
            yield {"event": "error", "message": "Nenhuma gravação em andamento."}
            return
        self.session = None
        tracker = LatencyTracker(session["mode"], "mic")
        try:
            audio, sample_rate, channels = self.microphone.stop()
            tracker.mark("capture_closed")
            yield from self.review_audio(audio, sample_rate, channels, session, tracker)
        except Exception as error:
            logger.error("Erro ao gerar o retorno: %s", error)
            yield {"event": "error", "message": str(error)}

    def review_audio(self, audio: bytes, sample_rate: int, channels: int, session: dict, tracker: LatencyTracker) -> Iterator[dict]:
        """
        Transcreve, mede e pede o retorno da IA para um áudio já gravado.

        Args:
            audio: PCM 16-bit.
            sample_rate: Taxa de amostragem do áudio.
            channels: Canais do áudio.
            session: Parâmetros definidos em `start_recording`.
            tracker: Medidor de latência do pedido.

        Yields:
            Eventos de retorno.
        """
        samples = AudioHelpers.pcm_to_float32(audio, sample_rate, channels)
        tracker.add_details(audio_seconds=round(len(samples) / 16000, 1))
        tracker.mark("audio_ready")
        yield {"event": "status", "message": "Transcrevendo..."}
        words = []
        text_parts = []
        language = session["language"]
        for segment in self.transcription.transcribe_segments(samples, session["language"], self._FILLER_HINT):
            tracker.mark("first_transcript")
            language = segment["language"]
            words.extend(segment["words"])
            text_parts.append(segment["text"])
            yield {"event": "transcript", "text": segment["text"]}
        tracker.mark("transcript_done")
        transcript = TextHelpers.clean_transcription(" ".join(text_parts))
        if not transcript:
            yield {"event": "error", "message": "Nenhuma fala detectada no microfone."}
            return
        tracker.add_details(language=language)
        analysis = self.analysis.analyze(words, language)
        tracker.mark("analysis_done")
        yield {"event": "analysis", **analysis}
        request = self.build_request(session, transcript, analysis)
        yield from self.stream_ai(session["mode"], request, tracker)

    def build_request(self, session: dict, transcript: str, analysis: dict) -> str:
        """
        Monta o pedido de IA conforme o modo.

        Args:
            session: Parâmetros da gravação.
            transcript: Texto transcrito.
            analysis: Métricas da fala.

        Returns:
            Texto do pedido.
        """
        if session["mode"] == "manager":
            return CoachPrompts.manager_request(transcript, session["target_language"])
        if session["mode"] == "presentation":
            return CoachPrompts.presentation_request(self.part_for(session["part_index"]), transcript, analysis)
        return CoachPrompts.rehearsal_request(transcript, analysis)

    def phrases_from_text(self, idea: str, target_language: str = "same") -> Iterator[dict]:
        """
        Gera as frases direta e formal a partir de uma ideia digitada.

        Args:
            idea: Ideia em português ou inglês.
            target_language: Idioma das frases: "same", "pt" ou "en".

        Yields:
            Eventos de retorno.
        """
        tracker = LatencyTracker("manager", "text")
        try:
            if not idea.strip():
                raise ValueError("Escreva a ideia antes de gerar as frases.")
            request = CoachPrompts.manager_request(idea.strip(), target_language)
            yield from self.stream_ai("manager", request, tracker)
        except Exception as error:
            logger.error("Erro ao gerar as frases: %s", error)
            yield {"event": "error", "message": str(error)}

    def stream_ai(self, mode: str, request: str, tracker: LatencyTracker) -> Iterator[dict]:
        """
        Repassa a resposta da IA em streaming e registra a latência.

        Args:
            mode: Modo do treinador.
            request: Texto do pedido.
            tracker: Medidor de latência do pedido.

        Yields:
            Eventos "ai", "latency" e "done".
        """
        system_prompt = CoachPrompts.system_prompt(mode)
        tracker.mark("ai_request_sent")
        for chunk in self.ai.stream(request, system_prompt):
            tracker.mark("ai_first_word")
            yield {"event": "ai", "text": chunk}
        tracker.mark("ai_done")
        tracker.add_details(warm_cli=getattr(self.ai, "last_was_warm", False), ai_blocks=getattr(self.ai, "last_blocks", []))
        tracker.save(self.latency_log)
        self.prewarm(mode)
        yield {"event": "latency", **tracker.as_dict()}
        yield {"event": "done"}

    def recording_state(self) -> dict:
        """
        Informa o estado do microfone para a interface.

        Returns:
            Dicionário com "recording", "level" e "seconds".
        """
        return {
            "recording": self.microphone.is_recording,
            "level": round(self.microphone.level, 4),
            "seconds": round(self.microphone.elapsed_seconds(), 1),
        }

    def stop(self) -> None:
        """
        Libera o microfone e encerra os processos aquecidos.

        Returns:
            None
        """
        if self.microphone.is_recording:
            self.microphone.stop()
        self.ai.stop()
