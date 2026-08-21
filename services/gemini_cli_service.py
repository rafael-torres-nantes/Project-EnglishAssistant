import logging
import subprocess
import json
from pathlib import Path
from typing import Iterator

from config.settings import Settings

logger = logging.getLogger(__name__)

class GeminiCLIService:
    def __init__(self, model: str = Settings.DEFAULT_GEMINI_MODEL, timeout: int = Settings.DEFAULT_TIMEOUT):
        self.model = model
        self.timeout = timeout
        self.executable = self.resolve_executable()

    def resolve_executable(self) -> str:
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

    def run_json(self, prompt: str, system_prompt: str) -> dict:
        cmd = self._build_command(prompt, system_prompt, 'json')
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, encoding='utf-8')
            result.check_returncode()
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            logger.error("Gemini CLI timed out after %d seconds.", self.timeout)
            raise
        except subprocess.CalledProcessError as e:
            logger.error("Gemini CLI failed: %s", e.stderr)
            raise
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON: %s", e)
            raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # local test
