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
    """Constantes de configuração e variáveis de ambiente do projeto."""

    DEFAULT_AI_PROVIDER = os.environ.get("AI_PROVIDER", "claude")
    DEFAULT_CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "haiku")
    DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-high")
    DEFAULT_TIMEOUT = 180
    DEFAULT_BUDGET_USD = 0.50
    STREAMING = os.environ.get("STREAMING", "False").strip().lower() == "true"
    AUDIO_SAMPLE_RATE = 16000
    AUDIO_CHANNELS = 1
    AUDIO_CHUNK_DURATION_SECONDS = 0.5
    # Threshold para RMS de audio normalizado float32 [-1.0, 1.0].
    SPEECH_RMS_THRESHOLD = 0.01
    SILENCE_TIMEOUT_SECONDS = float(os.environ.get("SILENCE_TIMEOUT_SECONDS", "2.5"))
    # Janela usada só na transcricao PARCIAL (streaming) para evitar reprocessar o
    # audio inteiro da fala a cada ciclo de 1s; a transcricao FINAL sempre usa o
    # buffer completo acumulado desde o inicio da fala.
    PARTIAL_TRANSCRIBE_WINDOW_SECONDS = float(os.environ.get("PARTIAL_TRANSCRIBE_WINDOW_SECONDS", "8.0"))
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
        """
        Força a codificação UTF-8 na saída padrão e de erro no Windows.

        Returns:
            None
        """
        if sys.platform == "win32":
            if isinstance(sys.stdout, io.TextIOWrapper):
                sys.stdout.reconfigure(encoding="utf-8")
            if isinstance(sys.stderr, io.TextIOWrapper):
                sys.stderr.reconfigure(encoding="utf-8")

    @staticmethod
    def setup_cuda_dll_path() -> None:
        """
        Adiciona os diretórios de DLL do CUDA (cuBLAS/cuDNN) ao PATH no Windows.

        Necessário em qualquer entrypoint que use faster-whisper com device="cuda":
        as DLLs de `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12` ficam dentro
        de site-packages e não entram no PATH do processo sozinhas.

        Returns:
            None
        """
        if os.name != 'nt':
            return
        for path in sys.path:
            if 'site-packages' in path:
                for pkg in ['cublas', 'cudnn', 'cuda_nvrtc']:
                    dll_dir = os.path.join(path, 'nvidia', pkg, 'bin')
                    if os.path.exists(dll_dir):
                        os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
                        try:
                            os.add_dll_directory(dll_dir)
                        except AttributeError:
                            pass

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # local test
    Settings.force_utf8_console()
    logger.info("Configuracoes carregadas com sucesso.")
    logger.info("Provider: %s", Settings.DEFAULT_AI_PROVIDER)
    logger.info("Claude Model: %s", Settings.DEFAULT_CLAUDE_MODEL)
    logger.info("Gemini Model: %s", Settings.DEFAULT_GEMINI_MODEL)
