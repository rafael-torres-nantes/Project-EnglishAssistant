import logging
import subprocess
import json
from pathlib import Path
from typing import Iterator

from config.settings import Settings

logger = logging.getLogger(__name__)

class GeminiCLIService:
    """Executa o Gemini CLI (Antigravity/agy.exe) localmente, headless."""

    def __init__(self, model: str = Settings.DEFAULT_GEMINI_MODEL, timeout: int = Settings.DEFAULT_TIMEOUT):
        """
        Função de inicialização do serviço de CLI do Gemini.

        Args:
            model (str): Modelo Gemini a usar (ex: "gemini-3.5-flash-high").
            timeout (int): Tempo máximo em segundos para cada chamada da CLI.

        Returns:
            None
        """
        self.model = model
        self.timeout = timeout
        self.executable = self.resolve_executable()

    def resolve_executable(self) -> str:
        """
        Localiza o executável do Gemini CLI (agy.exe) instalado pelo Antigravity.

        Returns:
            str: Caminho absoluto do executável.

        Raises:
            RuntimeError: Se o executável não existir no caminho esperado.
        """
        exe = Path.home() / 'AppData' / 'Local' / 'agy' / 'bin' / 'agy.exe'
        if not exe.exists():
            raise RuntimeError(f"Gemini CLI executable not found at {exe}. Install Antigravity first.")
        return str(exe)

    def _build_command(self, prompt: str, system_prompt: str, output_format: str) -> list[str]:
        # agy.exe uses a positional argument after --print instead of a --prompt flag
        full_prompt = f"System Instruction: {system_prompt}\n\n{prompt}" if system_prompt else prompt
        return [
            self.executable, '--print', full_prompt, '--model', self.model,
            '--output-format', output_format
        ]

    def run_text(self, prompt: str, system_prompt: str) -> str:
        """
        Executa o Gemini CLI de forma síncrona e retorna a resposta completa em texto.

        Args:
            prompt (str): Texto de entrada do usuário.
            system_prompt (str): Instrução de sistema.

        Returns:
            str: Resposta gerada pelo modelo, sem espaços nas bordas.

        Raises:
            subprocess.TimeoutExpired: Se a CLI exceder o tempo limite configurado.
            subprocess.CalledProcessError: Se a CLI retornar código de erro.
        """
        cmd = self._build_command(prompt, system_prompt, 'text')
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, encoding='utf-8')
            result.check_returncode()
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.error("Gemini CLI timed out after %d seconds.", self.timeout)
            raise
        except subprocess.CalledProcessError as e:
            logger.error("Gemini CLI failed: %s", e.stderr)
            raise

    def run_text_stream(self, prompt: str, system_prompt: str) -> Iterator[str]:
        """Gera a resposta em texto sem streaming real (produz um único pedaço).

        O agy.exe (Antigravity/Gemini CLI) não tem um formato de streaming
        incremental mapeado neste projeto; a resposta completa é entregue como
        um único pedaço, mantendo a mesma interface do ClaudeCLIService.

        Args:
            prompt: Texto enviado como entrada do usuário.
            system_prompt: Instrução de sistema.

        Yields:
            A resposta completa como um único pedaço de texto.
        """
        yield self.run_text(prompt, system_prompt)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # local test
