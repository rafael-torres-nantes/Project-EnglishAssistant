import http.client
import json
import threading
from typing import Any, Generator, Tuple

import pytest

from config.settings import Settings
from controllers.coach_web_controller import CoachWebController
from prompt_template.coach_prompts import CoachPrompts


class FakeCoachPrompts:
    """Dublê do controlador do treinador para testes de rotas de prompts."""

    def recording_state(self) -> dict:
        """Retorna o estado do microfone."""
        return {"recording": False, "level": 0.0, "seconds": 0.0}

    def stop(self) -> None:
        """Encerra recursos."""
        pass


@pytest.fixture
def prompts_server() -> Generator[Tuple[int, FakeCoachPrompts], None, None]:
    """Sobe um servidor de teste local numa porta livre."""
    coach = FakeCoachPrompts()
    web = CoachWebController(coach, port=0)
    thread = threading.Thread(target=web.server.serve_forever, daemon=True)
    thread.start()
    port = web.server.server_address[1]
    yield port, coach
    web.server.shutdown()
    web.server.server_close()


def send_http_request(port: int, method: str, path: str, body: Any = None, headers: dict | None = None) -> Tuple[http.client.HTTPResponse, str]:
    """Executa uma requisição HTTP direta contra a porta do servidor local.

    Args:
        port: Porta do servidor local.
        method: Verbo HTTP ("GET", "POST").
        path: Rota da requisição.
        body: Payload JSON ou string.
        headers: Cabeçalhos adicionais.

    Returns:
        Tupla com a resposta HTTP e o corpo decodificado em string.
    """
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    default_headers = {"Content-Type": "application/json"}
    if headers:
        default_headers.update(headers)
    raw_body = None
    if method == "POST":
        if isinstance(body, (dict, list)):
            raw_body = json.dumps(body)
        elif body is not None:
            raw_body = str(body)
        else:
            raw_body = "{}"
    connection.request(method, path, raw_body, default_headers)
    response = connection.getresponse()
    content = response.read().decode("utf-8")
    connection.close()
    return response, content


class TestCoachWebPrompts:
    """Valida as rotas /api/prompts e /api/prompt-preview do servidor web."""

    def test_get_prompts_structure_and_modes(self, prompts_server: Tuple[int, FakeCoachPrompts]) -> None:
        """Garante que /api/prompts retorna os prompts de sistema idênticos para todos os modos."""
        port, _ = prompts_server
        response, data = send_http_request(port, "GET", "/api/prompts")
        assert response.status == 200
        payload = json.loads(data)
        assert "modes" in payload
        assert "context" in payload
        assert "model" in payload

        for mode in CoachPrompts.modes():
            assert mode in payload["modes"]
            expected_prompt = CoachPrompts.system_prompt(mode)
            actual_prompt = payload["modes"][mode]["system_prompt"]
            assert actual_prompt == expected_prompt
            assert len(actual_prompt) == len(expected_prompt)

    def test_get_prompts_context_note_and_empty_files(self, prompts_server: Tuple[int, FakeCoachPrompts]) -> None:
        """Garante que context.files é vazio e context.note cumpre a declaração em português."""
        port, _ = prompts_server
        response, data = send_http_request(port, "GET", "/api/prompts")
        assert response.status == 200
        payload = json.loads(data)
        assert payload["context"]["files"] == []
        assert payload["context"]["note"] == "O treinador não usa arquivos de contexto: o pedido leva só métricas, transcrição, ideia ou parte do roteiro."

    def test_get_prompts_sanitization_no_secrets_or_absolute_paths(self, prompts_server: Tuple[int, FakeCoachPrompts]) -> None:
        """Assegura a ausência de chaves, tokens e caminhos absolutos no retorno de prompts."""
        port, _ = prompts_server
        response, data = send_http_request(port, "GET", "/api/prompts")
        assert response.status == 200
        forbidden_terms = ["ANTHROPIC", "API_KEY", "TOKEN", "SECRET", "C:\\", "E:\\"]
        for term in forbidden_terms:
            assert term not in data
            assert term.lower() not in data.lower() or term in ["TOKEN", "SECRET"]

    def test_get_prompts_sanitizes_tainted_settings(self, prompts_server: Tuple[int, FakeCoachPrompts], monkeypatch: pytest.MonkeyPatch) -> None:
        """Valida que valores suspeitos em Settings suprimem o bloco model."""
        port, _ = prompts_server
        monkeypatch.setattr(Settings, "COACH_MODEL", "ANTHROPIC_KEY_SECRET")
        response, data = send_http_request(port, "GET", "/api/prompts")
        assert response.status == 200
        payload = json.loads(data)
        assert payload["model"] is None

    def test_get_prompts_reports_claude_regardless_of_ai_provider(self, prompts_server: Tuple[int, FakeCoachPrompts], monkeypatch: pytest.MonkeyPatch) -> None:
        """Valida que o painel informa o provedor real do treinador, mesmo com AI_PROVIDER em Gemini."""
        port, _ = prompts_server
        monkeypatch.setattr(Settings, "DEFAULT_AI_PROVIDER", "gemini")
        monkeypatch.setattr(Settings, "COACH_MODEL", "sonnet")
        response, data = send_http_request(port, "GET", "/api/prompts")
        assert response.status == 200
        payload = json.loads(data)
        assert payload["model"] == {"provider": "claude", "name": "sonnet"}

    def test_preview_rehearsal_success(self, prompts_server: Tuple[int, FakeCoachPrompts]) -> None:
        """Valida a geração correta de preview de rehearsal via CoachPrompts."""
        port, _ = prompts_server
        analysis = {
            "word_count": 10,
            "speaking_seconds": 5.0,
            "words_per_minute": 120,
            "filler_total": 1,
            "fillers_per_minute": 12.0,
            "long_pauses": 0,
            "longest_pause_seconds": 0.0,
            "fillers": {"hum": 1},
        }
        transcript = "Olá, esta é uma fala de teste."
        response, data = send_http_request(
            port,
            "POST",
            "/api/prompt-preview",
            {"mode": "rehearsal", "transcript": transcript, "analysis": analysis},
        )
        assert response.status == 200
        payload = json.loads(data)
        expected = CoachPrompts.rehearsal_request(transcript, analysis)
        assert payload["request"] == expected

    def test_preview_manager_exact_phrase(self, prompts_server: Tuple[int, FakeCoachPrompts]) -> None:
        """Valida o preview no modo Gestor com a ideia especificada no critério 5."""
        port, _ = prompts_server
        idea = "preciso de mais dois dias"
        response, data = send_http_request(
            port,
            "POST",
            "/api/prompt-preview",
            {"mode": "manager", "idea": idea, "target_language": "same"},
        )
        assert response.status == 200
        payload = json.loads(data)
        expected = CoachPrompts.manager_request(idea, "same")
        assert payload["request"] == expected

    def test_preview_presentation_success(self, prompts_server: Tuple[int, FakeCoachPrompts]) -> None:
        """Valida o preview no modo Apresentação com roteiro e análise."""
        port, _ = prompts_server
        part = {"title": "Introdução", "text": "Texto do slide inicial."}
        transcript = "Falando sobre o slide inicial."
        analysis = {
            "word_count": 5,
            "speaking_seconds": 2.5,
            "words_per_minute": 120,
            "filler_total": 0,
            "fillers_per_minute": 0.0,
            "long_pauses": 0,
            "longest_pause_seconds": 0.0,
            "fillers": {},
        }
        response, data = send_http_request(
            port,
            "POST",
            "/api/prompt-preview",
            {"mode": "presentation", "part": part, "transcript": transcript, "analysis": analysis},
        )
        assert response.status == 200
        payload = json.loads(data)
        expected = CoachPrompts.presentation_request(part, transcript, analysis)
        assert payload["request"] == expected

    def test_preview_rejects_foreign_origin(self, prompts_server: Tuple[int, FakeCoachPrompts]) -> None:
        """Verifica recusa 403 para Foreign Origin em /api/prompt-preview."""
        port, _ = prompts_server
        response, _ = send_http_request(
            port,
            "POST",
            "/api/prompt-preview",
            {"mode": "manager", "idea": "teste"},
            headers={"Origin": "https://site-externo-malicioso.com"},
        )
        assert response.status == 403

    def test_preview_rejects_form_content_type(self, prompts_server: Tuple[int, FakeCoachPrompts]) -> None:
        """Verifica recusa 415 para Content-Type diferente de application/json."""
        port, _ = prompts_server
        response, _ = send_http_request(
            port,
            "POST",
            "/api/prompt-preview",
            "mode=manager&idea=teste",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status == 415

    def test_preview_rejects_invalid_mode(self, prompts_server: Tuple[int, FakeCoachPrompts]) -> None:
        """Verifica resposta 400 para modo desconhecido."""
        port, _ = prompts_server
        response, _ = send_http_request(
            port,
            "POST",
            "/api/prompt-preview",
            {"mode": "modo_inexistente"},
        )
        assert response.status == 400

    def test_security_headers_csp_font_src_data(self, prompts_server: Tuple[int, FakeCoachPrompts]) -> None:
        """Garante que a política Content-Security-Policy inclui font-src data: para fontes embutidas."""
        port, _ = prompts_server
        response, _ = send_http_request(port, "GET", "/")
        assert response.status == 200
        csp = response.getheader("Content-Security-Policy")
        assert csp is not None
        assert "font-src data:" in csp

    def test_security_headers_csp_no_external_font_sources(self, prompts_server: Tuple[int, FakeCoachPrompts]) -> None:
        """Garante que a política Content-Security-Policy proíbe fontes externas e CDNs."""
        port, _ = prompts_server
        response, _ = send_http_request(port, "GET", "/")
        assert response.status == 200
        csp = response.getheader("Content-Security-Policy")
        assert csp is not None
        directives = {d.strip().split()[0]: d.strip().split()[1:] for d in csp.split(";") if d.strip()}
        assert "font-src" in directives
        font_sources = directives["font-src"]
        assert font_sources == ["data:"]
        for forbidden in ["http:", "https:", "*", "fonts.googleapis.com", "fonts.gstatic.com"]:
            assert forbidden not in font_sources

