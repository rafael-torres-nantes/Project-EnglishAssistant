import ast
from pathlib import Path

import pytest

from controllers.coach_controller import CoachController
from prompt_template.coach_prompts import CoachPrompts

ROOT = Path(__file__).resolve().parent.parent


class FakeTranscription:
    """Devolve uma fala fixa, sem carregar o Whisper."""

    def transcribe_segments(self, samples, language, hint):
        yield {"language": "en", "text": " um the deploy failed", "words": [
            {"text": " um", "start": 0.0, "end": 0.3}, {"text": " the", "start": 0.4, "end": 0.6},
            {"text": " deploy", "start": 0.6, "end": 1.0}, {"text": " failed", "start": 1.0, "end": 1.4},
        ]}


class SilentTranscription:
    """Simula áudio sem fala."""

    def transcribe_segments(self, samples, language, hint):
        return iter(())


class FakeAi:
    """Registra os pedidos e responde em dois pedaços."""

    last_was_warm = True

    def __init__(self):
        self.requests = []
        self.warmed = []

    def stream(self, request, system_prompt):
        self.requests.append((request, system_prompt))
        yield "Versão "
        yield "clara"

    def prewarm(self, system_prompt):
        self.warmed.append(system_prompt)

    def stop(self):
        pass


class FakeMicrophone:
    """Simula o microfone com um segundo de áudio."""

    is_recording = False
    level = 0.0

    def start(self):
        self.is_recording = True
        return "Microfone de teste"

    def stop(self):
        self.is_recording = False
        return b"\x10\x00" * 16000, 16000, 1

    def elapsed_seconds(self):
        return 0.0


class TestCoachController:
    """Valida o fluxo do treinador e os limites do que ele pode fazer."""

    @staticmethod
    def build(tmp_path, transcription=None):
        return CoachController(transcription or FakeTranscription(), FakeAi(), FakeMicrophone(), latency_log=tmp_path / "latency.jsonl")

    def test_feedback_only_arrives_after_stop(self, tmp_path):
        coach = self.build(tmp_path)
        coach.start_recording("rehearsal")
        assert coach.ai.requests == []
        events = list(coach.stop_and_review())
        kinds = [event["event"] for event in events]
        assert kinds.index("transcript") < kinds.index("analysis") < kinds.index("ai") < kinds.index("latency")
        assert kinds[-1] == "done"

    def test_records_every_stage_without_speech_text(self, tmp_path):
        coach = self.build(tmp_path)
        coach.start_recording("rehearsal")
        list(coach.stop_and_review())
        saved = (tmp_path / "latency.jsonl").read_text(encoding="utf-8")
        for stage in ("capture_closed", "audio_ready", "first_transcript", "transcript_done", "analysis_done", "ai_request_sent", "ai_first_word", "ai_done"):
            assert stage in saved
        assert "deploy" not in saved

    def test_silence_reports_error_without_calling_ai(self, tmp_path):
        coach = self.build(tmp_path, SilentTranscription())
        coach.start_recording("rehearsal")
        events = list(coach.stop_and_review())
        assert events[-1] == {"event": "error", "message": "Nenhuma fala detectada no microfone."}
        assert coach.ai.requests == []

    def test_presentation_requires_valid_part_before_opening_microphone(self, tmp_path):
        coach = self.build(tmp_path)
        with pytest.raises(ValueError):
            coach.start_recording("presentation", part_index=0)
        assert coach.microphone.is_recording is False

    def test_presentation_request_contains_chosen_part(self, tmp_path):
        coach = self.build(tmp_path)
        coach.load_script("# Um\nprimeira\n# Dois\nsegunda")
        coach.start_recording("presentation", part_index=1)
        list(coach.stop_and_review())
        request = coach.ai.requests[0][0]
        assert "segunda" in request and "primeira" not in request

    def test_manager_from_text_uses_target_language(self, tmp_path):
        coach = self.build(tmp_path)
        list(coach.phrases_from_text("preciso de mais prazo", "en"))
        assert "English" in coach.ai.requests[0][0]

    def test_invalid_language_never_opens_microphone(self, tmp_path):
        coach = self.build(tmp_path)
        with pytest.raises(ValueError):
            coach.start_recording("rehearsal", language="fr")
        assert coach.microphone.is_recording is False

    def test_stop_without_recording_returns_error(self, tmp_path):
        events = list(self.build(tmp_path).stop_and_review())
        assert events[0]["event"] == "error"


class TestCoachBoundaries:
    """Trava o limite do projeto: o treinador usa só microfone e não recebe contexto externo."""

    FILES = ["controllers/coach_controller.py", "controllers/coach_web_controller.py", "services/microphone_capture_service.py", "services/warm_claude_service.py", "services/speech_analysis_service.py", "services/presentation_script_service.py", "prompt_template/coach_prompts.py"]

    @staticmethod
    def imported_modules(path):
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.add(node.module)
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
        return names

    @pytest.mark.parametrize("path", FILES)
    def test_does_not_use_system_audio_or_context_files(self, path):
        modules = self.imported_modules(path)
        assert "services.audio_capture_service" not in modules
        assert "services.context_service" not in modules

    def test_modes_are_exactly_the_three_allowed(self):
        assert set(CoachPrompts.modes()) == {"rehearsal", "manager", "presentation"}

    def test_warm_command_never_uses_bare_or_api_key(self):
        source = (ROOT / "services/warm_claude_service.py").read_text(encoding="utf-8")
        assert "--bare" not in source
        assert "ANTHROPIC_API_KEY" not in source
