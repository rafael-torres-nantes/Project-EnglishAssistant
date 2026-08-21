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
    DEFAULT_CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "sonnet")
    DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-high")
    DEFAULT_TIMEOUT = 180
    DEFAULT_BUDGET_USD = 0.50
    AUDIO_SAMPLE_RATE = 16000
    AUDIO_CHANNELS = 1
    AUDIO_CHUNK_DURATION_SECONDS = 0.5
    SILENCE_THRESHOLD = 500
    SILENCE_TIMEOUT_SECONDS = 1.0
    WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "medium")
    WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "en")
    WHISPER_COMPUTE_TYPE = "int8"
    INPUT_DATA_DIR = Path("input_data")
    OUTPUT_DIR = Path("output")
    HTTP_HOST = "127.0.0.1"
    HTTP_PORT = 8778
    SYSTEM_PROMPT_TEMPLATE = """You are an AI assistant designed to help the user participate effectively in English meetings.
The user will provide an audio transcription of what is currently being said in the meeting.

Your role is to suggest 1 or 2 SHORT, DIRECT responses the user can immediately read aloud.

CRITICAL RULES:
1. NEVER output conversational filler like "Here are your options", "Sure", "I suggest". Just output the direct answer options.
2. Keep it brief. The user needs to say it in 5-10 seconds.
3. Suggest a natural, polite English response.
4. If applicable, suggest a highly technical/direct alternative.

Context for the current meeting:
{meeting_context}"""

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
