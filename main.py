import argparse
import logging
import time

from config.settings import Settings

Settings.setup_cuda_dll_path()

logging.basicConfig(level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("faster_whisper").setLevel(logging.WARNING)

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(): pass

from controllers.assistant_controller import AssistantController
from controllers.tutor_controller import TutorController
from services.context_service import ContextService
from services.audio_capture_service import AudioCaptureService
from services.response_service import ResponseService
from utils.audio_helpers import AudioHelpers

logger = logging.getLogger(__name__)

_BANNER = """╔══════════════════════════════════════════════════╗
║        🎧 English Meeting Assistant 🎧          ║
║     Real-time AI-powered meeting support         ║
╚══════════════════════════════════════════════════╝"""

def main():
    """
    Ponto de entrada da CLI: parseia os argumentos e despacha para o comando escolhido.

    Returns:
        None
    """
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

    # tutor command
    tutor_parser = subparsers.add_parser("tutor", help="Start an interactive English Tutor session")
    tutor_parser.add_argument("--provider", default=Settings.DEFAULT_AI_PROVIDER, help="claude or gemini")

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
        chunks = []
        max_rms = 0.0
        end_time = time.time() + 5
        while time.time() < end_time:
            payload = audio_service.get_audio_chunk()
            if payload is None:
                continue
            data, sample_rate, channels = payload
            chunks.append(payload)
            audio_array = AudioHelpers.pcm_to_float32(data, sample_rate, channels)
            max_rms = max(max_rms, AudioHelpers.calculate_rms(audio_array))
        audio_service.stop()
        if not chunks:
            print("No audio detected. Check your audio device.")
        elif max_rms > Settings.SPEECH_RMS_THRESHOLD:
            print(f"Audio detected successfully. Captured {len(chunks)} chunks, peak RMS={max_rms:.4f}.")
        else:
            print(f"Chunks captured ({len(chunks)}), but signal is silent (peak RMS={max_rms:.6f}). Check system volume/output device.")

    elif args.command == "test-ai":
        print(_BANNER)
        provider = args.provider
        print(f"Testing AI provider: {provider}")
        response_service = ResponseService(provider=provider)
        response = response_service.generate_response("Hello, this is a test prompt.", "")
        print("Response:")
        print(response)

    elif args.command == "tutor":
        provider = getattr(args, "provider", Settings.DEFAULT_AI_PROVIDER)
        controller = TutorController(provider=provider)
        controller.start()

if __name__ == "__main__":
    main()
