import http.client
import json
import threading

import pytest

from controllers.coach_web_controller import CoachWebController


class FakeCoach:
    """Registra as chamadas da API sem tocar em microfone nem CLI."""

    def __init__(self):
        self.started = []

    def recording_state(self):
        return {"recording": False, "level": 0.0, "seconds": 0.0}

    def prewarm(self, mode):
        pass

    def load_script(self, text):
        if not text:
            raise ValueError("O roteiro está vazio.")
        return [{"title": "Parte 1", "text": text}]

    def start_recording(self, mode, language, part_index, target_language):
        self.started.append(mode)
        return "Microfone"

    def stop_and_review(self):
        yield {"event": "ai", "text": "olá"}
        yield {"event": "done"}

    def phrases_from_text(self, text, target_language):
        yield {"event": "ai", "text": text}

    def stop(self):
        pass


@pytest.fixture
def server():
    coach = FakeCoach()
    web = CoachWebController(coach, port=0)
    thread = threading.Thread(target=web.server.serve_forever, daemon=True)
    thread.start()
    yield web.server.server_address[1], coach
    web.server.shutdown()
    web.server.server_close()


def call(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    final_headers = {"Content-Type": "application/json", **(headers or {})}
    connection.request(method, path, json.dumps(body or {}) if method == "POST" else None, final_headers)
    response = connection.getresponse()
    data = response.read().decode("utf-8")
    connection.close()
    return response, data


class TestCoachWeb:
    """Valida as travas de origem e o formato do streaming."""

    def test_serves_page_with_security_headers(self, server):
        port, _ = server
        response, data = call(port, "GET", "/")
        assert response.status == 200
        assert "Treinador de comunicação" in data
        assert "frame-ancestors 'none'" in response.getheader("Content-Security-Policy")

    def test_rejects_foreign_origin_on_microphone_start(self, server):
        port, coach = server
        response, _ = call(port, "POST", "/api/record/start", {"mode": "rehearsal"}, {"Origin": "https://site-malicioso.example"})
        assert response.status == 403
        assert coach.started == []

    def test_rejects_dns_rebinding_host(self, server):
        port, coach = server
        response, _ = call(port, "POST", "/api/record/start", {"mode": "rehearsal"}, {"Host": "site-malicioso.example"})
        assert response.status == 403
        assert coach.started == []

    def test_rejects_form_content_type(self, server):
        port, coach = server
        response, _ = call(port, "POST", "/api/record/start", {"mode": "rehearsal"}, {"Content-Type": "text/plain"})
        assert response.status == 415
        assert coach.started == []

    def test_accepts_same_origin(self, server):
        port, coach = server
        response, _ = call(port, "POST", "/api/record/start", {"mode": "rehearsal"}, {"Origin": f"http://127.0.0.1:{port}"})
        assert response.status == 200
        assert coach.started == ["rehearsal"]

    def test_rejects_oversized_body(self, server):
        port, _ = server
        response, _ = call(port, "POST", "/api/script", {"text": "x" * 300000})
        assert response.status == 413

    def test_invalid_script_returns_bad_request(self, server):
        port, _ = server
        response, _ = call(port, "POST", "/api/script", {"text": ""})
        assert response.status == 400

    def test_stop_streams_server_sent_events(self, server):
        port, _ = server
        response, data = call(port, "POST", "/api/record/stop")
        assert response.getheader("Content-Type").startswith("text/event-stream")
        assert 'data: {"event": "ai", "text": "olá"}' in data
