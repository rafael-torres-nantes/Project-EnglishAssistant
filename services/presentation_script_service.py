import logging
import re

logger = logging.getLogger(__name__)


class PresentationScriptService:
    """Divide o roteiro de uma apresentação em partes ensaiáveis."""

    _HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
    _SEPARATOR = re.compile(r"^\s*(-{3,}|\*{3,})\s*$")

    def parse(self, script: str) -> list[dict]:
        """
        Separa o roteiro por títulos Markdown ou separadores; sem eles, por parágrafos.

        Args:
            script: Texto do roteiro.

        Returns:
            Lista de partes, cada uma com "title" e "text".

        Raises:
            ValueError: Se o roteiro estiver vazio.
        """
        if not script.strip():
            raise ValueError("O roteiro está vazio.")
        lines = script.splitlines()
        has_structure = any(self._HEADING.match(line) or self._SEPARATOR.match(line) for line in lines)
        if not has_structure:
            return self.parse_paragraphs(script)
        parts = []
        title = None
        body = []
        for line in lines:
            heading = self._HEADING.match(line)
            if heading or self._SEPARATOR.match(line):
                self.append_part(parts, title, body)
                title = heading.group(1) if heading else None
                body = []
                continue
            body.append(line)
        self.append_part(parts, title, body)
        return parts

    @staticmethod
    def append_part(parts: list[dict], title: str | None, body: list[str]) -> None:
        """
        Acrescenta uma parte à lista, ignorando blocos sem texto.

        Args:
            parts: Lista de partes em construção.
            title: Título da parte; None gera um título numerado.
            body: Linhas de texto da parte.

        Returns:
            None
        """
        text = "\n".join(body).strip()
        if text:
            parts.append({"title": title or f"Parte {len(parts) + 1}", "text": text})

    @staticmethod
    def parse_paragraphs(script: str) -> list[dict]:
        """
        Usa cada parágrafo como uma parte, para roteiro sem títulos.

        Args:
            script: Texto do roteiro.

        Returns:
            Lista de partes numeradas.
        """
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", script) if item.strip()]
        return [{"title": f"Parte {number}", "text": text} for number, text in enumerate(paragraphs, 1)]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Teste local: %s", PresentationScriptService().parse("# Abertura\nOlá\n\n# Fim\nObrigado"))
