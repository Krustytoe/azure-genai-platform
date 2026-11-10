import pytest

from ragapi.redaction import redact


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("mail jane.doe@example.com today", "email"),
        ("my ssn is 123-45-6789", "ssn"),
        ("card 4111 1111 1111 1111 please", "card"),
        ("key AKIAIOSFODNN7EXAMPLE leaked", "aws_key"),
        ("call (555) 123-4567 now", "phone"),
        ("call +1 555-123-4567 now", "phone"),
    ],
)
def test_redacts_known_entities(text: str, label: str) -> None:
    result = redact(text)
    assert f"[REDACTED_{label.upper()}]" in result.text
    assert result.counts[label] == 1


def test_card_requires_valid_luhn() -> None:
    # 16 digits that fail the Luhn check are left alone (order numbers, IDs ...).
    result = redact("order 1234 5678 9012 3456 shipped")
    assert result.text == "order 1234 5678 9012 3456 shipped"
    assert not result.counts


def test_invalid_ssn_ranges_are_ignored() -> None:
    assert redact("000-12-3456 and 666-12-3456").counts["ssn"] == 0


def test_clean_text_is_unchanged() -> None:
    text = "What is the domestic meal per diem for 2026?"
    assert redact(text).text == text
