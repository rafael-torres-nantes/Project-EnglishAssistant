import numpy as np
import pytest

from utils.audio_helpers import AudioHelpers


def _int16_bytes(values: list[int]) -> bytes:
    return np.array(values, dtype=np.int16).tobytes()


def test_calculate_rms_silence_is_zero():
    silence = np.zeros(100, dtype=np.float32)
    assert AudioHelpers.calculate_rms(silence) == 0.0


def test_calculate_rms_empty_array_is_zero():
    assert AudioHelpers.calculate_rms(np.array([], dtype=np.float32)) == 0.0


def test_calculate_rms_none_is_zero():
    assert AudioHelpers.calculate_rms(None) == 0.0


def test_calculate_rms_constant_signal():
    signal = np.full(100, 0.5, dtype=np.float32)
    assert AudioHelpers.calculate_rms(signal) == pytest.approx(0.5)


def test_pcm_to_float32_mono_no_resample():
    data = _int16_bytes([0, 16384, -16384, 32767])
    result = AudioHelpers.pcm_to_float32(data, original_sample_rate=16000, channels=1)
    assert result.dtype == np.float32
    assert result[0] == pytest.approx(0.0)
    assert result[1] == pytest.approx(0.5, abs=1e-3)
    assert result[2] == pytest.approx(-0.5, abs=1e-3)


def test_pcm_to_float32_stereo_averages_channels():
    # Left=32767 (max), Right=0 -> average ~0.5
    data = _int16_bytes([32767, 0])
    result = AudioHelpers.pcm_to_float32(data, original_sample_rate=16000, channels=2)
    assert len(result) == 1
    assert result[0] == pytest.approx(0.5, abs=1e-3)


def test_pcm_to_float32_resamples_when_rate_differs():
    data = _int16_bytes([0] * 480)
    result = AudioHelpers.pcm_to_float32(data, original_sample_rate=48000, channels=1)
    # 480 samples a 48000Hz equivalem a 160 samples a 16000Hz
    assert len(result) == 160


def test_merge_audio_chunks_concatenates_bytes():
    chunks = [b"abc", b"def", b""]
    assert AudioHelpers.merge_audio_chunks(chunks) == b"abcdef"


def test_format_duration_formats_minutes_and_seconds():
    assert AudioHelpers.format_duration(75) == "01:15"
    assert AudioHelpers.format_duration(5) == "00:05"
