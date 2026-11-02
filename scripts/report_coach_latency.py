"""Resume as medições de latência do treinador gravadas em output/coach_latency.jsonl."""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import Settings


class CoachLatencyReport:
    """Agrupa as medições por modo e imprime a mediana acumulada de cada etapa."""

    _STAGES = ("capture_closed", "audio_ready", "first_transcript", "transcript_done", "analysis_done", "ai_request_sent", "ai_first_word", "ai_done")

    def __init__(self, path: Path = Settings.COACH_LATENCY_LOG) -> None:
        """
        Função de inicialização do relatório.

        Args:
            path: Arquivo JSONL com as medições.

        Returns:
            None
        """
        self.path = path

    def load(self) -> list[dict]:
        """
        Lê as medições do arquivo.

        Returns:
            Lista de medições; vazia se o arquivo não existir.
        """
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def print_report(self) -> None:
        """
        Imprime a mediana por modo, origem e estado da CLI.

        Returns:
            None
        """
        groups = {}
        for record in self.load():
            key = (record["mode"], record["source"], "aquecida" if record.get("warm_cli") else "fria")
            groups.setdefault(key, []).append(record)
        if not groups:
            print(f"Sem medições em {self.path}")
            return
        for key, records in sorted(groups.items()):
            print(f"\n{key[0]} | {key[1]} | CLI {key[2]} | n={len(records)}")
            for stage in self._STAGES:
                values = [record["stages"][stage] for record in records if stage in record["stages"]]
                if values:
                    print(f"  {stage:<18} {statistics.median(values):6.2f} s (min {min(values):.2f}, max {max(values):.2f})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    CoachLatencyReport().print_report()
