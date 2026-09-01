import logging
import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.markup import escape

from services.response_service import ResponseService
from services.context_service import ContextService
from config.settings import Settings

logger = logging.getLogger(__name__)

class TutorController:
    """Sessão de tutor de inglês interativo via terminal, em texto livre."""

    def __init__(self, provider: str = Settings.DEFAULT_AI_PROVIDER):
        """
        Função de inicialização do controller de tutor.

        Args:
            provider (str): Provedor de IA a usar ("claude" ou "gemini").

        Returns:
            None
        """
        self.provider = provider
        self.console = Console()
        self.response_service = ResponseService(provider=provider)
        self.context_service = ContextService()
        self.is_running = False

    def start(self) -> None:
        """
        Inicia a sessão interativa de tutor, lendo entradas do usuário até "exit"/"quit".

        Returns:
            None
        """
        self.is_running = True
        context_files = self.context_service.list_files()

        self.console.print(Panel(
            "[bold cyan]AI English Tutor[/]\n"
            f"Provider: [green]{self.provider}[/]\n"
            f"Context files loaded: {len(context_files)}\n"
            "Type [bold red]'exit'[/] or [bold red]'quit'[/] to stop.",
            title="Welcome",
            border_style="cyan"
        ))

        context = self.context_service.load_all_context()
        
        while self.is_running:
            try:
                user_input = Prompt.ask("\n[bold yellow]You[/]")
                if user_input.lower() in ['exit', 'quit']:
                    break
                
                if not user_input.strip():
                    continue

                if Settings.STREAMING:
                    self.console.print("[bold green]Tutor:[/] ", end="")
                    for chunk in self.response_service.generate_tutor_response_stream(user_input, context):
                        self.console.print(chunk, end="", markup=False)
                        sys.stdout.flush()
                    self.console.print()
                else:
                    self.console.print("[dim]Thinking...[/]", end="\r")
                    response = self.response_service.generate_tutor_response(user_input, context)
                    # Clear the thinking line
                    self.console.print(" " * 20, end="\r")
                    self.console.print(f"[bold green]Tutor:[/] {escape(response)}")

            except KeyboardInterrupt:
                break
            except Exception as e:
                self.console.print(f"\n[bold red]Error:[/] {e}")

        self.stop()

    def stop(self) -> None:
        """
        Finaliza a sessão de tutor.

        Returns:
            None
        """
        self.is_running = False
        self.response_service.stop()
        self.console.print("\n[bold yellow]Tutor session ended. Keep practicing![/]")
