import logging
from pathlib import Path

from config.settings import Settings

logger = logging.getLogger(__name__)

class ContextService:
    def __init__(self, context_dir: Path = Settings.INPUT_DATA_DIR):
        self.context_dir = context_dir
        if not self.context_dir.exists():
            self.context_dir.mkdir(parents=True, exist_ok=True)

    def load_all_context(self) -> str:
        files = self.list_files()
        if not files:
            return ""

        context_parts = []
        for file in files:
            content = self.load_file(file)
            context_parts.append(f"=== Context from: {file} ===\n{content}")

        return "\n\n".join(context_parts)

    def load_file(self, filename: str) -> str:
        file_path = self.context_dir / filename
        if file_path.exists() and file_path.is_file():
            return file_path.read_text(encoding='utf-8')
        return ""

    def list_files(self) -> list[str]:
        if not self.context_dir.exists():
            return []

        files = []
        for p in self.context_dir.iterdir():
            if p.is_file() and p.suffix.lower() in ['.txt', '.md'] and p.name != '.gitkeep':
                files.append(p.name)
        return sorted(files)

    def get_context_summary(self) -> str:
        return self.load_all_context()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # local test
    service = ContextService()
    logger.info("Context files: %s", service.list_files())
    logger.info("Context summary:\n%s", service.get_context_summary())
