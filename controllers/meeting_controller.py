import logging
import queue
import threading
import time
from pathlib import Path
from typing import Iterator

from config.settings import Settings
from utils.audio_helpers import AudioHelpers

logger = logging.getLogger(__name__)


class MeetingController:
    """Orquestra a captura de áudio WASAPI loopback, transcrição contínua e sugestões de IA para reuniões."""

    def __init__(
        self,
        transcription,
        response_service,
        context_service,
        audio_factory,
        whisper_model_name: str,
        provider: str,
    ):
        """Inicializa o controlador de reuniões de trabalho.

        Args:
            transcription: Serviço de transcrição Whisper com `transcribe` e `is_speech`.
            response_service: Serviço de geração de resposta com `generate_response_stream` e `preview_prompts`.
            context_service: Serviço de contexto com `list_files`, `load_file` e `load_all_context`.
            audio_factory: Fábrica que instancia novo `AudioCaptureService`.
            whisper_model_name: Nome do modelo Whisper em uso.
            provider: Provedor de inteligência artificial ("claude" ou "gemini").

        Returns:
            None
        """
        self.transcription = transcription
        self.response_service = response_service
        self.context_service = context_service
        self.audio_factory = audio_factory
        self.whisper_model_name = whisper_model_name
        self.provider = provider.lower() if isinstance(provider, str) else str(provider)

        self.is_running = False
        self._device_name = None
        self._audio = None

        self._finals = []
        self._final_counter = 0
        self._current_suggestion = None
        self._suggestion_counter = 0
        self._last_request = None

        self._subscribers = []
        self._subscribers_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._stop_lock = threading.Lock()

        # Controle de buffer de fala para concorrência
        self._block_lock = threading.Lock()
        self._accumulated_audio = []
        self._is_speaking = False
        self._silence_frames = 0

        # Controle de geração assíncrona com pendente único
        self._pending_lock = threading.Lock()
        self._pending_generation = None
        self._active_generator = None
        self._generation_worker_thread = None

        self._process_thread = None
        self._watchdog_thread = None

    @property
    def is_capturing(self) -> bool:
        """Verifica se a captura de áudio WASAPI está ativamente em execução.

        Returns:
            True se a thread de captura estiver viva e o stream PyAudio aberto.
        """
        if not self.is_running or self._audio is None:
            return False
        capture_thread = getattr(self._audio, "capture_thread", None)
        stream = getattr(self._audio, "stream", None)
        return bool(capture_thread and capture_thread.is_alive() and stream is not None)

    def state(self) -> dict:
        """Informa o estado operacional atual da sessão de reunião.

        Returns:
            Dicionário com `running`, `capturing` e `device`.
        """
        return {
            "running": self.is_running,
            "capturing": self.is_capturing,
            "device": self._device_name if self.is_running else None,
        }

    def start(self) -> str:
        """Inicia a sessão de reunião localizando o dispositivo e abrindo a captura.

        Returns:
            Nome do dispositivo de loopback WASAPI em uso.

        Raises:
            RuntimeError: Se a sessão já estiver ativa ou se o dispositivo loopback não for encontrado.
        """
        if self.is_running:
            raise RuntimeError("Meeting session already running")

        audio = self.audio_factory()
        device_info = audio.find_loopback_device()
        device_name = device_info.get("name", "Default WASAPI Loopback") if isinstance(device_info, dict) else str(device_info)

        self._audio = audio
        self._device_name = device_name
        self.is_running = True

        self._audio.start()

        # Aguarda brevemente a inicialização do stream de áudio
        for _ in range(50):
            if getattr(self._audio, "stream", None) is not None:
                break
            time.sleep(0.02)

        self._process_thread = threading.Thread(target=self.process_loop, daemon=True)
        self._process_thread.start()

        self._watchdog_thread = threading.Thread(target=self.watchdog_loop, daemon=True)
        self._watchdog_thread.start()

        self.broadcast({"type": "state", **self.state()})
        return self._device_name

    def stop(self) -> None:
        """Encerra a captura de áudio, interrompe a geração e fecha a sessão de reunião de forma segura.

        Returns:
            None
        """
        with self._stop_lock:
            if not self.is_running:
                return
            self.is_running = False

            with self._pending_lock:
                self._pending_generation = None
                if self._active_generator is not None:
                    try:
                        self._active_generator.close()
                    except Exception as error:
                        logger.debug("Erro ao fechar gerador ativo: %s", error)
                    self._active_generator = None

            audio_thread = getattr(self._audio, "capture_thread", None) if self._audio else None
            pyaudio_inst = getattr(self._audio, "pyaudio_instance", None) if self._audio else None

            if self._audio is not None:
                try:
                    self._audio.stop()
                except Exception as error:
                    logger.error("Erro ao parar captura de áudio: %s", error)

                if audio_thread is not None and audio_thread.is_alive():
                    logger.warning("Thread de captura WASAPI ainda ativa após timeout de stop; pyaudio_instance não terminada.")
                elif pyaudio_inst is not None:
                    try:
                        pyaudio_inst.terminate()
                    except Exception as error:
                        logger.warning("Erro ao terminar pyaudio_instance: %s", error)

            self.broadcast({"type": "state", **self.state()})

    def generate_now(self) -> None:
        """Força a finalização do bloco em andamento ou re-executa a geração sobre o último bloco final.

        Returns:
            None

        Raises:
            RuntimeError: Se a sessão não estiver ativa ou se não houver bloco de fala nem final anterior.
        """
        if not self.is_running:
            raise RuntimeError("Sessão de reunião não está em execução.")

        with self._block_lock:
            if self._is_speaking and self._accumulated_audio:
                audio_to_process = list(self._accumulated_audio)
                self._accumulated_audio = []
                self._is_speaking = False
                self._silence_frames = 0

                start_time = time.time()
                text = self.transcription.transcribe(audio_to_process)
                elapsed_time = time.time() - start_time

                if text and text.strip():
                    self._final_counter += 1
                    final_item = {"id": self._final_counter, "text": text.strip()}
                    with self._state_lock:
                        self._finals.append(final_item)
                        if len(self._finals) > Settings.MEETING_MAX_FINALS:
                            self._finals = self._finals[-Settings.MEETING_MAX_FINALS:]
                    self.broadcast({
                        "type": "final",
                        "id": final_item["id"],
                        "text": final_item["text"],
                        "transcribe_seconds": round(elapsed_time, 3),
                    })
                    self.queue_generation(final_item["id"], final_item["text"])
                return

        with self._state_lock:
            if not self._finals:
                raise RuntimeError("Nenhuma transcrição final anterior disponível para gerar sugestão.")
            last_final = self._finals[-1]

        self.queue_generation(last_final["id"], last_final["text"])

    def clear_history(self) -> None:
        """Apaga a transcrição, a sugestão e a fala em andamento, sem parar a captura.

        Returns:
            None
        """
        with self._pending_lock:
            self._pending_generation = None
        with self._block_lock:
            self._accumulated_audio = []
            self._is_speaking = False
            self._silence_frames = 0
        with self._state_lock:
            self._finals = []
            self._current_suggestion = None
            self._suggestion_counter += 1
            self._last_request = None
        self.broadcast({"type": "cleared"})

    def set_system_prompt(self, template: str) -> None:
        """Troca o prompt de sistema usado a partir da próxima sugestão.

        Args:
            template: Template com o campo `meeting_context`.

        Returns:
            None
        """
        self.response_service.system_prompt_template = template

    def queue_generation(self, final_id: int, text: str) -> None:
        """Enfileira uma solicitação de geração com vaga de pendente único substituível.

        Args:
            final_id: Identificador do bloco de transcrição final.
            text: Texto da fala transcrita.

        Returns:
            None
        """
        with self._pending_lock:
            self._pending_generation = (final_id, text)
            if self._generation_worker_thread is None or not self._generation_worker_thread.is_alive():
                self._generation_worker_thread = threading.Thread(target=self.generation_loop, daemon=True)
                self._generation_worker_thread.start()

    def generation_loop(self) -> None:
        """Laço do worker daemon de geração que consome os blocos pendentes."""
        while self.is_running:
            with self._pending_lock:
                if self._pending_generation is None:
                    break
                final_id, text = self._pending_generation
                self._pending_generation = None

            self.generate_single(final_id, text)

    def generate_single(self, final_id: int, text: str) -> None:
        """Executa uma rodada de geração via streaming com medição de latência.

        Args:
            final_id: Identificador do bloco de transcrição final associado.
            text: Texto transcrito para envio à IA.

        Returns:
            None
        """
        context = self.context_service.load_all_context()
        system_prompt, prompt = self.response_service.preview_prompts(text, context)
        self._last_request = {"system_prompt": system_prompt, "prompt": prompt}

        self._suggestion_counter += 1
        sug_id = self._suggestion_counter
        suggestion = {"id": sug_id, "text": "", "done": False}
        self._current_suggestion = suggestion

        self.broadcast({"type": "suggestion_start", "id": sug_id, "final_id": final_id})

        start_time = time.time()
        first_token_time = None
        accumulated_text = ""

        try:
            generator = self.response_service.generate_response_stream(text, context)
            with self._pending_lock:
                self._active_generator = generator

            for chunk in generator:
                # Limpar a conversa troca o contador: a resposta em andamento não volta para a tela.
                if not self.is_running or sug_id != self._suggestion_counter:
                    break
                if first_token_time is None:
                    first_token_time = time.time() - start_time
                accumulated_text += chunk
                suggestion["text"] = accumulated_text
                self.broadcast({"type": "suggestion_chunk", "id": sug_id, "text": chunk})
        except GeneratorExit:
            return
        except Exception as error:
            # O texto da exceção da CLI repete o comando inteiro, com o contexto pessoal.
            logger.error("Erro na geração de sugestão pela IA: %s", type(error).__name__)
            self.broadcast({"type": "error", "message": f"Erro gerando sugestão ({type(error).__name__}). Veja o log do servidor."})
            return
        finally:
            with self._pending_lock:
                self._active_generator = None

        if not self.is_running or sug_id != self._suggestion_counter:
            return

        total_time = time.time() - start_time
        first_token_seconds = first_token_time if first_token_time is not None else total_time
        suggestion["done"] = True
        self.broadcast({
            "type": "suggestion_done",
            "id": sug_id,
            "first_token_seconds": round(first_token_seconds, 2),
            "total_seconds": round(total_time, 2),
        })

    def process_loop(self) -> None:
        """Laço principal de leitura de áudio, detecção de fala e acionamento de transcrições."""
        max_silence_frames = max(1, int(Settings.SILENCE_TIMEOUT_SECONDS / Settings.AUDIO_CHUNK_DURATION_SECONDS))
        last_transcribe_time = 0.0
        last_level_time = 0.0

        while self.is_running:
            if not self.is_capturing:
                logger.error("Captura WASAPI finalizada de forma inesperada.")
                self.broadcast({"type": "error", "message": "Captura de áudio desconectada."})
                self.stop()
                break

            payload = self._audio.get_audio_chunk()

            with self._block_lock:
                if payload is None:
                    if not self._is_speaking:
                        time.sleep(0.02)
                        continue
                    self._silence_frames += max(1, int(1.0 / Settings.AUDIO_CHUNK_DURATION_SECONDS))

                if payload is not None:
                    chunk, sample_rate, channels = payload
                    audio_array = AudioHelpers.pcm_to_float32(chunk, sample_rate, channels)
                    rms_value = AudioHelpers.calculate_rms(audio_array)

                    now = time.time()
                    if now - last_level_time >= 0.2:
                        last_level_time = now
                        self.broadcast({"type": "level", "rms": round(float(rms_value), 4)})

                    speech_detected = self.transcription.is_speech(chunk, sample_rate, channels)
                    if speech_detected:
                        if not self._is_speaking:
                            last_transcribe_time = time.time()
                        self._is_speaking = True
                        self._silence_frames = 0
                        self._accumulated_audio.append(payload)
                    elif self._is_speaking:
                        self._silence_frames += 1
                        self._accumulated_audio.append(payload)

                if self._is_speaking:
                    utterance_seconds = len(self._accumulated_audio) * Settings.AUDIO_CHUNK_DURATION_SECONDS
                    hit_utterance_cap = utterance_seconds >= Settings.MEETING_MAX_UTTERANCE_SECONDS

                    if not (self._silence_frames > max_silence_frames or hit_utterance_cap):
                        if time.time() - last_transcribe_time >= 1.0:
                            try:
                                window_frames = max(1, int(Settings.PARTIAL_TRANSCRIBE_WINDOW_SECONDS / Settings.AUDIO_CHUNK_DURATION_SECONDS))
                                partial_slice = self._accumulated_audio[-window_frames:]
                                partial_text = self.transcription.transcribe(partial_slice)
                                if partial_text:
                                    self.broadcast({"type": "partial", "text": partial_text})
                            except Exception as error:
                                logger.error("Erro na transcrição parcial: %s", error)
                            last_transcribe_time = time.time()

                    if self._silence_frames > max_silence_frames or hit_utterance_cap:
                        audio_to_finalize = list(self._accumulated_audio)
                        self._accumulated_audio = []
                        self._silence_frames = 0
                        if not hit_utterance_cap:
                            self._is_speaking = False

                        start_time = time.time()
                        final_text = self.transcription.transcribe(audio_to_finalize)
                        elapsed_time = time.time() - start_time

                        if final_text and final_text.strip():
                            self._final_counter += 1
                            final_item = {"id": self._final_counter, "text": final_text.strip()}
                            with self._state_lock:
                                self._finals.append(final_item)
                                if len(self._finals) > Settings.MEETING_MAX_FINALS:
                                    self._finals = self._finals[-Settings.MEETING_MAX_FINALS:]
                            self.broadcast({
                                "type": "final",
                                "id": final_item["id"],
                                "text": final_item["text"],
                                "transcribe_seconds": round(elapsed_time, 3),
                            })
                            self.queue_generation(final_item["id"], final_item["text"])

            time.sleep(0.01)

    def watchdog_loop(self) -> None:
        """Laço daemon de monitoramento de assinantes órfãos e envio de heartbeat ping."""
        last_ping_time = time.time()
        zero_subscribers_start = time.time()

        while self.is_running:
            time.sleep(0.05)
            now = time.time()

            with self._subscribers_lock:
                subscriber_count = len(self._subscribers)

            if subscriber_count > 0:
                zero_subscribers_start = None
            else:
                if zero_subscribers_start is None:
                    zero_subscribers_start = now
                elif now - zero_subscribers_start >= Settings.MEETING_ORPHAN_SECONDS:
                    logger.warning("Nenhum assinante conectado por %s segundos. Encerrando sessão órfã.", Settings.MEETING_ORPHAN_SECONDS)
                    self.stop()
                    break

            if now - last_ping_time >= Settings.MEETING_HEARTBEAT_SECONDS:
                last_ping_time = now
                self.broadcast({"type": "ping"})

    def broadcast(self, event: dict) -> None:
        """Distribui um evento SSE para todas as filas individuais de assinantes.

        Args:
            event: Dicionário do evento contendo a chave `type`.

        Returns:
            None
        """
        with self._subscribers_lock:
            subscribers = list(self._subscribers)

        event_type = event.get("type", "")
        for sub_queue in subscribers:
            if event_type in ("level", "partial"):
                if sub_queue.qsize() >= 30:
                    continue
                try:
                    sub_queue.put_nowait(event)
                except queue.Full:
                    pass
            else:
                while sub_queue.full():
                    try:
                        item = sub_queue.get_nowait()
                        if item.get("type") not in ("level", "partial"):
                            sub_queue.put_nowait(item)
                            break
                    except (queue.Empty, queue.Full):
                        break
                try:
                    sub_queue.put_nowait(event)
                except queue.Full:
                    pass

    def events(self) -> Iterator[dict]:
        """Gerador SSE que transmite snapshot inicial e fluxo de eventos em tempo real.

        Yields:
            Eventos da sessão em formato de dicionário.
        """
        sub_queue = queue.Queue(maxsize=100)
        with self._subscribers_lock:
            self._subscribers.append(sub_queue)

        with self._state_lock:
            snapshot = {
                "type": "snapshot",
                "running": self.is_running,
                "capturing": self.is_capturing,
                "device": self._device_name if self.is_running else None,
                "finals": list(self._finals),
                "suggestion": dict(self._current_suggestion) if self._current_suggestion else None,
            }

        try:
            yield snapshot
            while True:
                try:
                    event = sub_queue.get(timeout=1.0)
                    yield event
                except queue.Empty:
                    if not self.is_running:
                        break
        finally:
            with self._subscribers_lock:
                if sub_queue in self._subscribers:
                    self._subscribers.remove(sub_queue)

    def backstage(self) -> dict:
        """Devolve os metadados e configurações transparentes da sessão para inspeção nos Bastidores.

        Returns:
            Dicionário com provider, model, whisper_model, language, system_prompt_template, context_files e last_request.
        """
        if self.provider == "claude":
            model_name = Settings.DEFAULT_CLAUDE_MODEL
        else:
            model_name = Settings.DEFAULT_GEMINI_MODEL

        context_files = []
        if self.context_service is not None:
            for file_name in self.context_service.list_files():
                base_name = Path(file_name).name
                content = self.context_service.load_file(file_name) or ""
                context_files.append({
                    "name": base_name,
                    "bytes": len(content.encode("utf-8")),
                    "content": content,
                })

        sys_template = getattr(self.response_service, "system_prompt_template", "")

        return {
            "provider": self.provider,
            "model": model_name,
            "whisper_model": self.whisper_model_name,
            "language": getattr(self.transcription, "language", Settings.WHISPER_LANGUAGE),
            "system_prompt_template": sys_template,
            "context_files": context_files,
            "last_request": self._last_request,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("MeetingController module loaded successfully.")
