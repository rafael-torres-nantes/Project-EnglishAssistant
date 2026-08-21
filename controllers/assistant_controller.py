import logging
import time
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.text import Text

from services.audio_capture_service import AudioCaptureService
from services.transcription_service import TranscriptionService
from services.response_service import ResponseService
from services.context_service import ContextService
from config.settings import Settings

logger = logging.getLogger(__name__)

class AssistantController:
    def __init__(self, provider: str = Settings.DEFAULT_AI_PROVIDER, whisper_model: str = Settings.WHISPER_MODEL_SIZE):
        self.provider = provider
        self.whisper_model = whisper_model
        self.console = Console()
        self.audio_service = AudioCaptureService()
        self.transcription_service = TranscriptionService(model_size=whisper_model)
        self.response_service = ResponseService(provider=provider)
        self.context_service = ContextService()
        self.is_running = False

    def start(self) -> None:
        self.is_running = True

        context_files = self.context_service.list_files()

        self.console.print(f"[bold green]Provider:[/] {self.provider}")
        self.console.print(f"[bold green]Whisper Model:[/] {self.whisper_model}")
        self.console.print(f"[bold green]Context Files Loaded:[/] {len(context_files)}")
        if context_files:
            for f in context_files:
                self.console.print(f"  [dim]• {f}[/]")

        try:
            self._process_loop()
        except KeyboardInterrupt:
            self.console.print("\n[bold yellow]Stopping assistant gracefully...[/]")
        finally:
            self.stop()

    def stop(self) -> None:
        self.is_running = False
        self.audio_service.stop()
        self.transcription_service.stop()
        self.response_service.stop()

    def _process_loop(self) -> None:
        self.audio_service.start()
        accumulated_audio = []
        is_speaking = False
        # Limitamos o tempo de silencio para fechar o bloco mais rápido
        max_silence_frames = max(1, int(Settings.SILENCE_TIMEOUT_SECONDS / Settings.AUDIO_CHUNK_DURATION_SECONDS))
        
        silence_frames = 0

        # UI dinâmica
        status_text = Text("🎧 Listening to system audio...", style="dim italic")
        status_panel = Panel(status_text, border_style="blue", title="Status")

        with Live(status_panel, console=self.console, refresh_per_second=4, transient=False) as live:
            while self.is_running:
                payload = self.audio_service.get_audio_chunk()
                if payload is None:
                    time.sleep(0.1)
                    continue

                chunk, sample_rate, channels = payload
                speech_detected = self.transcription_service.is_speech(chunk, sample_rate, channels)

                if speech_detected:
                    if not is_speaking:
                        # Mudou de silencio para fala
                        live.update(Panel(Text("🔊 Speech detected! Recording...", style="bold green"), border_style="green", title="Status"))
                    is_speaking = True
                    silence_frames = 0
                    accumulated_audio.append(payload)

                elif is_speaking:
                    silence_frames += 1
                    accumulated_audio.append(payload)

                    if silence_frames > max_silence_frames:
                        # Momento de processar
                        live.update(Panel(Text("⏳ Processing transcription...", style="bold yellow"), border_style="yellow", title="Status"))
                        
                        transcription = self.transcription_service.transcribe(accumulated_audio)
                        
                        if transcription and transcription.strip():
                            # Imprime a transcrição congelada acima
                            self.console.print(Panel(transcription, title="🎙️ Transcription", border_style="cyan"))
                            
                            live.update(Panel(Text("🧠 Generating AI suggestions...", style="bold magenta"), border_style="magenta", title="Status"))
                            
                            context = self.context_service.load_all_context()
                            response = self.response_service.generate_response(transcription, context)
                            
                            # Imprime as sugestões congeladas acima
                            self.console.print(Panel(response, title="🤖 AI Suggestions", border_style="green"))

                        # Reseta os contadores e limpa
                        accumulated_audio = []
                        is_speaking = False
                        silence_frames = 0
                        # Volta pro painel de listening
                        live.update(Panel(Text("🎧 Listening to system audio...", style="dim italic"), border_style="blue", title="Status"))

                time.sleep(0.01)

if __name__ == "__main__":
    pass
