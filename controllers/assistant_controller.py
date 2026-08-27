import logging
import time
import sys
try:
    import msvcrt
except ImportError:
    msvcrt = None

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
        last_transcribe_time = 0

        # UI dinâmica
        status_text = Text("🎧 Listening to system audio... (Press 'p' to force reply)", style="dim italic")
        status_panel = Panel(status_text, border_style="blue", title="Status")

        with Live(status_panel, console=self.console, refresh_per_second=4, transient=False) as live:
            while self.is_running:
                force_process = False
                if msvcrt and msvcrt.kbhit():
                    try:
                        key = msvcrt.getch().decode('utf-8', 'ignore').lower()
                        if key == 'p':
                            force_process = True
                    except Exception:
                        pass

                payload = self.audio_service.get_audio_chunk()
                if payload is None and not force_process:
                    time.sleep(0.1)
                    continue

                if payload is not None:
                    chunk, sample_rate, channels = payload
                    speech_detected = self.transcription_service.is_speech(chunk, sample_rate, channels)

                    if speech_detected:
                        if not is_speaking:
                            # Mudou de silencio para fala
                            live.update(Panel(Text("🔊 Speech detected! Recording...", style="bold green"), border_style="green", title="Status"))
                            last_transcribe_time = time.time()
                        is_speaking = True
                        silence_frames = 0
                        accumulated_audio.append(payload)
                    elif is_speaking:
                        silence_frames += 1
                        accumulated_audio.append(payload)

                if is_speaking:
                    # Streaming transcription update every 1 second
                    if time.time() - last_transcribe_time >= 1.0:
                        try:
                            partial_text = self.transcription_service.transcribe(accumulated_audio)
                            if partial_text:
                                live.update(Panel(Text(f"🎙️ {partial_text} ...", style="bold cyan"), border_style="cyan", title="Transcribing... (Press 'p' to force)"))
                        except Exception:
                            pass
                        last_transcribe_time = time.time()

                    if silence_frames > max_silence_frames or force_process:
                        # Momento de processar final
                        if force_process:
                            self.console.print(Panel(Text("🛑 Force processing triggered by user ('p' pressed)", style="bold red"), border_style="red"))
                        
                        live.update(Panel(Text("⏳ Finalizing transcription...", style="bold yellow"), border_style="yellow", title="Status"))
                        
                        transcribe_start = time.time()
                        transcription = self.transcription_service.transcribe(accumulated_audio)
                        transcribe_elapsed = time.time() - transcribe_start

                        if transcription and transcription.strip():
                            # Imprime a transcrição congelada acima
                            self.console.print(Panel(transcription, title=f"🎙️ Transcription ({transcribe_elapsed:.2f}s)", border_style="cyan"))

                            live.update(Panel(Text("🧠 Generating AI suggestions...", style="bold magenta"), border_style="magenta", title="Status"))

                            context = self.context_service.load_all_context()
                            generate_start = time.time()

                            if Settings.STREAMING:
                                response = ""
                                try:
                                    for chunk in self.response_service.generate_response_stream(transcription, context):
                                        response += chunk
                                        live.update(Panel(response, title="🤖 AI Suggestions (streaming...)", border_style="green"))
                                except Exception as e:
                                    logger.error("Erro ao gerar resposta em streaming: %s", e)
                                    response = f"Error generating response: {str(e)}"
                            else:
                                response = self.response_service.generate_response(transcription, context)

                            generate_elapsed = time.time() - generate_start

                            # Limpa o Live panel de streaming para não duplicar na tela antes do print final
                            live.update(Panel(Text("⏳ Cleaning up...", style="dim"), border_style="white", title="Status"))
                            
                            # Imprime as sugestões congeladas acima
                            self.console.print(Panel(response, title=f"🤖 AI Suggestions ({generate_elapsed:.2f}s)", border_style="green"))

                        # Reseta os contadores e limpa
                        accumulated_audio = []
                        is_speaking = False
                        silence_frames = 0
                        
                        # Limpa o áudio que continuou sendo capturado em background
                        with self.audio_service.audio_queue.mutex:
                            self.audio_service.audio_queue.queue.clear()
                            
                        if force_process:
                            live.update(Panel(Text("⏳ Paused to avoid immediate feedback...", style="dim yellow"), border_style="yellow", title="Status"))
                            time.sleep(1.5)
                            with self.audio_service.audio_queue.mutex:
                                self.audio_service.audio_queue.queue.clear()

                        # Volta pro painel de listening
                        live.update(Panel(Text("🎧 Listening to system audio... (Press 'p' to force reply)", style="dim italic"), border_style="blue", title="Status"))

                time.sleep(0.01)

if __name__ == "__main__":
    pass
