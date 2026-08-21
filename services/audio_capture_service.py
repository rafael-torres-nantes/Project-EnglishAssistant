import logging
import queue
import threading
import pyaudiowpatch as pyaudio

from config.settings import Settings

logger = logging.getLogger(__name__)

class AudioCaptureService:
    def __init__(self, sample_rate: int = Settings.AUDIO_SAMPLE_RATE, channels: int = Settings.AUDIO_CHANNELS, chunk_duration: float = Settings.AUDIO_CHUNK_DURATION_SECONDS):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_duration = chunk_duration
        self.chunk_size = int(self.sample_rate * self.chunk_duration)
        self.pyaudio_instance = pyaudio.PyAudio()
        self.audio_queue = queue.Queue()
        self.is_capturing = False
        self.capture_thread = None
        self.stream = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        self.pyaudio_instance.terminate()

    def find_loopback_device(self) -> dict:
        wasapi_info = self.pyaudio_instance.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = self.pyaudio_instance.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
        
        if not default_speakers["isLoopbackDevice"]:
            for loopback in self.pyaudio_instance.get_loopback_device_info_generator():
                if default_speakers["name"] in loopback["name"]:
                    return loopback
            raise RuntimeError("Dispositivo de loopback WASAPI não encontrado para os alto-falantes padrão.")
        
        return default_speakers

    def capture_loop(self) -> None:
        try:
            device = self.find_loopback_device()
            # Must use device's exact native settings for WASAPI Loopback to avoid error -9997
            self.sample_rate = int(device["defaultSampleRate"])
            self.channels = device["maxInputChannels"]
            self.chunk_size = int(self.sample_rate * self.chunk_duration)
            
            logger.info("Dispositivo WASAPI: %s (%d Hz, %d channels)", device["name"], self.sample_rate, self.channels)

            self.stream = self.pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                input_device_index=device["index"]
            )
            
            while self.is_capturing:
                try:
                    data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                    # Pass tuple with metadata so downstream services can resample
                    self.audio_queue.put((data, self.sample_rate, self.channels))
                except Exception as e:
                    logger.error(f"Erro na captura de áudio: {e}")
                    
        except Exception as e:
            logger.error(f"Falha ao iniciar dispositivo de captura: {e}")
        finally:
            if self.stream is not None:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None

    def start(self) -> None:
        if self.is_capturing:
            return
        logger.info("Iniciando captura de áudio...")
        self.is_capturing = True
        self.capture_thread = threading.Thread(target=self.capture_loop, daemon=True)
        self.capture_thread.start()

    def stop(self) -> None:
        if not self.is_capturing:
            return
        logger.info("Parando captura de áudio...")
        self.is_capturing = False
        if self.capture_thread is not None:
            self.capture_thread.join(timeout=2.0)
            self.capture_thread = None

    def get_audio_chunk(self) -> bytes | None:
        try:
            return self.audio_queue.get(timeout=1.0)
        except queue.Empty:
            return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); # local test
