import json
import logging
import re
import time
from pathlib import Path

from config.settings import Settings
from prompt_template.meeting_prompt import MEETING_CONTEXT_SECTION, MEETING_INSTRUCTIONS, MEETING_SCOPE_RULE
from services.context_service import ContextService

logger = logging.getLogger(__name__)


class ListenWorkspaceService(ContextService):
    """Guarda os contextos selecionados e o prompt editável da aba Listen."""

    _NAME_PATTERN = re.compile(r"^[\w][\w \-.]{0,99}\.(md|txt)$", re.IGNORECASE)
    _MAX_TEXT_BYTES = 200 * 1024

    def __init__(self, context_dir: Path = Settings.INPUT_DATA_DIR):
        """Inicializa o espaço de trabalho do Listen.

        Args:
            context_dir: Diretório dos arquivos de contexto.

        Returns:
            None
        """
        super().__init__(context_dir)
        self._state_dir = self.context_dir / ".listen"
        self._settings_path = self._state_dir / "settings.json"
        self._prompt_path = self._state_dir / "prompt.md"
        self._trash_dir = self._state_dir / "trash"

    def list_files(self) -> list[str]:
        """Lista só os contextos selecionados, que são os enviados à IA.

        Returns:
            Nomes dos arquivos selecionados, em ordem alfabética.
        """
        excluded = self.load_excluded()
        return [name for name in self.list_all_files() if name not in excluded]

    def list_all_files(self) -> list[str]:
        """Lista todos os contextos, selecionados ou não.

        Returns:
            Nomes dos arquivos, em ordem alfabética.
        """
        return super().list_files()

    def load_excluded(self) -> set[str]:
        """Lê os contextos desmarcados; arquivo novo nasce selecionado.

        Returns:
            Conjunto com os nomes desmarcados.
        """
        if not self._settings_path.exists():
            return set()
        try:
            excluded = json.loads(self._settings_path.read_text(encoding="utf-8")).get("excluded", [])
        except (ValueError, AttributeError) as error:
            logger.warning("Configuração do Listen ilegível, usando todos os contextos: %s", error)
            return set()
        return {name for name in excluded if isinstance(name, str)}

    def save_excluded(self, excluded: set[str]) -> None:
        """Grava os contextos desmarcados.

        Args:
            excluded: Nomes desmarcados.

        Returns:
            None
        """
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(json.dumps({"excluded": sorted(excluded)}, ensure_ascii=False), encoding="utf-8")

    def validate_name(self, name) -> str:
        """Confere se o nome é de um arquivo direto da pasta de contexto.

        Args:
            name: Nome recebido da interface.

        Returns:
            O próprio nome, já validado.

        Raises:
            ValueError: Se o nome tiver caminho, extensão errada ou caractere inválido.
        """
        if not isinstance(name, str) or not self._NAME_PATTERN.fullmatch(name) or ".." in name:
            raise ValueError("Nome inválido. Use letras, números, espaço, hífen ou ponto, terminando em .md ou .txt.")
        return name

    def validate_text(self, text, label: str) -> str:
        """Confere tipo e tamanho de um texto vindo da interface.

        Args:
            text: Conteúdo recebido.
            label: Nome do campo usado na mensagem de erro.

        Returns:
            O próprio texto.

        Raises:
            ValueError: Se não for texto ou passar do limite.
        """
        if not isinstance(text, str):
            raise ValueError(f"{label} precisa ser texto.")
        if len(text.encode("utf-8")) > self._MAX_TEXT_BYTES:
            raise ValueError(f"{label} passou do limite de {self._MAX_TEXT_BYTES // 1024} KB.")
        return text

    def read_context(self, name) -> dict:
        """Lê um contexto para edição.

        Args:
            name: Nome do arquivo.

        Returns:
            Dicionário com `name` e `content`.

        Raises:
            ValueError: Se o nome for inválido ou o arquivo não existir.
        """
        valid_name = self.validate_name(name)
        if valid_name not in self.list_all_files():
            raise ValueError(f"Contexto não encontrado: {valid_name}")
        return {"name": valid_name, "content": self.load_file(valid_name)}

    def save_context(self, name, content, previous_name=None) -> str:
        """Cria, atualiza ou renomeia um contexto, deixando-o selecionado.

        Args:
            name: Nome final do arquivo.
            content: Texto do arquivo.
            previous_name: Nome atual, quando for edição.

        Returns:
            Nome gravado.

        Raises:
            ValueError: Se o nome ou o texto forem inválidos, ou se o nome já estiver em uso.
        """
        valid_name = self.validate_name(name)
        text = self.validate_text(content, "O contexto")
        old_name = self.validate_name(previous_name) if previous_name else None
        existing = self.list_all_files()
        if valid_name in existing and valid_name != old_name:
            raise ValueError(f"Já existe um contexto chamado {valid_name}.")
        (self.context_dir / valid_name).write_text(text, encoding="utf-8")

        excluded = self.load_excluded()
        excluded.discard(valid_name)
        if old_name and old_name != valid_name:
            if old_name in existing:
                (self.context_dir / old_name).unlink()
            excluded.discard(old_name)
        self.save_excluded(excluded)
        return valid_name

    def delete_context(self, name) -> None:
        """Move um contexto para a lixeira do Listen, de onde ele pode ser recuperado.

        Args:
            name: Nome do arquivo.

        Returns:
            None

        Raises:
            ValueError: Se o nome for inválido ou o arquivo não existir.
        """
        valid_name = self.read_context(name)["name"]
        self._trash_dir.mkdir(parents=True, exist_ok=True)
        (self.context_dir / valid_name).replace(self._trash_dir / f"{int(time.time())}-{valid_name}")
        excluded = self.load_excluded()
        excluded.discard(valid_name)
        self.save_excluded(excluded)

    def set_selection(self, selected) -> None:
        """Define quais contextos entram no prompt.

        Args:
            selected: Lista com os nomes que devem ficar selecionados.

        Returns:
            None

        Raises:
            ValueError: Se a lista for inválida.
        """
        if not isinstance(selected, list) or not all(isinstance(name, str) for name in selected):
            raise ValueError("A seleção precisa ser uma lista de nomes.")
        self.save_excluded(set(self.list_all_files()) - set(selected))

    def instructions(self) -> str:
        """Lê as instruções em uso, personalizadas ou padrão.

        Returns:
            Texto das instruções.
        """
        if self._prompt_path.exists():
            return self._prompt_path.read_text(encoding="utf-8")
        return MEETING_INSTRUCTIONS

    def save_prompt(self, instructions) -> None:
        """Grava as instruções personalizadas.

        Args:
            instructions: Novo texto.

        Returns:
            None

        Raises:
            ValueError: Se o texto estiver vazio ou for inválido.
        """
        text = self.validate_text(instructions, "O prompt")
        if not text.strip():
            raise ValueError("O prompt não pode ficar vazio. Use Restaurar padrão para voltar ao original.")
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._prompt_path.write_text(text, encoding="utf-8")

    def reset_prompt(self) -> None:
        """Volta para as instruções padrão.

        Returns:
            None
        """
        self._prompt_path.unlink(missing_ok=True)

    def system_prompt_template(self) -> str:
        """Monta o template enviado à IA, com escopo e contexto sempre no fim.

        As chaves do texto editável são escapadas porque o template passa por `str.format`.

        Returns:
            Template com o campo `meeting_context`.
        """
        editable = self.instructions().replace("{", "{{").replace("}", "}}")
        return f"{editable}\n\n{MEETING_SCOPE_RULE}\n\n{MEETING_CONTEXT_SECTION}"

    def workspace(self) -> dict:
        """Resume o estado para a interface.

        Returns:
            Dicionário com `contexts` e `prompt`.
        """
        excluded = self.load_excluded()
        contexts = [
            {
                "name": name,
                "bytes": len(self.load_file(name).encode("utf-8")),
                "selected": name not in excluded,
            }
            for name in self.list_all_files()
        ]
        return {
            "contexts": contexts,
            "prompt": {
                "instructions": self.instructions(),
                "is_custom": self._prompt_path.exists(),
                "scope_rule": MEETING_SCOPE_RULE,
            },
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Contextos do Listen: %s", ListenWorkspaceService().workspace()["contexts"])
