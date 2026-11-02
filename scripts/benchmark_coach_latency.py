"""Mede cada etapa do treinador a partir de um WAV, com Whisper e CLI reais e sem microfone."""
import argparse
import statistics
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import Settings

Settings.setup_cuda_dll_path()

from controllers.coach_controller import CoachController
from prompt_template.coach_prompts import CoachPrompts
from services.transcription_service import TranscriptionService
from services.warm_claude_service import WarmClaudeService
from utils.latency_tracker import LatencyTracker


class CoachLatencyBenchmark:
    """Roda o mesmo caminho de código do botão de gravar, trocando só a origem do áudio."""

    _WARM_WAIT_SECONDS = 6
    _SCRIPT = "# Fila\nA fila de pedidos cresce nos horários de pico porque o processamento é síncrono."

    def __init__(self, wav_path: str, mode: str, language: str | None, cold: bool) -> None:
        """
        Função de inicialização do benchmark.

        Args:
            wav_path: WAV PCM de 16 bits com a fala.
            mode: Modo do treinador.
            language: "pt", "en" ou None para detectar.
            cold: True inicia a CLI só quando o pedido chega.

        Returns:
            None
        """
        self.mode = mode
        self.language = language
        self.cold = cold
        with wave.open(wav_path, "rb") as handle:
            self.audio = handle.readframes(handle.getnframes())
            self.sample_rate = handle.getframerate()
            self.channels = handle.getnchannels()
        transcription = TranscriptionService(model_size=Settings.COACH_WHISPER_MODEL)
        transcription.warm_up()
        self.coach = CoachController(transcription, WarmClaudeService(), None, latency_log=Settings.COACH_LATENCY_LOG)
        self.coach.load_script(self._SCRIPT)

    def run_once(self) -> tuple[dict, str, str]:
        """
        Executa uma medição completa.

        Returns:
            Tupla (medição, transcrição, resposta da IA).
        """
        session = {"mode": self.mode, "language": self.language, "part_index": 0, "target_language": "same"}
        self.coach.ai.stop()
        if not self.cold:
            self.coach.prewarm(self.mode)
            time.sleep(self._WARM_WAIT_SECONDS)
        tracker = LatencyTracker(self.mode, "benchmark")
        latency, transcript, answer = {}, [], []
        for event in self.coach.review_audio(self.audio, self.sample_rate, self.channels, session, tracker):
            if event["event"] == "transcript":
                transcript.append(event["text"])
            if event["event"] == "ai":
                answer.append(event["text"])
            if event["event"] == "latency":
                latency = event
            if event["event"] == "error":
                raise RuntimeError(event["message"])
        return latency, "".join(transcript), "".join(answer)

    def run(self, runs: int) -> None:
        """
        Repete a medição e imprime a mediana de cada etapa.

        Args:
            runs: Número de repetições.

        Returns:
            None
        """
        results = []
        for number in range(runs):
            latency, transcript, answer = self.run_once()
            results.append(latency)
            print(f"execução {number + 1}: 1ª palavra em {latency['stages']['ai_first_word']:.2f} s, CLI aquecida={latency['warm_cli']}, blocos={latency['ai_blocks']}")
        print(f"modelo={Settings.COACH_MODEL} effort={Settings.COACH_EFFORT or 'padrão'} whisper={Settings.COACH_WHISPER_MODEL} áudio={results[0]['audio_seconds']} s")
        for stage in results[0]["stages"]:
            values = [result["stages"][stage] for result in results]
            print(f"  {stage:<18} {statistics.median(values):6.2f} s (min {min(values):.2f}, max {max(values):.2f})")
        print(f"\nTRANSCRIÇÃO: {transcript}\n\nRESPOSTA:\n{answer}")
        self.coach.ai.stop()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav")
    parser.add_argument("--mode", default="rehearsal", choices=CoachPrompts.modes())
    parser.add_argument("--language", default=None, choices=["pt", "en"])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--cold", action="store_true")
    args = parser.parse_args()
    CoachLatencyBenchmark(args.wav, args.mode, args.language, args.cold).run(args.runs)
