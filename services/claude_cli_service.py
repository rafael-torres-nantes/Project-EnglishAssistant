import logging
import subprocess
import shutil
import json

from config.settings import Settings

logger = logging.getLogger(__name__)

class ClaudeCLIService:
    def __init__(self, model: str = Settings.DEFAULT_CLAUDE_MODEL, timeout: int = Settings.DEFAULT_TIMEOUT, budget_usd: float = Settings.DEFAULT_BUDGET_USD):
        self.model = model
        self.timeout = timeout
        self.budget_usd = budget_usd
        self.executable = self.resolve_executable()

    def resolve_executable(self) -> str:
        exe = shutil.which("claude")
        if not exe:
            raise RuntimeError("Claude CLI executable not found in PATH. Run 'claude auth login' first.")
        return exe

    def _build_command(self, prompt: str, system_prompt: str, output_format: str) -> list[str]:
        return [
            self.executable, '-p', prompt, '--model', self.model, '--output-format', output_format,
            '--system-prompt', system_prompt, '--tools', '', '--safe-mode',
            '--max-budget-usd', str(self.budget_usd)
        ]

    def run_text(self, prompt: str, system_prompt: str) -> str:
        cmd = self._build_command(prompt, system_prompt, 'text')
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, encoding='utf-8')
            result.check_returncode()
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            logger.error("Claude CLI timed out after %d seconds.", self.timeout)
            raise
        except subprocess.CalledProcessError as e:
            logger.error("Claude CLI failed: %s", e.stderr)
            raise

    def run_json(self, prompt: str, system_prompt: str) -> dict:
        cmd = self._build_command(prompt, system_prompt, 'json')
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, encoding='utf-8')
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
