from services.speech_analysis_service import SpeechAnalysisService


class TestSpeechAnalysis:
    """Valida muletas, velocidade e pausas sem depender de áudio."""

    @staticmethod
    def words(text: str, step: float = 0.5) -> list[dict]:
        return [{"text": f" {word}", "start": index * step, "end": index * step + step * 0.8} for index, word in enumerate(text.split())]

    def test_marks_english_fillers_and_phrases(self):
        result = SpeechAnalysisService().analyze(self.words("um I mean the deploy failed you know"), "en")
        assert result["fillers"] == {"um": 1, "i mean": 1, "you know": 1}
        assert [word["filler"] for word in result["words"]] == [True, True, True, False, False, False, True, True]

    def test_like_as_verb_is_not_filler(self):
        result = SpeechAnalysisService().analyze(self.words("I like this and it is like broken"), "en")
        assert result["fillers"] == {"like": 1}

    def test_kind_of_as_noun_phrase_is_not_filler(self):
        result = SpeechAnalysisService().analyze(self.words("a kind of database"), "en")
        assert result["fillers"] == {}

    def test_marks_portuguese_fillers(self):
        result = SpeechAnalysisService().analyze(self.words("tipo o teste falhou né"), "pt")
        assert result["fillers"] == {"tipo": 1, "né": 1}

    def test_tipo_de_is_not_filler(self):
        result = SpeechAnalysisService().analyze(self.words("esse tipo de erro"), "pt")
        assert result["fillers"] == {}

    def test_word_with_own_meaning_needs_marker_punctuation(self):
        service = SpeechAnalysisService()
        assert service.analyze(self.words("ele fez assim mesmo"), "pt")["fillers"] == {}
        assert service.analyze(self.words("então, vamos subir"), "pt")["fillers"] == {"então": 1}
        assert service.analyze(self.words("é... vamos subir"), "pt")["fillers"] == {"é": 1}

    def test_counts_repetition(self):
        result = SpeechAnalysisService().analyze(self.words("o o deploy"), "pt")
        assert result["fillers"] == {"repetição": 1}
        assert result["words"][1]["filler"] is True

    def test_speed_ignores_silence_around_speech(self):
        words = [{"text": " a", "start": 10.0, "end": 10.5}, {"text": " b", "start": 10.5, "end": 11.0}]
        result = SpeechAnalysisService().analyze(words, "en")
        assert result["speaking_seconds"] == 1.0
        assert result["words_per_minute"] == 120

    def test_counts_long_pauses(self):
        words = [{"text": " a", "start": 0.0, "end": 0.5}, {"text": " b", "start": 2.5, "end": 3.0}, {"text": " c", "start": 3.1, "end": 3.5}]
        result = SpeechAnalysisService().analyze(words, "en")
        assert result["long_pauses"] == 1
        assert result["longest_pause_seconds"] == 2.0

    def test_empty_speech_returns_zero_metrics(self):
        result = SpeechAnalysisService().analyze([], "en")
        assert result["word_count"] == 0
        assert result["words_per_minute"] == 0
