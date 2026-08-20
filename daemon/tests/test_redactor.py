"""Tests for the PII redactor."""

from blankslate.security.redactor import Redactor


def test_email_redacted():
    out = Redactor().redact("contact me at john.doe@example.com soon")
    assert "john.doe@example.com" not in out
    assert "<redacted_email>" in out


def test_phone_redacted():
    out = Redactor().redact("call 555 123 4567 please")
    assert "555 123 4567" not in out


def test_ssn_redacted():
    out = Redactor().redact("my ssn is 123-45-6789")
    assert "123-45-6789" not in out


def test_credit_card_redacted():
    out = Redactor().redact("card 4111 1111 1111 1111")
    assert "4111 1111 1111 1111" not in out


def test_plain_text_untouched():
    text = "what is the weather today"
    assert Redactor().redact(text) == text


def test_disabled_keeps_text():
    out = Redactor(enabled=False).redact("mail me at a@b.com")
    assert out == "mail me at a@b.com"


def test_extra_patterns():
    red = Redactor(extra_patterns=[r"\bsecret\b"])
    out = red.redact("the secret code is 42")
    assert "secret" not in out
    assert "<redacted_" in out


def test_redact_dict_values():
    data = {"email": "a@b.com", "note": "ok"}
    out = Redactor().redact_dict(data)
    assert "a@b.com" not in out["email"]
    assert out["note"] == "ok"