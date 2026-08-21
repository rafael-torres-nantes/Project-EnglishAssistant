import logging
import math
import struct
import numpy as np

logger = logging.getLogger(__name__)

class AudioHelpers:
    @staticmethod
    def calculate_rms(audio_array: np.ndarray) -> float:
        if audio_array is None or len(audio_array) == 0:
            return 0.0
        return float(np.sqrt(np.mean(audio_array**2)))

    @staticmethod
    def pcm_to_float32(audio_data: bytes, original_sample_rate: int = 16000, channels: int = 1) -> np.ndarray:
        pcm_array = np.frombuffer(audio_data, dtype=np.int16)
        
        # If stereo, average the channels to make it mono
        if channels == 2:
            pcm_array = pcm_array.reshape(-1, 2).mean(axis=1)
        elif channels > 2:
            pcm_array = pcm_array.reshape(-1, channels).mean(axis=1)

        float_array = pcm_array.astype(np.float32) / 32768.0

        # Resample to 16000 Hz if needed
        if original_sample_rate != 16000:
            target_length = int(len(float_array) * 16000 / original_sample_rate)
            float_array = np.interp(
                np.linspace(0.0, 1.0, target_length),
                np.linspace(0.0, 1.0, len(float_array)),
                float_array
            )
            
        return float_array.astype(np.float32)

    @staticmethod
    def merge_audio_chunks(chunks: list[bytes]) -> bytes:
        return b"".join(chunks)

    @staticmethod
    def format_duration(seconds: float) -> str:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # local test
