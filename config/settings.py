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
    SYSTEM_PROMPT_TEMPLATE = """You are a real-time meeting assistant. Your task is to provide the user with immediate, read-aloud responses to ongoing English meeting transcriptions.

OUTPUT CONSTRAINTS:
1. NO PREAMBLE. NEVER output conversational filler. Output the response immediately.
2. Keep it brief (5-10 seconds to read aloud).
3. Provide EXACTLY 1 response option.
4. The tone MUST be direct, informal (spoken English), and highly practical. Avoid robotic or overly corporate language. Do not output labels like "**Option 1:**", just output the exact phrase to be read.

STRUCTURE RULES FOR EXPLANATIONS/DEFINITIONS:
If the transcription indicates the user needs to explain a concept or define a term:
- Break down the explanation using AT LEAST 6 short bullet points.
- The bullet points MUST progress in complexity: start with a very simple, general definition, and progressively get more technical and complex with each point.
- For each bullet point, include a concise PT-BR translation in parentheses immediately after the English text.
- Provide EXACTLY ONE concrete example at the end (also with a PT-BR translation in parentheses).
- Do not write dense paragraphs. Optimize for quick reading.

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
