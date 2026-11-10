"""Local PII redaction.

Runs before anything leaves the process (retrieval query, model prompt) and on
the model's answer. It is a second layer: the cloud guardrail is the primary
control, but redacting first means raw identifiers never reach logs, traces or
the provider at all.
"""

import re
from collections import Counter
from dataclasses import dataclass, field


def _luhn_ok(candidate: str) -> bool:
    digits = [int(c) for c in candidate if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("ssn", re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")),
    ("card", re.compile(r"\b(?:\d[ -]?){12,18}\d\b")),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("phone", re.compile(r"(?<!\w)(?:\+1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b")),
]


@dataclass
class RedactionResult:
    text: str
    counts: Counter[str] = field(default_factory=Counter)


def redact(text: str) -> RedactionResult:
    counts: Counter[str] = Counter()
    for label, pattern in _PATTERNS:

        def _sub(match: re.Match[str], label: str = label) -> str:
            if label == "card" and not _luhn_ok(match.group(0)):
                return match.group(0)
            counts[label] += 1
            return f"[REDACTED_{label.upper()}]"

        text = pattern.sub(_sub, text)
    return RedactionResult(text=text, counts=counts)
