import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterator

from config.settings import Settings
from prompt_template.coach_prompts import CoachPrompts

logger = logging.getLogger(__name__)


class CoachHttpHandler(BaseHTTPRequestHandler):
    """Atende a página e a API local do treinador."""

    server_version = "CoachLocal"
    sys_version = ""
    # Prazo do socket: um Content-Length falso não prende a thread esperando corpo que nunca chega.
    timeout = 30
    _WEB_DIR = Path(__file__).resolve().parent.parent / "web"
    _PAGE = _WEB_DIR / "index.html"
    # Lista fechada: nenhum caminho vindo do navegador chega ao disco.
    _ASSETS = {
        "/css/coach.css": ("css/coach.css", "text/css; charset=utf-8"),
        "/css/listen.css": ("css/listen.css", "text/css; charset=utf-8"),
        "/js/coach.js": ("js/coach.js", "text/javascript; charset=utf-8"),
        "/js/listen.js": ("js/listen.js", "text/javascript; charset=utf-8"),
    }
    _SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
    }

    def log_message(self, format: str, *args) -> None:
        """
        Envia o log de acesso do servidor para o logger, em nível debug.

        Args:
            format: Formato da mensagem.
            *args: Valores da mensagem.

        Returns:
            None
        """
        logger.debug(format, *args)

    def is_trusted_origin(self) -> bool:
        """
        Recusa pedido de outra origem: sem isso, qualquer site aberto no navegador poderia ligar o microfone.

        A checagem de Host cobre DNS rebinding; a de Origin cobre pedido cruzado.

        Returns:
            True se o pedido veio da própria página local.
        """
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in hosts:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{host}" for host in hosts}

    def send_payload(self, status: int, body: bytes, content_type: str) -> None:
        """
        Envia uma resposta completa com os cabeçalhos de segurança.

        Args:
            status: Código HTTP.
            body: Corpo da resposta.
            content_type: Tipo do conteúdo.

        Returns:
            None
        """
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in self._SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, payload: dict) -> None:
        """
        Envia uma resposta JSON.

        Args:
            status: Código HTTP.
            payload: Conteúdo da resposta.

        Returns:
            None
        """
        self.send_payload(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def send_events(self, events: Iterator[dict]) -> None:
        """
        Envia eventos em Server-Sent Events conforme são gerados.

        Se o navegador fechar a conexão, o gerador é encerrado e libera o processo da CLI.

        Args:
            events: Gerador de eventos.

        Returns:
            None
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        for name, value in self._SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        try:
            for event in events:
                self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8"))
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            logger.info("Navegador fechou a conexão durante o streaming.")
        finally:
            events.close()

    def discard_body(self) -> None:
        """
        Lê e descarta o corpo antes de uma resposta de recusa.

        Fechar a conexão com corpo não lido faz o Windows resetá-la, e o navegador recebe erro
        de rede em vez da resposta.

        Returns:
            None
        """
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return
        self.rfile.read(min(max(length, 0), Settings.COACH_MAX_DRAIN_BYTES))

    def read_json_body(self) -> dict | None:
        """
        Lê o corpo JSON do pedido, respondendo o erro quando ele for inválido.

        Returns:
            O corpo como dicionário; None se a resposta de erro já foi enviada.
        """
        if self.headers.get_content_type() != "application/json":
            self.discard_body()
            self.send_json(415, {"error": "Use application/json."})
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "Content-Length inválido."})
            return None
        if length < 0 or length > Settings.COACH_MAX_BODY_BYTES:
            self.discard_body()
            self.send_json(413, {"error": "Corpo do pedido grande demais."})
            return None
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self.send_json(400, {"error": "JSON inválido."})
            return None
        if not isinstance(body, dict):
            self.send_json(400, {"error": "O corpo precisa ser um objeto JSON."})
            return None
        return body

    def do_GET(self) -> None:
        """
        Atende a página e o estado do microfone.

        Returns:
            None
        """
        if not self.is_trusted_origin():
            self.send_json(403, {"error": "Origem não permitida."})
            return
        if self.path == "/":
            self.send_payload(200, self._PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if self.path in self._ASSETS:
            relative_path, content_type = self._ASSETS[self.path]
            self.send_payload(200, (self._WEB_DIR / relative_path).read_bytes(), content_type)
            return
        if self.path == "/api/listen/workspace":
            workspace = getattr(self.server, "workspace", None)
            if workspace is None:
                self.send_json(503, {"error": "Listen workspace not configured"})
                return
            self.send_json(200, workspace.workspace())
            return
        if self.path == "/api/state":
            self.send_json(200, self.server.coach.recording_state())
            return
        if self.path == "/api/prompts":
            self.send_prompts()
            return
        if self.path.startswith("/api/meeting/"):
            if getattr(self.server, "meeting", None) is None:
                self.send_json(503, {"error": "Meeting service not configured"})
                return
            if self.path == "/api/meeting/state":
                self.send_json(200, self.server.meeting.state())
                return
            if self.path == "/api/meeting/events":
                self.send_events(self.server.meeting.events())
                return
            if self.path == "/api/meeting/backstage":
                self.send_json(200, self.server.meeting.backstage())
                return
            self.send_json(404, {"error": "Rota não encontrada."})
            return
        self.send_json(404, {"error": "Rota não encontrada."})

    def send_prompts(self) -> None:
        """Devolve os prompts de sistema por modo, contexto estrito e dados do modelo.

        Returns:
            None
        """
        modes = {
            mode: {"system_prompt": CoachPrompts.system_prompt(mode)}
            for mode in CoachPrompts.modes()
        }
        forbidden = ("ANTHROPIC", "API_KEY", "TOKEN", "SECRET", "C:\\", "E:\\")
        # O treinador sempre responde pelo WarmClaudeService; AI_PROVIDER só vale para o listen e o tutor.
        provider = "claude"
        model_name = getattr(Settings, "COACH_MODEL", None)
        model_info = None
        if isinstance(provider, str) and isinstance(model_name, str):
            prov_clean = provider.strip()
            mod_clean = model_name.strip()
            if not any(f in prov_clean.upper() or f in mod_clean.upper() or f in prov_clean or f in mod_clean for f in forbidden):
                model_info = {"provider": prov_clean, "name": mod_clean}

        payload = {
            "modes": modes,
            "context": {
                "files": [],
                "note": "O treinador não usa arquivos de contexto: o pedido leva só métricas, transcrição, ideia ou parte do roteiro.",
            },
            "model": model_info,
        }
        self.send_json(200, payload)

    def do_POST(self) -> None:
        """
        Atende as ações do treinador.

        Returns:
            None
        """
        if not self.is_trusted_origin():
            self.discard_body()
            self.send_json(403, {"error": "Origem não permitida."})
            return
        if self.path.startswith("/api/meeting/"):
            if getattr(self.server, "meeting", None) is None:
                self.discard_body()
                self.send_json(503, {"error": "Meeting service not configured"})
                return
        if self.path.startswith("/api/listen/") and getattr(self.server, "workspace", None) is None:
            self.discard_body()
            self.send_json(503, {"error": "Listen workspace not configured"})
            return
        body = self.read_json_body()
        if body is None:
            return
        coach = self.server.coach
        try:
            if self.path.startswith("/api/listen/"):
                self.handle_listen(body)
                return
            if self.path == "/api/meeting/clear":
                self.server.meeting.clear_history()
                self.send_json(200, {"ok": True})
                return
            if self.path == "/api/meeting/start":
                if coach.recording_state().get("recording", False):
                    self.send_json(409, {"error": "Microfone do treinador está gravando."})
                    return
                device = self.server.meeting.start()
                self.send_json(200, {"device": device})
                return
            if self.path == "/api/meeting/stop":
                self.server.meeting.stop()
                self.send_json(200, {"ok": True})
                return
            if self.path == "/api/meeting/generate":
                self.server.meeting.generate_now()
                self.send_json(200, {"ok": True})
                return
            if self.path == "/api/prewarm":
                coach.prewarm(body.get("mode", ""))
                self.send_json(200, {"ok": True})
                return
            if self.path == "/api/script":
                self.send_json(200, {"parts": coach.load_script(str(body.get("text", "")))})
                return
            if self.path == "/api/record/start":
                meeting = getattr(self.server, "meeting", None)
                if meeting is not None and getattr(meeting, "is_running", False):
                    self.send_json(409, {"error": "Pare a captura da reunião antes de gravar."})
                    return
                device = coach.start_recording(body.get("mode", ""), body.get("language"), body.get("part_index"), body.get("target_language", "same"))
                self.send_json(200, {"device": device})
                return
            if self.path == "/api/record/stop":
                self.send_events(coach.stop_and_review())
                return
            if self.path == "/api/manager":
                self.send_events(coach.phrases_from_text(str(body.get("text", "")), body.get("target_language", "same")))
                return
            if self.path == "/api/prompt-preview":
                mode = body.get("mode")
                if not isinstance(mode, str) or mode not in CoachPrompts.modes():
                    self.send_json(400, {"error": f"Modo inválido: {mode}"})
                    return
                if mode == "rehearsal":
                    transcript = body.get("transcript")
                    analysis = body.get("analysis")
                    if not isinstance(transcript, str) or not isinstance(analysis, dict):
                        self.send_json(400, {"error": "Dados inválidos para rehearsal. 'transcript' (str) e 'analysis' (dict) são obrigatórios."})
                        return
                    try:
                        req = CoachPrompts.rehearsal_request(transcript, analysis)
                    except (KeyError, TypeError, ValueError) as err:
                        self.send_json(400, {"error": f"Erro gerando preview: {err}"})
                        return
                    self.send_json(200, {"request": req})
                    return
                if mode == "manager":
                    idea = body.get("idea")
                    if idea is None:
                        idea = body.get("text")
                    target_lang = body.get("target_language", "same")
                    if not isinstance(idea, str) or not isinstance(target_lang, str):
                        self.send_json(400, {"error": "Dados inválidos para manager. 'idea'/'text' (str) e 'target_language' (str) são obrigatórios."})
                        return
                    try:
                        req = CoachPrompts.manager_request(idea, target_lang)
                    except ValueError as err:
                        self.send_json(400, {"error": str(err)})
                        return
                    self.send_json(200, {"request": req})
                    return
                if mode == "presentation":
                    part = body.get("part")
                    transcript = body.get("transcript")
                    analysis = body.get("analysis")
                    if not isinstance(part, dict) or not isinstance(transcript, str) or not isinstance(analysis, dict):
                        self.send_json(400, {"error": "Dados inválidos para presentation. 'part' (dict), 'transcript' (str) e 'analysis' (dict) são obrigatórios."})
                        return
                    if "title" not in part or "text" not in part:
                        self.send_json(400, {"error": "A parte do roteiro deve conter 'title' e 'text'."})
                        return
                    try:
                        req = CoachPrompts.presentation_request(part, transcript, analysis)
                    except (KeyError, TypeError, ValueError) as err:
                        self.send_json(400, {"error": f"Erro gerando preview: {err}"})
                        return
                    self.send_json(200, {"request": req})
                    return
            self.send_json(404, {"error": "Rota não encontrada."})
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
        except (RuntimeError, OSError) as error:
            logger.error("Erro na API do treinador: %s", error)
            self.send_json(409, {"error": str(error)})

    def handle_listen(self, body: dict) -> None:
        """Atende a edição de contextos e do prompt da aba Listen.

        Args:
            body: Corpo JSON do pedido.

        Returns:
            None

        Raises:
            ValueError: Se o nome, o texto ou a seleção forem inválidos.
        """
        workspace = self.server.workspace
        if self.path == "/api/listen/context/read":
            self.send_json(200, workspace.read_context(body.get("name")))
            return
        if self.path == "/api/listen/context/save":
            workspace.save_context(body.get("name"), body.get("content"), body.get("previous_name"))
            self.send_json(200, workspace.workspace())
            return
        if self.path == "/api/listen/context/delete":
            workspace.delete_context(body.get("name"))
            self.send_json(200, workspace.workspace())
            return
        if self.path == "/api/listen/selection":
            workspace.set_selection(body.get("selected"))
            self.send_json(200, workspace.workspace())
            return
        if self.path in ("/api/listen/prompt/save", "/api/listen/prompt/reset"):
            if self.path.endswith("save"):
                workspace.save_prompt(body.get("instructions"))
            if self.path.endswith("reset"):
                workspace.reset_prompt()
            meeting = getattr(self.server, "meeting", None)
            if meeting is not None:
                meeting.set_system_prompt(workspace.system_prompt_template())
            self.send_json(200, workspace.workspace())
            return
        self.send_json(404, {"error": "Rota não encontrada."})


class CoachWebController:
    """Publica a interface do treinador só na interface local da máquina."""

    def __init__(self, coach, host: str = Settings.HTTP_HOST, port: int = Settings.HTTP_PORT, meeting=None, workspace=None):
        """
        Função de inicialização do servidor local.

        Args:
            coach: Instância de CoachController.
            host: Endereço de escuta.
            port: Porta de escuta; 0 escolhe uma porta livre.
            meeting: Instância opcional de MeetingController.
            workspace: Instância opcional de ListenWorkspaceService.

        Returns:
            None
        """
        self.coach = coach
        self.meeting = meeting
        self.server = ThreadingHTTPServer((host, port), CoachHttpHandler)
        self.server.daemon_threads = True
        self.server.coach = coach
        self.server.meeting = meeting
        self.server.workspace = workspace

    def url(self) -> str:
        """
        Informa o endereço da interface.

        Returns:
            URL local da página.
        """
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}/"

    def start(self) -> None:
        """
        Atende pedidos até o Ctrl+C e libera os recursos ao sair.

        Returns:
            None
        """
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Encerrando o treinador.")
        finally:
            self.stop()

    def stop(self) -> None:
        """
        Fecha o servidor, a reunião, o microfone e os processos da CLI.

        Returns:
            None
        """
        self.server.server_close()
        meeting = getattr(self.server, "meeting", None)
        if meeting is not None:
            try:
                meeting.stop()
            except Exception as error:
                logger.error("Erro ao parar reunião no encerramento: %s", error)
        self.coach.stop()
