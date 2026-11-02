import json
import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class LatencyTracker:
    """Marca o tempo acumulado de cada etapa de um pedido, sem guardar nenhum texto da fala."""

    def __init__(self, mode: str, source: str):
        """
        Função de inicialização do medidor; o relógio começa aqui.

        Args:
            mode: Modo do treinador.
            source: Origem do pedido ("mic", "text" ou "benchmark").

        Returns:
            None
        """
        self.started_at = time.perf_counter()
        self.stages = {}
        self.details = {"mode": mode, "source": source}

    def mark(self, stage: str) -> None:
        """
        Registra o tempo da etapa; só a primeira marcação de cada etapa vale.

        Args:
            stage: Nome da etapa.

        Returns:
            None
        """
        if stage not in self.stages:
            self.stages[stage] = round(time.perf_counter() - self.started_at, 3)

    def add_details(self, **details) -> None:
        """
        Acrescenta informações sobre o pedido (modelo, duração do áudio, idioma).

        Args:
            **details: Pares nome e valor.

        Returns:
            None
        """
        self.details.update(details)

    def as_dict(self) -> dict:
        """
        Devolve a medição para exibir ou salvar.

        Returns:
            Dicionário com os detalhes e as etapas em segundos acumulados.
        """
        return {**self.details, "stages": dict(self.stages)}

    def save(self, path: Path) -> None:
        """
        Acrescenta a medição a um arquivo JSONL.

        Args:
            path: Caminho do arquivo.

        Returns:
            None
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"at": datetime.now().isoformat(timespec="seconds"), **self.as_dict()}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tracker = LatencyTracker("rehearsal", "benchmark")
    tracker.mark("first")
    logger.info("Teste local: %s", tracker.as_dict())
