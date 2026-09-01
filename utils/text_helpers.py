import logging
import re

logger = logging.getLogger(__name__)

class TextHelpers:
    """Funções auxiliares de manipulação de texto, sem estado."""

    _WHISPER_ARTIFACTS = [r"\[BLANK_AUDIO\]", r"\[SILENCE\]", r"\(silence\)", r"\[.*?\]"]

    @staticmethod
    def clean_transcription(text: str) -> str:
        """
        Remove artefatos comuns do Whisper e normaliza espaçamento.

        Args:
            text (str): Texto bruto retornado pela transcrição.

        Returns:
            str: Texto limpo, sem marcadores como "[BLANK_AUDIO]" e sem espaços duplicados.
        """
        for artifact in TextHelpers._WHISPER_ARTIFACTS:
            text = re.sub(artifact, "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def truncate(text: str, max_length: int) -> str:
        """
        Corta um texto no comprimento máximo, adicionando reticências se necessário.

        Args:
            text (str): Texto de entrada.
            max_length (int): Comprimento máximo permitido antes do corte.

        Returns:
            str: Texto original, ou truncado com "..." ao final.
        """
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."

    @staticmethod
    def word_count(text: str) -> int:
        """
        Conta o número de palavras em um texto, separadas por espaço em branco.

        Args:
            text (str): Texto de entrada.

        Returns:
            int: Número de palavras.
        """
        return len(text.split())

    @staticmethod
    def format_timestamp(seconds: float) -> str:
        """
        Formata uma duração em segundos como string "HH:MM:SS".

        Args:
            seconds (float): Duração em segundos.

        Returns:
            str: Duração formatada, ex: "01:01:01".
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def sanitize_for_cli(text: str) -> str:
        """
        Escapa aspas duplas e remove quebras de linha para uso seguro em argumento de CLI.

        Args:
            text (str): Texto de entrada.

        Returns:
            str: Texto com aspas escapadas e quebras de linha substituídas por espaço.
        """
        sanitized = text.replace('"', '\\"').replace('\n', ' ')
        return sanitized

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # local test
