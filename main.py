import argparse
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("faster_whisper").setLevel(logging.WARNING)

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(): pass

from config.settings import Settings
from controllers.assistant_controller import AssistantController
from services.context_service import ContextService
from services.audio_capture_service import AudioCaptureService
from services.response_service import ResponseService

logger = logging.getLogger(__name__)

_BANNER = """╔══════════════════════════════════════════════════╗
║        🎧 English Meeting Assistant 🎧          ║
║     Real-time AI-powered meeting support         ║
╚══════════════════════════════════════════════════╝"""

def main():
    Settings.force_utf8_console()
    load_dotenv()

    parser = argparse.ArgumentParser(description="English Meeting Assistant")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # listen command
    listen_parser = subparsers.add_parser("listen", help="Start listening to system audio")
    listen_parser.add_argument("--provider", default=Settings.DEFAULT_AI_PROVIDER, help="claude or gemini")
    listen_parser.add_argument("--whisper-model", default=Settings.WHISPER_MODEL_SIZE, help="tiny/base/small/medium/large-v3")
    listen_parser.add_argument("--language", default=Settings.WHISPER_LANGUAGE, help="Language code")

    # context command
    context_parser = subparsers.add_parser("context", help="Manage context files in input_data/")
    context_subparsers = context_parser.add_subparsers(dest="context_command")

    context_subparsers.add_parser("list", help="List context files")

    context_show_parser = context_subparsers.add_parser("show", help="Show context file contents")
    context_show_parser.add_argument("filename", help="Name of the file to show")

    # test-audio command
    subparsers.add_parser("test-audio", help="Test audio capture for 5 seconds")

    # test-ai command
    test_ai_parser = subparsers.add_parser("test-ai", help="Send a test prompt to the AI provider")
    test_ai_parser.add_argument("--provider", default=Settings.DEFAULT_AI_PROVIDER, help="claude or gemini")

    args = parser.parse_args()

    if args.command is None or args.command == "listen":
        print(_BANNER)
        provider = getattr(args, "provider", Settings.DEFAULT_AI_PROVIDER)
        whisper_model = getattr(args, "whisper_model", Settings.WHISPER_MODEL_SIZE)
        controller = AssistantController(provider=provider, whisper_model=whisper_model)
        controller.start()

    elif args.command == "context":
        context_service = ContextService()
        if args.context_command == "list":
            files = context_service.list_files()
            print("Context files in input_data/:")
            for f in files:
                print(f"  - {f}")
            if not files:
                print("  (no context files found in input_data/)")
        elif args.context_command == "show":
            content = context_service.load_file(args.filename)
            if content:
                print(f"Content of {args.filename}:")
                print(content)
            else:
                print(f"File not found: {args.filename}")

    elif args.command == "test-audio":
        print(_BANNER)
        print("Testing audio capture for 5 seconds...")
        audio_service = AudioCaptureService()
        audio_service.start()
        time.sleep(5)
        chunks = []
        for _ in range(50):
            chunk = audio_service.get_audio_chunk()
            if chunk:
                chunks.append(chunk)
            time.sleep(0.1)
        audio_service.stop()
        if chunks:
            print(f"Audio detected successfully. Captured {len(chunks)} chunks.")
        else:
            print("No audio detected. Check your audio device.")

    elif args.command == "test-ai":
        print(_BANNER)
        provider = args.provider
        print(f"Testing AI provider: {provider}")
        response_service = ResponseService(provider=provider)
        response = response_service.generate_response("Hello, this is a test prompt.", "")
        print("Response:")
        print(response)

if __name__ == "__main__":
    main()
