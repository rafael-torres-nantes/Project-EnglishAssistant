import http.client
import json
import threading
from typing import Iterator

import pytest

from controllers.coach_web_controller import CoachWebController


class FakeCoach:
    """Simula o CoachController para os testes de integração HTTP."""

    def __init__(self):
        self.started = []
        self.is_recording = False

    def recording_state(self) -> dict:
        return {"recording": self.is_recording, "level": 0.0, "seconds": 0.0}

    def prewarm(self, mode: str) -> None:
        pass

    def load_script(self, text: str) -> list[dict]:
        return [{"title": "Parte 1", "text": text}]

    def start_recording(self, mode: str, language, part_index, target_language: str = "same") -> str:
        self.started.append(mode)
        self.is_recording = True
        return "Microfone Teste"

    def stop_and_review(self) -> Iterator[dict]:
        self.is_recording = False
        yield {"event": "done"}

    def stop(self) -> None:
        self.is_recording = False


class FakeMeeting:
    """Simula o MeetingController para os testes de integração HTTP."""

    def __init__(self, start_error: bool = False):
        self.is_running = False
        self.start_error = start_error
        self.start_called = 0
        self.stop_called = 0
        self.generate_called = 0

    def start(self) -> str:
        if self.start_error:
            raise RuntimeError("Dispositivo loopback ausente.")
        if self.is_running:
            raise RuntimeError("Meeting session already running")
        self.is_running = True
        self.start_called += 1
        return "Mock Speakers (WASAPI)"

    def stop(self) -> None:
        self.is_running = False
        self.stop_called += 1

    def generate_now(self) -> None:
        if not self.is_running:
            raise RuntimeError("Nenhuma transcrição final disponível.")
        self.generate_called += 1

    def state(self) -> dict:
        return {
            "running": self.is_running,
            "capturing": self.is_running,
            "device": "Mock Speakers (WASAPI)" if self.is_running else None,
        }

    def backstage(self) -> dict:
        return {
            "provider": "claude",
            "model": "haiku",
            "whisper_model": "small",
            "language": "en",
            "system_prompt_template": "Prompt template",
            "context_files": [],
            "last_request": None,
        }

    def events(self) -> Iterator[dict]:
        yield {
            "type": "snapshot",
            "running": self.is_running,
            "capturing": self.is_running,
            "device": "Mock Speakers (WASAPI)",
            "finals": [],
            "suggestion": None,
        }


@pytest.fixture
def web_server():
    coach = FakeCoach()
    meeting = FakeMeeting()
    web = CoachWebController(coach, port=0, meeting=meeting)
    thread = threading.Thread(target=web.server.serve_forever, daemon=True)
    thread.start()
    yield web.server.server_address[1], coach, meeting
    web.server.shutdown()
    web.server.server_close()


@pytest.fixture
def web_server_no_meeting():
    coach = FakeCoach()
    web = CoachWebController(coach, port=0, meeting=None)
    thread = threading.Thread(target=web.server.serve_forever, daemon=True)
    thread.start()
    yield web.server.server_address[1], coach
    web.server.shutdown()
    web.server.server_close()


def http_call(port: int, method: str, path: str, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    default_headers = {"Content-Type": "application/json"}
    if headers:
        default_headers.update(headers)
    payload = json.dumps(body or {}) if method == "POST" else None
    connection.request(method, path, payload, default_headers)
    response = connection.getresponse()
    data = response.read().decode("utf-8")
    connection.close()
    return response, data


class TestMeetingWeb:
    """Valida as rotas HTTP, segurança de origem e bloqueios concorrentes da reunião."""

    MEETING_ROUTES = [
        ("POST", "/api/meeting/start"),
        ("POST", "/api/meeting/stop"),
        ("POST", "/api/meeting/generate"),
        ("GET", "/api/meeting/state"),
        ("GET", "/api/meeting/events"),
        ("GET", "/api/meeting/backstage"),
    ]

    def test_untrusted_host_and_origin_return_403(self, web_server):
        port, coach, meeting = web_server

        for method, route in self.MEETING_ROUTES:
            # 1. Host falso / DNS rebinding
            resp_host, data_host = http_call(port, method, route, headers={"Host": "malicious.example"})
            assert resp_host.status == 403, f"Rota {route} deveria retornar 403 para Host falso"
            assert "Origem não permitida." in data_host

            # 2. Origin externa / cross-origin não autorizado
            resp_orig, data_orig = http_call(port, method, route, headers={"Origin": "https://malicious.example"})
            assert resp_orig.status == 403, f"Rota {route} deveria retornar 403 para Origin externa"
            assert "Origem não permitida." in data_orig

        # Nenhuma captura ou gravação deve ter sido iniciada
        assert meeting.start_called == 0
        assert coach.started == []

    def test_meeting_none_returns_503(self, web_server_no_meeting):
        port, _ = web_server_no_meeting

        for method, route in self.MEETING_ROUTES:
            resp, data = http_call(port, method, route)
            assert resp.status == 503, f"Rota {route} deveria retornar 503 quando meeting for None"
            assert "Meeting service not configured" in data

    def test_cross_conflict_coach_and_meeting(self, web_server):
        port, coach, meeting = web_server

        # Cenário 1: Microfone do treinador está gravando -> POST /api/meeting/start retorna 409
        coach.is_recording = True
        resp, data = http_call(port, "POST", "/api/meeting/start")
        assert resp.status == 409
        assert "Microfone do treinador está gravando." in data
        assert meeting.start_called == 0

        # Libera o treinador
        coach.is_recording = False

        # Inicia a reunião
        resp, data = http_call(port, "POST", "/api/meeting/start")
        assert resp.status == 200
        assert meeting.is_running is True

        # Cenário 2: Reunião ativa -> POST /api/record/start retorna 409 com mensagem prescrita
        resp_rec, data_rec = http_call(port, "POST", "/api/record/start", {"mode": "rehearsal"})
        assert resp_rec.status == 409
        assert "Pare a captura da reunião antes de gravar." in data_rec
        assert coach.started == []

        # Para a reunião
        http_call(port, "POST", "/api/meeting/stop")
        assert meeting.is_running is False

    def test_meeting_lifecycle_and_routes_success(self, web_server):
        port, coach, meeting = web_server

        # 1. State inicial
        resp, data = http_call(port, "GET", "/api/meeting/state")
        assert resp.status == 200
        state = json.loads(data)
        assert state["running"] is False

        # 2. Start
        resp, data = http_call(port, "POST", "/api/meeting/start")
        assert resp.status == 200
        result = json.loads(data)
        assert result["device"] == "Mock Speakers (WASAPI)"
        assert meeting.is_running is True

        # 3. Generate
        resp, data = http_call(port, "POST", "/api/meeting/generate")
        assert resp.status == 200
        assert json.loads(data)["ok"] is True
        assert meeting.generate_called == 1

        # 4. Backstage
        resp, data = http_call(port, "GET", "/api/meeting/backstage")
        assert resp.status == 200
        bs = json.loads(data)
        assert bs["provider"] == "claude"
        assert bs["model"] == "haiku"

        # 5. Events SSE
        resp, data = http_call(port, "GET", "/api/meeting/events")
        assert resp.status == 200
        assert resp.getheader("Content-Type").startswith("text/event-stream")
        assert 'data: {"type": "snapshot"' in data

        # 6. Stop
        resp, data = http_call(port, "POST", "/api/meeting/stop")
        assert resp.status == 200
        assert json.loads(data)["ok"] is True
        assert meeting.is_running is False

    def test_start_returns_409_when_meeting_start_fails(self):
        coach = FakeCoach()
        meeting = FakeMeeting(start_error=True)
        web = CoachWebController(coach, port=0, meeting=meeting)
        thread = threading.Thread(target=web.server.serve_forever, daemon=True)
        thread.start()
        port = web.server.server_address[1]

        resp, data = http_call(port, "POST", "/api/meeting/start")
        assert resp.status == 409
        assert "Dispositivo loopback ausente." in data

        web.server.shutdown()
        web.server.server_close()

    def test_generate_returns_409_when_meeting_generate_fails(self, web_server):
        port, coach, meeting = web_server
        # Meeting não está rodando -> generate_now levanta RuntimeError
        resp, data = http_call(port, "POST", "/api/meeting/generate")
        assert resp.status == 409
        assert "Nenhuma transcrição final disponível." in data
