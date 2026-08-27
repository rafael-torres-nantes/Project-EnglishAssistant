import os
import logging
import sys
import io
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

class Settings:
    DEFAULT_AI_PROVIDER = os.environ.get("AI_PROVIDER", "claude")
    DEFAULT_CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "haiku")
    DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-high")
    DEFAULT_TIMEOUT = 180
    DEFAULT_BUDGET_USD = 0.50
    STREAMING = os.environ.get("STREAMING", "False").strip().lower() == "true"
    AUDIO_SAMPLE_RATE = 16000
    AUDIO_CHANNELS = 1
    AUDIO_CHUNK_DURATION_SECONDS = 0.5
    SILENCE_THRESHOLD = 500
    SILENCE_TIMEOUT_SECONDS = float(os.environ.get("SILENCE_TIMEOUT_SECONDS", "2.5"))
    WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "small")
    WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "en")
    WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
    WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "float16")
    WHISPER_BEAM_SIZE = int(os.environ.get("WHISPER_BEAM_SIZE", "1"))
    INPUT_DATA_DIR = Path("input_data")
    OUTPUT_DIR = Path("output")
    HTTP_HOST = "127.0.0.1"
    HTTP_PORT = 8778


    @staticmethod
    def force_utf8_console() -> None:
        if sys.platform == "win32":
            if isinstance(sys.stdout, io.TextIOWrapper):
                sys.stdout.reconfigure(encoding="utf-8")
            if isinstance(sys.stderr, io.TextIOWrapper):
                sys.stderr.reconfigure(encoding="utf-8")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # local test
    Settings.force_utf8_console()
    logger.info("Configuracoes carregadas com sucesso.")
    logger.info("Provider: %s", Settings.DEFAULT_AI_PROVIDER)
    logger.info("Claude Model: %s", Settings.DEFAULT_CLAUDE_MODEL)
    logger.info("Gemini Model: %s", Settings.DEFAULT_GEMINI_MODEL)
