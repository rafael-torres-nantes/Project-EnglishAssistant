import logging
import re

logger = logging.getLogger(__name__)

class TextHelpers:
    _WHISPER_ARTIFACTS = [r"\[BLANK_AUDIO\]", r"\[SILENCE\]", r"\(silence\)", r"\[.*?\]"]

    @staticmethod
    def clean_transcription(text: str) -> str:
        for artifact in TextHelpers._WHISPER_ARTIFACTS:
            text = re.sub(artifact, "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def truncate(text: str, max_length: int) -> str:
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."

    @staticmethod
    def word_count(text: str) -> int:
        return len(text.split())

    @staticmethod
    def format_timestamp(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def sanitize_for_cli(text: str) -> str:
        sanitized = text.replace('"', '\\"').replace('\n', ' ')
        return sanitized

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # local test
