import pytest

from blankslate.audio.io import Speaker
from blankslate.tts.engine import SapiEngine, build_tts_engine


@pytest.fixture
def speaker() -> Speaker:
    return Speaker()


def test_factory_none_engine(speaker) -> None:
    engine = build_tts_engine("none", speaker, voice="af_heart", speed=1.0)
    assert engine.name == "none"
    engine.speak("hello")  # no-op, must not raise


def test_factory_unknown_engine_raises(speaker) -> None:
    with pytest.raises(ValueError):
        build_tts_engine("bogus", speaker, voice="af_heart", speed=1.0)


def test_kokoro_falls_back_to_sapi_without_extra(speaker) -> None:
    engine = build_tts_engine("kokoro", speaker, voice="af_heart", speed=1.0)
    # kokoro extra is not installed in CI; factory must degrade to SAPI
    assert isinstance(engine, SapiEngine)


def test_sapi_engine_available(speaker) -> None:
    engine = SapiEngine(speaker)
    if engine.available():
        assert engine.name == "sapi"
        engine.speak("")  # empty text is a safe no-op
