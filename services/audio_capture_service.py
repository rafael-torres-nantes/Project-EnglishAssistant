import logging
import queue
import threading
import pyaudiowpatch as pyaudio

from config.settings import Settings

logger = logging.getLogger(__name__)

class AudioCaptureService:
    """Captura o áudio de saída do sistema via WASAPI Loopback, em thread separada."""

    def __init__(self, sample_rate: int = Settings.AUDIO_SAMPLE_RATE, channels: int = Settings.AUDIO_CHANNELS, chunk_duration: float = Settings.AUDIO_CHUNK_DURATION_SECONDS):
        """
        Função de inicialização do serviço de captura de áudio.

        Args:
            sample_rate (int): Taxa de amostragem inicial (recalculada para a do dispositivo real).
            channels (int): Número de canais inicial (recalculado para o do dispositivo real).
            chunk_duration (float): Duração de cada chunk de áudio, em segundos.

        Returns:
            None
        """
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
        """
        Permite usar a classe como context manager (`with AudioCaptureService() as svc:`).

        Returns:
            AudioCaptureService: A própria instância.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Encerra a captura e libera os recursos do PyAudio ao sair do context manager.

        Returns:
            None
        """
        self.stop()
        self.pyaudio_instance.terminate()

    def find_loopback_device(self) -> dict:
        """
        Localiza o dispositivo de loopback WASAPI correspondente à saída de áudio padrão.

        Returns:
            dict: Informações do dispositivo de loopback (nome, índice, taxa de amostragem, canais).

        Raises:
            RuntimeError: Se nenhum dispositivo de loopback correspondente for encontrado.
        """
        wasapi_info = self.pyaudio_instance.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = self.pyaudio_instance.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
        
        if not default_speakers["isLoopbackDevice"]:
            for loopback in self.pyaudio_instance.get_loopback_device_info_generator():
                if default_speakers["name"] in loopback["name"]:
                    return loopback
            raise RuntimeError("Dispositivo de loopback WASAPI não encontrado para os alto-falantes padrão.")
        
        return default_speakers

    def capture_loop(self) -> None:
        """
        Laço de captura contínua de áudio, executado na thread dedicada.

        Abre o stream WASAPI Loopback e enfileira chunks de áudio até que
        `is_capturing` seja desativado por `stop()`.

        Returns:
            None
        """
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
        """
        Inicia a captura de áudio em uma thread daemon separada.

        Returns:
            None
        """
        if self.is_capturing:
            return
        logger.info("Iniciando captura de áudio...")
        self.is_capturing = True
        self.capture_thread = threading.Thread(target=self.capture_loop, daemon=True)
        self.capture_thread.start()

    def stop(self) -> None:
        """
        Para a captura de áudio e aguarda a thread de captura encerrar.

        Returns:
            None
        """
        if not self.is_capturing:
            return
        logger.info("Parando captura de áudio...")
        self.is_capturing = False
        if self.capture_thread is not None:
            self.capture_thread.join(timeout=2.0)
            self.capture_thread = None

    def get_audio_chunk(self) -> bytes | None:
        """
        Retira o próximo chunk de áudio da fila de captura.

        Returns:
            bytes | None: Tupla (bytes, sample_rate, channels) do próximo chunk;
                None se nenhum chunk chegar dentro de 1 segundo.
        """
        try:
            return self.audio_queue.get(timeout=1.0)
        except queue.Empty:
            return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); # local test
