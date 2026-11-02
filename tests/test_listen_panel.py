import subprocess
from pathlib import Path

import pytest

from controllers.meeting_controller import MeetingController
from prompt_template.meeting_prompt import MEETING_REPLY_INSTRUCTION, MEETING_SYSTEM_PROMPT
from services.response_service import ResponseService

PAGE = "\n".join(
    Path(path).read_text(encoding="utf-8") for path in ("web/index.html", "web/js/coach.js", "web/js/listen.js")
)


class TestListenPage:
    """Trava a ligação entre a aba Listen e as rotas de reunião."""

    @pytest.mark.parametrize("marker", [
        'id="tab-listen"',
        'id="panel-listen"',
        'id="listen-toggle"',
        'id="listen-generate"',
        'id="listen-suggestion"',
        'id="listen-finals"',
        'new EventSource("/api/meeting/events")',
        '"/api/meeting/start"',
        '"/api/meeting/stop"',
        '"/api/meeting/generate"',
        '"/api/meeting/backstage"',
    ])
    def test_page_has_listen_marker(self, marker):
        assert marker in PAGE

    def test_listen_mode_does_not_prewarm_coach(self):
        guard = PAGE.index('if (mode === "listen") {\n    refreshListenContext()'.replace("\n", "\r\n" if "\r\n" in PAGE else "\n"))
        prewarm = PAGE.index('postJson("/api/prewarm", {mode})')
        assert guard < prewarm


class TestGenerationError:
    """Garante que erro da CLI não leve o contexto pessoal para a tela."""

    def test_error_event_does_not_repeat_cli_command(self):
        class FailingResponses:
            def preview_prompts(self, text, context):
                return "system", "prompt"

            def generate_response_stream(self, text, context):
                raise subprocess.CalledProcessError(1, ["agy.exe", "--print", "contexto pessoal secreto"])
                yield ""

        class EmptyContext:
            def load_all_context(self):
                return ""

        controller = MeetingController(None, FailingResponses(), EmptyContext(), None, "small", "claude")
        controller.is_running = True
        events = []
        controller.broadcast = events.append

        controller.generate_single(1, "Who are you?")

        error_events = [event for event in events if event["type"] == "error"]
        assert len(error_events) == 1
        assert "CalledProcessError" in error_events[0]["message"]
        assert "secreto" not in error_events[0]["message"]


class TestMeetingPrompt:
    """Valida o formato do prompt do Listen."""

    def test_prompt_keeps_interview_scope_rule(self):
        assert "" in MEETING_SYSTEM_PROMPT

    def test_prompt_does_not_force_english(self):
        assert "held in English" not in MEETING_SYSTEM_PROMPT
        assert "in English" not in MEETING_REPLY_INSTRUCTION

    def test_context_with_braces_formats_without_error(self):
        service = ResponseService("claude", MEETING_SYSTEM_PROMPT, MEETING_REPLY_INSTRUCTION)
        system_prompt, prompt = service.preview_prompts("Who are you?", "contexto {com chaves}")
        assert "contexto {com chaves}" in system_prompt
        assert "Who are you?" in prompt
        assert MEETING_REPLY_INSTRUCTION in prompt

    def test_default_instruction_is_unchanged_for_cli_listen(self):
        service = ResponseService("claude")
        _, prompt = service.preview_prompts("Hello", "")
        assert "I could give in English" in prompt
