"""Benchmark de tempo e qualidade de resposta entre configurações de provider/modelo de IA."""
import logging
import statistics
import sys
import time
import os
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger(__name__)


class AIResponseBenchmark:
    """Compara ResponseService.generate_response entre configurações de provider/modelo.

    Reproduz o caminho de código real usado pelo AssistantController em produção,
    contra um prompt de reunião realista (não o "Hello, test" genérico do comando
    `test-ai`), para medir tempo e avaliar a qualidade da resposta gerada.
    """

    _TRANSCRIPTION = (
        "So, we looked at the Q3 numbers and honestly the churn rate went up again. "
        "I think we need to understand why customers are leaving before we commit to "
        "the new pricing tier. What's your take on this? Do you think we should delay "
        "the launch until we have better retention data?"
    )

    _CONTEXT = (
        "Meeting: Product pricing review with the VP of Product. "
        "The user is a backend engineer being asked for their opinion on a business decision."
    )

    def __init__(self, runs_per_config: int = 3) -> None:
        """
        Função de inicialização do benchmark.

        Args:
            runs_per_config (int): Número de chamadas repetidas por configuração testada.

        Returns:
            None
        """
        self.runs_per_config = runs_per_config

    def run_config(self, name: str, env_overrides: Dict[str, str]) -> Dict:
        """Roda N chamadas de ResponseService.generate_response para uma configuração.

        Args:
            name: Nome descritivo da configuração testada (ex: "Claude Sonnet").
            env_overrides: Variáveis de ambiente a sobrescrever antes do teste
                (ex: {"AI_PROVIDER": "claude", "CLAUDE_MODEL": "sonnet"}).

        Returns:
            Dicionário com a lista de tempos medidos e a última resposta gerada.
        """
        for key, value in env_overrides.items():
            os.environ[key] = value

        # Settings le os.environ no momento da definicao da classe (import-time),
        # entao os modulos config/services precisam ser reimportados a cada
        # configuracao testada para que a mudanca de env var tenha efeito.
        for module_name in list(sys.modules):
            if module_name.startswith(("config", "services")):
                del sys.modules[module_name]

        from services.response_service import ResponseService

        times: List[float] = []
        last_response = None
        for run_index in range(self.runs_per_config):
            service = ResponseService(provider=env_overrides["AI_PROVIDER"])
            start = time.time()
            try:
                last_response = service.generate_response(self._TRANSCRIPTION, self._CONTEXT)
                elapsed = time.time() - start
                times.append(elapsed)
                logger.info("[%s] run %d/%d: %.2fs", name, run_index + 1, self.runs_per_config, elapsed)
            except Exception as e:
                elapsed = time.time() - start
                logger.error("[%s] run %d/%d falhou apos %.2fs: %s", name, run_index + 1, self.runs_per_config, elapsed, e)

        return {"times": times, "response": last_response}

    def run_all(self, configs: List[Dict]) -> None:
        """Roda todas as configurações e imprime um resumo comparativo no console.

        Args:
            configs: Lista de dicts com "name" e "env" (variáveis de ambiente a aplicar).
        """
        results = {}
        for config in configs:
            print(f"\n=== Testando: {config['name']} ===")
            results[config["name"]] = self.run_config(config["name"], config["env"])

        print("\n\n========== RESUMO ==========")
        for name, data in results.items():
            times = data["times"]
            if not times:
                print(f"\n{name}: TODAS AS RUNS FALHARAM")
                continue
            print(f"\n{name}:")
            print(f"  Media: {statistics.mean(times):.2f}s | Min: {min(times):.2f}s | Max: {max(times):.2f}s | Runs OK: {len(times)}/{self.runs_per_config}")
            print(f"  Ultima resposta:\n---\n{data['response']}\n---")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    benchmark = AIResponseBenchmark(runs_per_config=3)
    benchmark.run_all([
        {"name": "Claude Haiku", "env": {"AI_PROVIDER": "claude", "CLAUDE_MODEL": "haiku"}},
        {"name": "Claude Sonnet", "env": {"AI_PROVIDER": "claude", "CLAUDE_MODEL": "sonnet"}},
        {"name": "Gemini 3.5 Flash High", "env": {"AI_PROVIDER": "gemini", "GEMINI_MODEL": "gemini-3.5-flash-high"}},
    ])
