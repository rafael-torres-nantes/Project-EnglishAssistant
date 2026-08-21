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
    def __init__(self, model: str = Settings.DEFAULT_CLAUDE_MODEL, timeout: int = Settings.DEFAULT_TIMEOUT, budget_usd: float = Settings.DEFAULT_BUDGET_USD):
        self.model = model
        self.timeout = timeout
        self.budget_usd = budget_usd
        self.executable = self.resolve_executable()

    def resolve_executable(self) -> str:
        # Prefer the real claude.exe (set by the Claude Code install itself) over the
        # npm .cmd shim: shutil.which("claude") resolves to claude.CMD on Windows, which
        # Windows routes through cmd.exe, adding a shell-parsing hop we don't need.
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
        # The prompt itself is sent via stdin for the same reason: it can contain
        # newlines (e.g. multi-line meeting transcriptions) that would otherwise
        # be truncated by cmd.exe if passed as a CLI argument.
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
