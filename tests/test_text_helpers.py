from utils.text_helpers import TextHelpers


def test_clean_transcription_removes_whisper_artifacts():
    assert TextHelpers.clean_transcription("[BLANK_AUDIO]") == ""
    assert TextHelpers.clean_transcription("Hello [SILENCE] world") == "Hello world"
    assert TextHelpers.clean_transcription("(silence) Hi there") == "Hi there"


def test_clean_transcription_removes_generic_bracket_tags():
    assert TextHelpers.clean_transcription("Hello [music] world") == "Hello world"


def test_clean_transcription_collapses_whitespace():
    assert TextHelpers.clean_transcription("  Hello    world  ") == "Hello world"


def test_clean_transcription_preserves_normal_text():
    assert TextHelpers.clean_transcription("How are you doing today?") == "How are you doing today?"


def test_truncate_short_text_unchanged():
    assert TextHelpers.truncate("hello", 10) == "hello"


def test_truncate_long_text_adds_ellipsis():
    assert TextHelpers.truncate("hello world", 5) == "hello..."


def test_word_count():
    assert TextHelpers.word_count("one two three") == 3
    assert TextHelpers.word_count("") == 0


def test_format_timestamp():
    assert TextHelpers.format_timestamp(3661) == "01:01:01"
    assert TextHelpers.format_timestamp(59) == "00:00:59"


def test_sanitize_for_cli_escapes_quotes_and_newlines():
    assert TextHelpers.sanitize_for_cli('He said "hi"\nline2') == 'He said \\"hi\\" line2'
