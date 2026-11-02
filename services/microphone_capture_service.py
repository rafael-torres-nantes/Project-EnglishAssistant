import logging
import threading
import time

import numpy as np
import pyaudiowpatch as pyaudio

from config.settings import Settings
from utils.audio_helpers import AudioHelpers

logger = logging.getLogger(__name__)


class MicrophoneCaptureService:
    """Grava o microfone entre um start e um stop; nunca captura o áudio do sistema."""

    _CHUNK_SECONDS = 0.1

    def __init__(self, device_index: int | None = Settings.COACH_MIC_DEVICE_INDEX, max_seconds: int = Settings.COACH_MAX_RECORDING_SECONDS):
        """
        Função de inicialização do serviço de microfone.

        Args:
            device_index: Índice do dispositivo de entrada; None usa o padrão do Windows.
            max_seconds: Duração máxima da gravação, para não crescer sem limite na memória.

        Returns:
            None
        """
        self.device_index = device_index
        self.max_seconds = max_seconds
        self.is_recording = False
        self.level = 0.0
        self.sample_rate = 0
        self.channels = 0
        self.frames = []
        self.started_at = 0.0
        self.pyaudio_instance = None
        self.stream = None
        self.thread = None

    def find_input_device(self, pyaudio_instance) -> dict:
        """
        Resolve o dispositivo de entrada e recusa dispositivos de loopback.

        Args:
            pyaudio_instance: Instância aberta do PyAudio.

        Returns:
            Informações do dispositivo de entrada.

        Raises:
            RuntimeError: Se o dispositivo for loopback ou não tiver canais de entrada.
        """
        index = self.device_index
        if index is None:
            index = pyaudio_instance.get_host_api_info_by_type(pyaudio.paWASAPI)["defaultInputDevice"]
        device = pyaudio_instance.get_device_info_by_index(index)
        if device.get("isLoopbackDevice"):
            raise RuntimeError("O ensaio aceita só microfone; dispositivo de loopback recusado.")
        if device["maxInputChannels"] < 1:
            raise RuntimeError(f"O dispositivo '{device['name']}' não tem entrada de áudio.")
        return device

    def start(self) -> str:
        """
        Abre o microfone e começa a gravar em uma thread dedicada.

        Returns:
            Nome do dispositivo em uso.

        Raises:
            RuntimeError: Se já houver gravação em andamento ou o dispositivo for inválido.
        """
        if self.is_recording:
            raise RuntimeError("Já existe uma gravação em andamento.")
        # Instância nova a cada gravação: o PyAudio só enxerga troca de dispositivo padrão ao iniciar.
        self.pyaudio_instance = pyaudio.PyAudio()
        try:
            device = self.find_input_device(self.pyaudio_instance)
            self.sample_rate = int(device["defaultSampleRate"])
            self.channels = int(device["maxInputChannels"])
            self.stream = self.pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=int(self.sample_rate * self._CHUNK_SECONDS),
                input_device_index=device["index"],
            )
        except Exception:
            self.pyaudio_instance.terminate()
            self.pyaudio_instance = None
            raise
        self.frames = []
        self.level = 0.0
        self.started_at = time.perf_counter()
        self.is_recording = True
        self.thread = threading.Thread(target=self.capture_loop, daemon=True)
        self.thread.start()
        logger.info("Microfone aberto: %s (%d Hz, %d canais)", device["name"], self.sample_rate, self.channels)
        return device["name"]

    def capture_loop(self) -> None:
        """
        Lê o microfone até o stop ou até atingir a duração máxima.

        Returns:
            None
        """
        chunk_size = int(self.sample_rate * self._CHUNK_SECONDS)
        while self.is_recording and self.elapsed_seconds() < self.max_seconds:
            try:
                data = self.stream.read(chunk_size, exception_on_overflow=False)
            except OSError as error:
                logger.error("Erro lendo o microfone: %s", error)
                break
            self.frames.append(data)
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            self.level = AudioHelpers.calculate_rms(samples)

    def elapsed_seconds(self) -> float:
        """
        Informa há quanto tempo a gravação atual começou.

        Returns:
            Segundos desde o start; 0.0 se não houver gravação.
        """
        if not self.is_recording:
            return 0.0
        return time.perf_counter() - self.started_at

    def stop(self) -> tuple[bytes, int, int]:
        """
        Fecha o microfone e devolve o áudio gravado.

        Returns:
            Tupla (PCM 16-bit, taxa de amostragem, canais).

        Raises:
            RuntimeError: Se nenhuma gravação estiver em andamento.
        """
        if not self.is_recording:
            raise RuntimeError("Nenhuma gravação em andamento.")
        self.is_recording = False
        self.thread.join(timeout=2.0)
        self.thread = None
        self.stream.stop_stream()
        self.stream.close()
        self.stream = None
        self.pyaudio_instance.terminate()
        self.pyaudio_instance = None
        self.level = 0.0
        return AudioHelpers.merge_audio_chunks(self.frames), self.sample_rate, self.channels


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    service = MicrophoneCaptureService()
    logger.info("Dispositivo: %s", service.start())
    time.sleep(2)
    audio, rate, channels = service.stop()
    logger.info("Teste local: %d bytes, %d Hz, %d canais", len(audio), rate, channels)
