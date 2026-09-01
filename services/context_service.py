import logging
from pathlib import Path

from config.settings import Settings

logger = logging.getLogger(__name__)

class ContextService:
    """Carrega arquivos de contexto (perfil, notas) usados nos prompts de IA."""

    def __init__(self, context_dir: Path = Settings.INPUT_DATA_DIR):
        """
        Função de inicialização do serviço de contexto.

        Args:
            context_dir (Path): Diretório onde ficam os arquivos de contexto.

        Returns:
            None
        """
        self.context_dir = context_dir
        if not self.context_dir.exists():
            self.context_dir.mkdir(parents=True, exist_ok=True)

    def load_all_context(self) -> str:
        """
        Carrega e concatena o conteúdo de todos os arquivos de contexto.

        Returns:
            str: Conteúdo de todos os arquivos, cada um precedido do nome de origem;
                string vazia se não houver arquivos.
        """
        files = self.list_files()
        if not files:
            return ""

        context_parts = []
        for file in files:
            content = self.load_file(file)
            context_parts.append(f"=== Context from: {file} ===\n{content}")

        return "\n\n".join(context_parts)

    def load_file(self, filename: str) -> str:
        """
        Lê o conteúdo de um arquivo de contexto específico.

        Args:
            filename (str): Nome do arquivo dentro do diretório de contexto.

        Returns:
            str: Conteúdo do arquivo; string vazia se não existir.
        """
        file_path = self.context_dir / filename
        if file_path.exists() and file_path.is_file():
            return file_path.read_text(encoding='utf-8')
        return ""

    def list_files(self) -> list[str]:
        """
        Lista os arquivos de contexto disponíveis (.txt e .md).

        Returns:
            list[str]: Nomes de arquivo ordenados alfabeticamente.
        """
        if not self.context_dir.exists():
            return []

        files = []
        for p in self.context_dir.iterdir():
            if p.is_file() and p.suffix.lower() in ['.txt', '.md'] and p.name != '.gitkeep':
                files.append(p.name)
        return sorted(files)

    def get_context_summary(self) -> str:
        """
        Retorna um resumo do contexto atual (hoje, equivalente ao contexto completo).

        Returns:
            str: Mesmo conteúdo de load_all_context().
        """
        return self.load_all_context()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # local test
    service = ContextService()
    logger.info("Context files: %s", service.list_files())
    logger.info("Context summary:\n%s", service.get_context_summary())
