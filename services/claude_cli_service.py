import logging
import subprocess
import shutil
import json
import os
import tempfile
from contextlib import contextmanager
from typing import Iterator

from config.settings import Settings

logger = logging.getLogger(__name__)

class ClaudeCLIService:
    """Executa o Claude Code CLI localmente, headless, sem chave de API."""

    def __init__(self, model: str = Settings.DEFAULT_CLAUDE_MODEL, timeout: int = Settings.DEFAULT_TIMEOUT, budget_usd: float = Settings.DEFAULT_BUDGET_USD):
        """
        Função de inicialização do serviço de CLI do Claude.

        Args:
            model (str): Modelo Claude a usar (ex: "haiku", "sonnet").
            timeout (int): Tempo máximo em segundos para cada chamada da CLI.
            budget_usd (float): Orçamento máximo em dólares por chamada (--max-budget-usd).

        Returns:
            None
        """
        self.model = model
        self.timeout = timeout
        self.budget_usd = budget_usd
        self.executable = self.resolve_executable()

    def resolve_executable(self) -> str:
        """
        Localiza o executável real do Claude Code CLI no sistema.

        Prefere claude.exe (definido pelo próprio instalador do Claude Code) em vez
        do shim .cmd do npm, que no Windows passa por cmd.exe desnecessariamente.

        Returns:
            str: Caminho absoluto do executável.

        Raises:
            RuntimeError: Se o executável não for encontrado no PATH.
        """
        exe = os.environ.get("CLAUDE_CODE_EXECPATH") or shutil.which("claude")
        if not exe or not os.path.isfile(exe):
            raise RuntimeError("Claude CLI executable not found in PATH. Run 'claude auth login' first.")
        return exe

    @staticmethod
    @contextmanager
    def _system_prompt_file(system_prompt: str):
        # `claude` resolves to a .cmd shim on Windows, which routes through cmd.exe.
        # cmd.exe truncates CLI arguments at the first embedded newline, so a
        # multi-line system prompt must be passed via file instead of --system-prompt.
        fd, path = tempfile.mkstemp(suffix='.txt', text=True)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(system_prompt)
            yield path
        finally:
            os.unlink(path)

    def _build_command(self, system_prompt_file: str, output_format: str) -> list[str]:
        return [
            self.executable, '-p', '--model', self.model, '--output-format', output_format,
            '--system-prompt-file', system_prompt_file, '--tools', '', '--safe-mode',
            '--max-budget-usd', str(self.budget_usd)
        ]

    def run_text(self, prompt: str, system_prompt: str) -> str:
        """
        Executa o Claude CLI de forma síncrona e retorna a resposta completa em texto.

        O prompt é enviado via stdin (não como argumento de CLI) porque pode conter
        quebras de linha, que o cmd.exe truncaria.

        Args:
            prompt (str): Texto de entrada do usuário.
            system_prompt (str): Instrução de sistema.

        Returns:
            str: Resposta gerada pelo modelo, sem espaços nas bordas.

        Raises:
            subprocess.TimeoutExpired: Se a CLI exceder o tempo limite configurado.
            subprocess.CalledProcessError: Se a CLI retornar código de erro.
        """
        try:
            with self._system_prompt_file(system_prompt) as sp_file:
                cmd = self._build_command(sp_file, 'text')
                result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout, encoding='utf-8')
            result.check_returncode()
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.error("Claude CLI timed out after %d seconds.", self.timeout)
            raise
        except subprocess.CalledProcessError as e:
            logger.error("Claude CLI failed: %s", e.stderr)
            raise

    def run_text_stream(self, prompt: str, system_prompt: str) -> Iterator[str]:
        """Gera a resposta em texto de forma incremental (streaming).

        Usa --output-format stream-json --include-partial-messages para receber
        os pedaços de texto assim que o modelo os gera, em vez de esperar a
        resposta completa. Eventos de "thinking" e de assinatura são ignorados;
        apenas os deltas de texto visível (text_delta) são repassados.

        Args:
            prompt: Texto enviado como entrada do usuário (via stdin).
            system_prompt: Instrução de sistema (via arquivo temporário).

        Yields:
            Pedaços de texto (deltas) da resposta assim que chegam.

        Raises:
            subprocess.TimeoutExpired: Se o processo exceder o tempo limite configurado.
            RuntimeError: Se o processo da CLI terminar com código de erro.
        """
        with self._system_prompt_file(system_prompt) as sp_file:
            cmd = self._build_command(sp_file, 'stream-json') + ['--include-partial-messages', '--verbose']
            process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', bufsize=1
            )
            process.stdin.write(prompt)
            process.stdin.close()

            try:
                for line in process.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    event = json.loads(line)
                    if event.get('type') != 'stream_event':
                        continue
                    delta = event['event'].get('delta', {})
                    if delta.get('type') == 'text_delta':
                        yield delta['text']

                return_code = process.wait(timeout=self.timeout)
                if return_code != 0:
                    stderr_output = process.stderr.read()
                    logger.error("Claude CLI failed: %s", stderr_output)
                    raise RuntimeError(f"Claude CLI exited with code {return_code}: {stderr_output}")
            except subprocess.TimeoutExpired:
                process.kill()
                logger.error("Claude CLI timed out after %d seconds.", self.timeout)
                raise

    def run_json(self, prompt: str, system_prompt: str) -> dict:
        """
        Executa o Claude CLI e retorna a resposta decodificada como JSON.

        Args:
            prompt (str): Texto de entrada do usuário.
            system_prompt (str): Instrução de sistema.

        Returns:
            dict: Resposta decodificada do JSON retornado pela CLI.

        Raises:
            subprocess.TimeoutExpired: Se a CLI exceder o tempo limite configurado.
            subprocess.CalledProcessError: Se a CLI retornar código de erro.
            json.JSONDecodeError: Se a saída não for um JSON válido.
        """
        try:
            with self._system_prompt_file(system_prompt) as sp_file:
                cmd = self._build_command(sp_file, 'json')
                result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout, encoding='utf-8')
            result.check_returncode()
            return json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            logger.error("Claude CLI timed out after %d seconds.", self.timeout)
            raise
        except subprocess.CalledProcessError as e:
            logger.error("Claude CLI failed: %s", e.stderr)
            raise
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON: %s", e)
            raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # local test
