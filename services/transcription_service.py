import logging
import numpy as np
from faster_whisper import WhisperModel

from config.settings import Settings
from utils.audio_helpers import AudioHelpers
from utils.text_helpers import TextHelpers

logger = logging.getLogger(__name__)

class TranscriptionService:
    """Transcreve áudio para texto via faster-whisper, com detecção de fala por RMS."""

    def __init__(self, model_size: str = Settings.WHISPER_MODEL_SIZE, language: str = Settings.WHISPER_LANGUAGE, compute_type: str = Settings.WHISPER_COMPUTE_TYPE, beam_size: int = Settings.WHISPER_BEAM_SIZE, device: str = Settings.WHISPER_DEVICE):
        """
        Função de inicialização do serviço de transcrição.
        
        Args:
            model_size (str): Tamanho do modelo Whisper a ser usado.
            language (str): Código de idioma para transcrição.
            compute_type (str): Tipo de computação (ex: "int8", "float16").
            beam_size (int): Tamanho do feixe para decodificação.
            device (str): Dispositivo a ser usado ("cpu" ou "cuda").

        Returns:
            None
        """

        logger.info("Carregando modelo de transcrição '%s' (device=%s)...", model_size, device)
        try:
            self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        except Exception as e:
            # Portabilidade: a GPU configurada pode não existir nesta máquina
            # (ex: repositório rodando em outro computador sem CUDA).
            logger.warning("Falha ao carregar Whisper em '%s' (%s); usando CPU/int8.", device, e)
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")
        self.language = language
        self.beam_size = beam_size

    def audio_bytes_to_ndarray(self, audio_data: bytes, sample_rate: int = 16000, channels: int = 1) -> np.ndarray:
        """
        Converte bytes de áudio PCM em array float32 normalizado.

        Args:
            audio_data (bytes): Áudio PCM 16-bit little-endian.
            sample_rate (int): Taxa de amostragem original dos dados.
            channels (int): Número de canais dos dados originais.

        Returns:
            np.ndarray: Amostras float32 em [-1.0, 1.0], mono, em 16kHz.
        """
        return AudioHelpers.pcm_to_float32(audio_data, sample_rate, channels)

    def is_speech(self, audio_data: bytes, sample_rate: int = 16000, channels: int = 1) -> bool:
        """
        Verifica se um chunk de áudio contém fala, com base no RMS do sinal.

        Args:
            audio_data (bytes): Áudio PCM 16-bit little-endian.
            sample_rate (int): Taxa de amostragem original dos dados.
            channels (int): Número de canais dos dados originais.

        Returns:
            bool: True se o RMS ultrapassar Settings.SPEECH_RMS_THRESHOLD.
        """
        audio_array = self.audio_bytes_to_ndarray(audio_data, sample_rate, channels)
        rms = AudioHelpers.calculate_rms(audio_array)
        return rms > Settings.SPEECH_RMS_THRESHOLD

    def transcribe(self, accumulated_payloads) -> str:
        """
        Transcreve uma lista de chunks de áudio acumulados em texto.

        Args:
            accumulated_payloads: Lista de tuplas (bytes, sample_rate, channels)
                capturadas na mesma taxa de amostragem e número de canais.

        Returns:
            str: Texto transcrito e limpo; string vazia se não houver fala detectada.
        """
        # Extrai os bytes, assumindo mesmo sample_rate e channels em todos os chunks
        chunks = [p[0] for p in accumulated_payloads]
        sample_rate = accumulated_payloads[0][1]
        channels = accumulated_payloads[0][2]
        
        merged_audio = AudioHelpers.merge_audio_chunks(chunks)

        if not self.is_speech(merged_audio):
            return ""

        audio_array = self.audio_bytes_to_ndarray(merged_audio, sample_rate, channels)

        segments, _ = self.model.transcribe(
            audio_array,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=True
        )

        text_parts = [segment.text for segment in segments]
        return TextHelpers.clean_transcription(" ".join(text_parts))

    def stop(self) -> None:
        """
        Finaliza o serviço de transcrição.

        Returns:
            None
        """
        logger.info("Transcription service stopped.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # local test
