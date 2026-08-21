import logging
import numpy as np
from faster_whisper import WhisperModel

from config.settings import Settings
from utils.audio_helpers import AudioHelpers

logger = logging.getLogger(__name__)

class TranscriptionService:
    def __init__(self, model_size: str = Settings.WHISPER_MODEL_SIZE, language: str = Settings.WHISPER_LANGUAGE, compute_type: str = Settings.WHISPER_COMPUTE_TYPE, beam_size: int = Settings.WHISPER_BEAM_SIZE, device: str = Settings.WHISPER_DEVICE):
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
        return AudioHelpers.pcm_to_float32(audio_data, sample_rate, channels)

    def is_speech(self, audio_data: bytes, sample_rate: int = 16000, channels: int = 1) -> bool:
        audio_array = self.audio_bytes_to_ndarray(audio_data, sample_rate, channels)
        rms = AudioHelpers.calculate_rms(audio_array)
        # 0.01 is a solid default threshold for normalized float32 audio [-1.0, 1.0]
        # (Settings.SILENCE_THRESHOLD was originally designed for 16-bit PCM scale, i.e., 500)
        return rms > 0.01

    def transcribe(self, accumulated_payloads) -> str:
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
        return " ".join(text_parts).strip()

    def stop(self) -> None:
        logger.info("Transcription service stopped.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # local test
