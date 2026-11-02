import json
import logging
import os
import subprocess
import tempfile
import threading
import time
from typing import Iterator

from config.settings import Settings
from services.claude_cli_service import ClaudeCLIService

logger = logging.getLogger(__name__)


class WarmClaudeService:
    """Mantém um processo da CLI já iniciado por prompt de sistema, para cortar a espera da 1ª palavra.

    Cada processo atende um único pedido e morre: nada se acumula entre as falas. Usa o login
    OAuth da CLI, sem chave de API.
    """

    def __init__(self, model: str = Settings.COACH_MODEL, effort: str = Settings.COACH_EFFORT, timeout: int = Settings.DEFAULT_TIMEOUT, budget_usd: float = Settings.DEFAULT_BUDGET_USD, max_age_seconds: int = Settings.COACH_WARM_MAX_AGE_SECONDS):
        """
        Função de inicialização do serviço de CLI aquecida.

        Args:
            model: Modelo Claude a usar.
            effort: Nível de esforço da CLI; vazio mantém o padrão do modelo.
            timeout: Tempo máximo em segundos para cada pedido.
            budget_usd: Orçamento máximo por pedido (--max-budget-usd).
            max_age_seconds: Idade a partir da qual um processo ocioso é descartado.

        Returns:
            None
        """
        self.cli = ClaudeCLIService(model=model, timeout=timeout, budget_usd=budget_usd)
        self.effort = effort
        self.timeout = timeout
        self.max_age_seconds = max_age_seconds
        self.pool = {}
        self.lock = threading.Lock()
        self.last_was_warm = False
        self.last_blocks = []

    def build_command(self, system_prompt_file: str) -> list[str]:
        """
        Monta o comando da CLI com entrada em stream-json.

        Com stream-json a CLI inicializa antes de receber o prompt, e é isso que permite o
        aquecimento.

        Args:
            system_prompt_file: Caminho do arquivo com o prompt de sistema.

        Returns:
            Lista de argumentos do processo.
        """
        command = [
            self.cli.executable, '-p', '--model', self.cli.model,
            '--input-format', 'stream-json', '--output-format', 'stream-json',
            '--include-partial-messages', '--verbose', '--no-session-persistence',
            '--system-prompt-file', system_prompt_file, '--tools', '', '--safe-mode',
            '--max-budget-usd', str(self.cli.budget_usd),
        ]
        if self.effort:
            command += ['--effort', self.effort]
        return command

    def spawn(self, system_prompt: str) -> dict:
        """
        Inicia um processo da CLI, que fica aguardando o prompt no stdin.

        Args:
            system_prompt: Instrução de sistema do processo.

        Returns:
            Dicionário com o processo, o arquivo temporário e o instante de criação.
        """
        fd, path = tempfile.mkstemp(suffix='.txt', text=True)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(system_prompt)
        process = subprocess.Popen(
            self.build_command(path), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding='utf-8', bufsize=1,
        )
        return {"process": process, "path": path, "created_at": time.monotonic()}

    def prewarm(self, system_prompt: str) -> None:
        """
        Garante um processo pronto para o prompt de sistema informado.

        Args:
            system_prompt: Instrução de sistema que o próximo pedido vai usar.

        Returns:
            None
        """
        with self.lock:
            entry = self.pool.get(system_prompt)
            if entry and self.is_usable(entry):
                return
            if entry:
                self.discard(entry)
            self.pool[system_prompt] = self.spawn(system_prompt)

    def is_usable(self, entry: dict) -> bool:
        """
        Verifica se um processo aquecido segue vivo e dentro da idade máxima.

        Args:
            entry: Entrada do pool.

        Returns:
            True se o processo pode atender um pedido.
        """
        alive = entry["process"].poll() is None
        return alive and time.monotonic() - entry["created_at"] < self.max_age_seconds

    @staticmethod
    def discard(entry: dict) -> None:
        """
        Encerra o processo de uma entrada e apaga o arquivo temporário.

        Args:
            entry: Entrada a descartar.

        Returns:
            None
        """
        process = entry["process"]
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        for pipe in (process.stdin, process.stdout):
            try:
                pipe.close()
            except OSError:
                pass
        os.unlink(entry["path"])

    def acquire(self, prompt: str, system_prompt: str) -> dict:
        """
        Entrega o prompt a um processo aquecido; se ele tiver morrido, inicia um novo.

        Args:
            prompt: Texto do pedido.
            system_prompt: Instrução de sistema do pedido.

        Returns:
            Entrada do processo que recebeu o prompt.
        """
        with self.lock:
            entry = self.pool.pop(system_prompt, None)
        message = json.dumps({"type": "user", "message": {"role": "user", "content": prompt}})
        if entry and self.is_usable(entry):
            try:
                entry["process"].stdin.write(message + "\n")
                entry["process"].stdin.close()
                self.last_was_warm = True
                return entry
            except OSError as error:
                logger.warning("Processo aquecido indisponível (%s); iniciando outro.", error)
        if entry:
            self.discard(entry)
        self.last_was_warm = False
        entry = self.spawn(system_prompt)
        entry["process"].stdin.write(message + "\n")
        entry["process"].stdin.close()
        return entry

    def stream(self, prompt: str, system_prompt: str) -> Iterator[str]:
        """
        Gera a resposta em streaming, repassando só o texto visível.

        Args:
            prompt: Texto do pedido.
            system_prompt: Instrução de sistema.

        Yields:
            Pedaços de texto assim que chegam.

        Raises:
            RuntimeError: Se a CLI falhar, reportar erro ou estourar o tempo limite.
        """
        self.last_blocks = []
        entry = self.acquire(prompt, system_prompt)
        process = entry["process"]
        # Ler o stdout bloqueia sem prazo; o timer mata o processo e encerra a leitura.
        watchdog = threading.Timer(self.timeout, process.kill)
        watchdog.start()
        finished = False
        try:
            for line in process.stdout:
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("type") == "stream_event":
                    if event["event"].get("type") == "content_block_start":
                        self.last_blocks.append(event["event"]["content_block"].get("type"))
                    delta = event["event"].get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield delta["text"]
                if event.get("type") == "result":
                    if event.get("is_error"):
                        raise RuntimeError(f"Claude CLI reportou erro: {event.get('result')}")
                    finished = True
                    break
            if not finished:
                raise RuntimeError(f"Claude CLI encerrou sem resposta (código {process.poll()}).")
        finally:
            watchdog.cancel()
            self.discard(entry)

    def stop(self) -> None:
        """
        Encerra todos os processos aquecidos.

        Returns:
            None
        """
        with self.lock:
            entries = list(self.pool.values())
            self.pool.clear()
        for entry in entries:
            self.discard(entry)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    service = WarmClaudeService()
    logger.info("Teste local: %s", "".join(service.stream("Say OK.", "Answer briefly.")))
    service.stop()
