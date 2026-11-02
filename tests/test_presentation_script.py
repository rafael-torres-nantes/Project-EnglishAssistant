import pytest

from services.presentation_script_service import PresentationScriptService


class TestPresentationScript:
    """Valida a divisão do roteiro em partes."""

    def test_splits_by_markdown_headings(self):
        parts = PresentationScriptService().parse("# Abertura\nOlá\n\n## Problema\nA fila cresce\n")
        assert parts == [{"title": "Abertura", "text": "Olá"}, {"title": "Problema", "text": "A fila cresce"}]

    def test_text_before_first_heading_becomes_a_part(self):
        parts = PresentationScriptService().parse("Bom dia\n# Tema\nFila")
        assert [part["title"] for part in parts] == ["Parte 1", "Tema"]

    def test_splits_by_separator(self):
        parts = PresentationScriptService().parse("Um\n---\nDois")
        assert [part["text"] for part in parts] == ["Um", "Dois"]

    def test_splits_plain_text_by_paragraph(self):
        parts = PresentationScriptService().parse("Primeiro.\n\nSegundo.")
        assert parts == [{"title": "Parte 1", "text": "Primeiro."}, {"title": "Parte 2", "text": "Segundo."}]

    def test_empty_script_is_rejected(self):
        with pytest.raises(ValueError):
            PresentationScriptService().parse("  \n ")
