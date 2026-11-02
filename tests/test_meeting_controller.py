import queue
import threading
import time
from unittest.mock import MagicMock

import pytest

from config.settings import Settings
from controllers.meeting_controller import MeetingController
from prompt_template.meeting_prompt import MEETING_SYSTEM_PROMPT


class FakeAudioThread:
    """Simula a thread de captura do PyAudio."""

    def __init__(self, alive: bool = True):
        self._alive = alive

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout: float = 2.0) -> None:
        pass


class FakeAudioService:
    """Simula o AudioCaptureService com fila controlada e sem hardware real."""

    def __init__(self, loopback_error: bool = False, thread_blocked: bool = False):
        self.loopback_error = loopback_error
        self.thread_blocked = thread_blocked
        self.audio_queue = queue.Queue()
        self.is_capturing = False
        self.stream = object()
        self.capture_thread = FakeAudioThread(alive=True)
        self.pyaudio_instance = MagicMock()
        self.stop_called = False

    def find_loopback_device(self) -> dict:
        if self.loopback_error:
            raise RuntimeError("Dispositivo de loopback WASAPI não encontrado.")
        return {"name": "Mock WASAPI Loopback"}

    def start(self) -> None:
        self.is_capturing = True

    def stop(self) -> None:
        self.stop_called = True
        self.is_capturing = False
        if not self.thread_blocked:
            self.capture_thread._alive = False

    def get_audio_chunk(self):
        try:
            return self.audio_queue.get(timeout=0.05)
        except queue.Empty:
            return None


class FakeTranscriptionService:
    """Simula o serviço Whisper."""

    def __init__(self):
        self.speech_response = True
        self.transcribe_response = "Mock transcription"

    def is_speech(self, chunk, sample_rate, channels) -> bool:
        return self.speech_response

    def transcribe(self, audio_list) -> str:
        return self.transcribe_response


class FakeResponseService:
    """Simula o serviço de IA com rastreamento byte a byte."""

    def __init__(self, delay: float = 0.0):
        self.system_prompt_template = MEETING_SYSTEM_PROMPT
        self.delay = delay
        self.received_prompts = []
        self.last_system_prompt = None
        self.last_prompt = None

    def preview_prompts(self, text: str, context: str) -> tuple[str, str]:
        sys_p = self.system_prompt_template.format(meeting_context=context)
        usr_p = f"[Meeting Audio Transcription]\n{text}\n\nBased on this meeting conversation..."
        return sys_p, usr_p

    def generate_response_stream(self, text: str, context: str):
        sys_p, usr_p = self.preview_prompts(text, context)
        self.last_system_prompt = sys_p
        self.last_prompt = usr_p
        self.received_prompts.append((sys_p, usr_p))
        if self.delay > 0:
            time.sleep(self.delay)
        yield "Suggestion "
        if self.delay > 0:
            time.sleep(self.delay)
        yield "chunk."


class FakeContextService:
    """Simula o serviço de contexto com caminhos contendo pastas."""

    def list_files(self) -> list[str]:
        return ["C:\\Users\\Rafael\\context\\profile.md", "notes.txt"]

    def load_file(self, filename: str) -> str:
        return "# Context Content"

    def load_all_context(self) -> str:
        return "Loaded full context"


def make_controller(
    loopback_error: bool = False,
    thread_blocked: bool = False,
    ai_delay: float = 0.0,
    provider: str = "claude",
):
    audio_inst = FakeAudioService(loopback_error=loopback_error, thread_blocked=thread_blocked)
    audio_factory = lambda: audio_inst
    transcription = FakeTranscriptionService()
    response_svc = FakeResponseService(delay=ai_delay)
    context_svc = FakeContextService()
    controller = MeetingController(
        transcription=transcription,
        response_service=response_svc,
        context_service=context_svc,
        audio_factory=audio_factory,
        whisper_model_name="small",
        provider=provider,
    )
    return controller, audio_inst, transcription, response_svc, context_svc


class TestMeetingController:
    """Valida a lógica interna, concorrência e resiliência do MeetingController."""

    def test_start_raises_when_no_loopback_device(self):
        controller, _, _, _, _ = make_controller(loopback_error=True)
        with pytest.raises(RuntimeError, match="não encontrado"):
            controller.start()
        assert not controller.is_running
        assert not controller.is_capturing

    def test_start_already_running_raises_runtime_error(self):
        controller, _, _, _, _ = make_controller()
        device = controller.start()
        assert device == "Mock WASAPI Loopback"
        assert controller.is_running
        with pytest.raises(RuntimeError, match="already running"):
            controller.start()
        controller.stop()

    def test_speech_then_silence_generates_single_final_and_suggestion(self):
        controller, audio, transcription, response_svc, _ = make_controller()
        controller.start()

        # Insere chunks simulando fala
        dummy_pcm = b"\x00\x00" * 8000
        audio.audio_queue.put((dummy_pcm, 16000, 1))
        audio.audio_queue.put((dummy_pcm, 16000, 1))

        # Aguarda a detecção da fala
        time.sleep(0.15)
        # Transição para silêncio
        transcription.speech_response = False
        max_silence = int(Settings.SILENCE_TIMEOUT_SECONDS / Settings.AUDIO_CHUNK_DURATION_SECONDS) + 2
        for _ in range(max_silence):
            audio.audio_queue.put((dummy_pcm, 16000, 1))

        # Aguarda processamento do bloco final e sugestão
        time.sleep(0.4)

        state = controller.state()
        assert state["running"] is True
        assert len(controller._finals) == 1
        assert controller._finals[0]["text"] == "Mock transcription"
        assert controller._current_suggestion is not None
        assert controller._current_suggestion["done"] is True
        assert "Suggestion chunk." in controller._current_suggestion["text"]

        controller.stop()

    def test_utterance_hits_45s_cap_and_splits(self):
        controller, audio, transcription, _, _ = make_controller()
        controller.start()

        dummy_pcm = b"\x00\x00" * 8000
        # Simula 91 chunks de 0.5s = 45.5s de fala contínua sem silêncio
        for _ in range(91):
            audio.audio_queue.put((dummy_pcm, 16000, 1))

        for _ in range(30):
            if len(controller._finals) >= 1:
                break
            time.sleep(0.1)

        # O teto de 45s deve ter disparado pelo menos 1 final
        assert len(controller._finals) >= 1
        controller.stop()

    def test_none_chunk_counts_as_one_second_silence(self):
        controller, audio, transcription, _, _ = make_controller()
        controller.start()

        dummy_pcm = b"\x00\x00" * 8000
        # Fala inicial
        audio.audio_queue.put((dummy_pcm, 16000, 1))
        time.sleep(0.1)

        # Quando a fila esvazia, get_audio_chunk() retorna None após timeout de 0.05s
        # Deixamos passar tempo suficiente para computar o silêncio e fechar o bloco
        time.sleep(0.3)
        assert len(controller._finals) == 1
        controller.stop()

    def test_pending_generation_replaces_older(self):
        controller, _, _, response_svc, _ = make_controller(ai_delay=0.25)
        controller.is_running = True

        # Inicia a 1ª geração
        controller.queue_generation(1, "First utterance")
        time.sleep(0.05)

        # Enquanto a 1ª roda, enfileira a 2ª e logo em seguida a 3ª
        controller.queue_generation(2, "Second utterance")
        controller.queue_generation(3, "Third utterance (newest)")

        # Aguarda término de todas as gerações
        time.sleep(0.7)

        # Apenas a 1ª e a 3ª devem ter sido processadas; a 2ª foi substituída
        texts_processed = [usr for _, usr in response_svc.received_prompts]
        assert any("First utterance" in t for t in texts_processed)
        assert any("Third utterance" in t for t in texts_processed)
        assert not any("Second utterance" in t for t in texts_processed)

        controller.stop()

    def test_generate_now_all_scenarios(self):
        controller, _, transcription, _, _ = make_controller()

        # Cenário 3a: Chamada sem sessão ativa -> RuntimeError
        with pytest.raises(RuntimeError, match="não está em execução"):
            controller.generate_now()

        controller.start()

        # Cenário 3b: Sessão ativa mas sem nenhum final nem fala -> RuntimeError
        with pytest.raises(RuntimeError, match="Nenhuma transcrição final"):
            controller.generate_now()

        # Cenário 1: Durante fala em andamento -> corta imediatamente e gera
        dummy_pcm = b"\x00\x00" * 8000
        controller._is_speaking = True
        controller._accumulated_audio = [(dummy_pcm, 16000, 1)]

        controller.generate_now()
        time.sleep(0.2)
        assert len(controller._finals) == 1
        assert controller._is_speaking is False

        # Cenário 2: Ocioso com final anterior existente -> re-gera sobre o último final
        controller.generate_now()
        time.sleep(0.2)
        assert controller._suggestion_counter >= 2

        controller.stop()

    def test_capturing_false_when_capture_thread_dies(self):
        controller, audio, _, _, _ = make_controller()
        controller.start()
        assert controller.is_capturing is True

        # Simula a morte abrupta da thread WASAPI
        audio.capture_thread._alive = False
        assert controller.is_capturing is False

        # O laço de processamento detecta a morte e encerra a sessão
        time.sleep(0.15)
        assert controller.is_running is False

    def test_stop_idempotent_and_fast(self):
        controller, audio, _, _, _ = make_controller(thread_blocked=True)
        controller.start()

        start_time = time.time()
        # Thread bloqueada: stop deve respeitar o limite de 3 segundos
        controller.stop()
        elapsed = time.time() - start_time

        assert elapsed < 3.0
        assert not controller.is_running
        # Com a thread viva, terminate não deve ser chamado
        assert audio.pyaudio_instance.terminate.call_count == 0

        # Idempotência: segunda chamada imediata
        controller.stop()
        assert not controller.is_running

    def test_orphan_session_auto_stops_after_timeout(self, monkeypatch):
        controller, _, _, _, _ = make_controller()
        # Reduz o timeout de órfão para o teste unitário ser rápido
        monkeypatch.setattr(Settings, "MEETING_ORPHAN_SECONDS", 0.3)
        controller.start()

        # Sem nenhum assinante conectado, deve encerrar sozinho
        time.sleep(0.9)
        assert not controller.is_running

    def test_slow_subscriber_drops_levels_not_finals(self):
        controller, _, _, _, _ = make_controller()
        controller.start()

        events_gen = controller.events()
        snapshot = next(events_gen)
        assert snapshot["type"] == "snapshot"

        # Simula assinante lento inundando a fila com níveis sonoros
        for i in range(50):
            controller.broadcast({"type": "level", "rms": float(i)})

        # Emite eventos críticos
        controller.broadcast({"type": "final", "id": 10, "text": "Critical final", "transcribe_seconds": 0.5})
        controller.broadcast({"type": "suggestion_start", "id": 1, "final_id": 10})
        controller.broadcast({"type": "suggestion_chunk", "id": 1, "text": "Hello"})
        controller.broadcast({"type": "suggestion_done", "id": 1, "first_token_seconds": 0.1, "total_seconds": 0.2})

        received_types = []
        # Drena a fila do assinante
        while True:
            try:
                evt = controller._subscribers[0].get_nowait()
                received_types.append(evt["type"])
            except queue.Empty:
                break

        assert "final" in received_types
        assert "suggestion_start" in received_types
        assert "suggestion_chunk" in received_types
        assert "suggestion_done" in received_types

        events_gen.close()
        controller.stop()

    def test_preview_prompts_match_ai_service_payload(self):
        controller, _, _, response_svc, context_svc = make_controller()
        controller.start()

        controller.queue_generation(1, "Unique meeting utterance 12345")
        time.sleep(0.2)

        backstage = controller.backstage()
        assert backstage["last_request"] is not None
        assert response_svc.last_system_prompt is not None

        # Byte a byte idêntico
        assert backstage["last_request"]["system_prompt"] == response_svc.last_system_prompt
        assert backstage["last_request"]["prompt"] == response_svc.last_prompt

        controller.stop()

    def test_backstage_provider_and_model_reflection(self):
        controller_claude, _, _, _, _ = make_controller(provider="claude")
        bs_claude = controller_claude.backstage()
        assert bs_claude["provider"] == "claude"
        assert bs_claude["model"] == Settings.DEFAULT_CLAUDE_MODEL

        controller_gemini, _, _, _, _ = make_controller(provider="gemini")
        bs_gemini = controller_gemini.backstage()
        assert bs_gemini["provider"] == "gemini"
        assert bs_gemini["model"] == Settings.DEFAULT_GEMINI_MODEL

    def test_backstage_context_files_sanitized(self):
        controller, _, _, _, _ = make_controller()
        bs = controller.backstage()
        files = bs["context_files"]
        assert len(files) == 2
        for f in files:
            # Nunca deve expor caminhos com barras absolutas
            assert "/" not in f["name"]
            assert "\\" not in f["name"]
            assert "bytes" in f
            assert "content" in f

    def test_events_initial_snapshot(self):
        controller, _, _, _, _ = make_controller()
        controller.start()
        gen = controller.events()
        snapshot = next(gen)
        assert snapshot["type"] == "snapshot"
        assert snapshot["running"] is True
        assert snapshot["capturing"] is True
        assert "finals" in snapshot
        assert "suggestion" in snapshot
        gen.close()
        controller.stop()

    def test_partial_transcription_emitted_during_speech(self):
        controller, audio, transcription, _, _ = make_controller()
        controller.start()
        transcription.transcribe_response = "partial text"
        gen = controller.events()
        _ = next(gen)  # snapshot

        dummy_pcm = b"\x00\x00" * 8000
        # Envia chunks contínuos de fala por 1.4s sem deixar a fila secar
        for _ in range(14):
            audio.audio_queue.put((dummy_pcm, 16000, 1))
            time.sleep(0.1)

        received = []
        while True:
            try:
                evt = controller._subscribers[0].get_nowait()
                received.append(evt.get("type"))
            except queue.Empty:
                break

        assert "partial" in received
        gen.close()
        controller.stop()

    def test_level_event_rate_limit(self):
        controller, audio, _, _, _ = make_controller()
        controller.start()
        gen = controller.events()
        _ = next(gen)

        dummy_pcm = b"\x00\x00" * 8000
        for _ in range(20):
            audio.audio_queue.put((dummy_pcm, 16000, 1))
            time.sleep(0.01)

        time.sleep(0.3)
        level_events = []
        while True:
            try:
                evt = controller._subscribers[0].get_nowait()
                if evt.get("type") == "level":
                    level_events.append(evt)
            except queue.Empty:
                break

        # Em 0.3s, no máximo 2-3 eventos level (máximo 5 por segundo)
        assert len(level_events) <= 4
        gen.close()
        controller.stop()

    def test_sse_heartbeat_ping(self, monkeypatch):
        controller, _, _, _, _ = make_controller()
        monkeypatch.setattr(Settings, "MEETING_HEARTBEAT_SECONDS", 0.1)
        controller.start()
        gen = controller.events()
        _ = next(gen)

        time.sleep(0.25)
        pings = []
        while True:
            try:
                evt = controller._subscribers[0].get_nowait()
                if evt.get("type") == "ping":
                    pings.append(evt)
            except queue.Empty:
                break

        assert len(pings) >= 1
        gen.close()
        controller.stop()

    def test_stop_when_already_stopped_is_noop(self):
        controller, _, _, _, _ = make_controller()
        assert not controller.is_running
        controller.stop()
        assert not controller.is_running
