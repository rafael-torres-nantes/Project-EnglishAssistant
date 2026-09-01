import logging
import sys
import time
try:
    import msvcrt
except ImportError:
    msvcrt = None

from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich.markup import escape

from services.audio_capture_service import AudioCaptureService
from services.transcription_service import TranscriptionService
from services.response_service import ResponseService
from services.context_service import ContextService
from config.settings import Settings

logger = logging.getLogger(__name__)

class AssistantController:
    """Orquestra captura de áudio, transcrição e sugestão de resposta em tempo real."""

    def __init__(self, provider: str = Settings.DEFAULT_AI_PROVIDER, whisper_model: str = Settings.WHISPER_MODEL_SIZE):
        """
        Função de inicialização do controller do assistente de reuniões.

        Args:
            provider (str): Provedor de IA a usar ("claude" ou "gemini").
            whisper_model (str): Tamanho do modelo Whisper a carregar.

        Returns:
            None
        """
        self.provider = provider
        self.whisper_model = whisper_model
        self.console = Console()
        self.audio_service = AudioCaptureService()
        self.transcription_service = TranscriptionService(model_size=whisper_model)
        self.response_service = ResponseService(provider=provider)
        self.context_service = ContextService()
        self.is_running = False

    def start(self) -> None:
        """
        Inicia o assistente: exibe status inicial e entra no laço de escuta.

        Returns:
            None
        """
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
        """
        Finaliza o assistente e todos os serviços que ele coordena.

        Returns:
            None
        """
        self.is_running = False
        self.audio_service.stop()
        self.transcription_service.stop()
        self.response_service.stop()

    def _new_status_live(self, panel: Panel) -> Live:
        """Cria um novo Live de status, já iniciado.

        Nunca reaproveitamos um Live parado (`stop()`) depois de imprimir
        conteúdo permanente no meio: o objeto guarda a posição/altura do seu
        último frame e, ao reiniciar (`start()`), redesenha por cima dessa
        área — que a essa altura já pertence ao conteúdo impresso depois do
        stop. Isso corrompia o terminal (borda sumindo, texto cortado). Um
        Live novo sempre parte de uma posição de cursor limpa.

        Args:
            panel: Painel inicial a exibir.

        Returns:
            O objeto Live já ativo (`start()` chamado).
        """
        live = Live(panel, console=self.console, auto_refresh=False, transient=True)
        live.start()
        return live

    def _process_loop(self) -> None:
        self.audio_service.start()
        accumulated_audio = []
        is_speaking = False
        # Limitamos o tempo de silencio para fechar o bloco mais rápido
        max_silence_frames = max(1, int(Settings.SILENCE_TIMEOUT_SECONDS / Settings.AUDIO_CHUNK_DURATION_SECONDS))

        silence_frames = 0
        last_transcribe_time = 0

        listening_panel = Panel(Text("🎧 Listening to system audio... (Press 'p' to force reply)", style="dim italic"), border_style="blue", title="Status")

        live = self._new_status_live(listening_panel)
        try:
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
                            live.update(Panel(Text("🔊 Speech detected! Recording...", style="bold green"), border_style="green", title="Status"), refresh=True)
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
                            window_frames = max(1, int(Settings.PARTIAL_TRANSCRIBE_WINDOW_SECONDS / Settings.AUDIO_CHUNK_DURATION_SECONDS))
                            partial_text = self.transcription_service.transcribe(accumulated_audio[-window_frames:])
                            if partial_text:
                                live.update(Panel(Text(f"🎙️ {partial_text} ...", style="bold cyan"), border_style="cyan", title="Transcribing... (Press 'p' to force)"), refresh=True)
                        except Exception as e:
                            logger.error("Erro na transcrição parcial (streaming): %s", e)
                        last_transcribe_time = time.time()

                    if silence_frames > max_silence_frames or force_process:
                        # Momento de processar final
                        if force_process:
                            live.stop()
                            self.console.print(Panel(Text("🛑 Force processing triggered by user ('p' pressed)", style="bold red"), border_style="red"))
                            live = self._new_status_live(Panel(Text("⏳ Finalizing transcription...", style="bold yellow"), border_style="yellow", title="Status"))
                        else:
                            live.update(Panel(Text("⏳ Finalizing transcription...", style="bold yellow"), border_style="yellow", title="Status"), refresh=True)

                        transcribe_start = time.time()
                        transcription = self.transcription_service.transcribe(accumulated_audio)
                        transcribe_elapsed = time.time() - transcribe_start

                        if transcription and transcription.strip():
                            # Encerra o Live de status (apaga o painel transiente) para imprimir
                            # conteúdo permanente; o objeto é descartado, nunca reaproveitado.
                            live.stop()

                            # Imprime a transcrição permanentemente
                            self.console.print(Panel(escape(transcription), title=f"🎙️ Transcription ({transcribe_elapsed:.2f}s)", border_style="cyan"))

                            context = self.context_service.load_all_context()
                            generate_start = time.time()

                            if Settings.STREAMING:
                                # Impressao incremental simples (sem Live): um Live com altura
                                # mudando a cada update, logo depois de outro Live parado,
                                # corrompia o redraw no console (bordas sumindo, texto cortado).
                                self.console.print("[bold green]🤖 AI Suggestions:[/]")
                                response = ""
                                try:
                                    for chunk in self.response_service.generate_response_stream(transcription, context):
                                        response += chunk
                                        self.console.print(chunk, end="", markup=False)
                                        sys.stdout.flush()
                                    generate_elapsed = time.time() - generate_start
                                    self.console.print(f"\n[dim]({generate_elapsed:.2f}s)[/]\n")
                                except Exception as e:
                                    logger.error("Erro ao gerar resposta em streaming: %s", e)
                                    response = f"Error generating response: {str(e)}"
                                    self.console.print(Panel(escape(response), title="🤖 Error", border_style="red"))
                            else:
                                self.console.print("[dim]🧠 Generating AI suggestions...[/]", end="\r")
                                response = self.response_service.generate_response(transcription, context)
                                self.console.print(" " * 40, end="\r")
                                generate_elapsed = time.time() - generate_start
                                self.console.print(Panel(escape(response), title=f"🤖 AI Suggestions ({generate_elapsed:.2f}s)", border_style="green"))

                            # Novo Live para o status idle — nunca reaproveita o anterior.
                            live = self._new_status_live(listening_panel)

                        # Reseta os contadores e limpa
                        accumulated_audio = []
                        is_speaking = False
                        silence_frames = 0

                        # Limpa o áudio que continuou sendo capturado em background
                        with self.audio_service.audio_queue.mutex:
                            self.audio_service.audio_queue.queue.clear()

                        if force_process:
                            live.update(Panel(Text("⏳ Paused to avoid immediate feedback...", style="dim yellow"), border_style="yellow", title="Status"), refresh=True)
                            time.sleep(1.5)
                            with self.audio_service.audio_queue.mutex:
                                self.audio_service.audio_queue.queue.clear()

                        # Volta pro painel de listening
                        live.update(listening_panel, refresh=True)

                time.sleep(0.01)
        finally:
            live.stop()

if __name__ == "__main__":
    pass
