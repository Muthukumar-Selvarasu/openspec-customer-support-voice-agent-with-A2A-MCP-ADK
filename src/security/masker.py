"""Local 16-type PII redaction. Replacements use character spans, not byte offsets."""

from __future__ import annotations

import re

PII_INFO_TYPES = [
    {"name": "EMAIL_ADDRESS"},
    {"name": "PHONE_NUMBER"},
    {"name": "CREDIT_CARD_NUMBER"},
    {"name": "US_SOCIAL_SECURITY_NUMBER"},
    {"name": "PERSON_NAME"},
    {"name": "IP_ADDRESS"},
    {"name": "DATE_OF_BIRTH"},
    {"name": "STREET_ADDRESS"},
    {"name": "PASSWORD"},
    {"name": "URL"},
    {"name": "AGE"},
    {"name": "VEHICLE_IDENTIFICATION_NUMBER"},
    {"name": "IBAN_CODE"},
    {"name": "MAC_ADDRESS"},
    {"name": "US_EMPLOYER_IDENTIFICATION_NUMBER"},
    {"name": "LOCATION_COORDINATES"},
]

_NAME_STOP = frozenset(
    {
        "order",
        "status",
        "premium",
        "processing",
        "shipped",
        "delivered",
        "cancelled",
        "returned",
    }
)

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "EMAIL_ADDRESS",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
    (
        "URL",
        re.compile(r"\bhttps?://[^\s<>]+", re.IGNORECASE),
    ),
    (
        "MAC_ADDRESS",
        re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b"),
    ),
    (
        "IP_ADDRESS",
        re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
    ),
    (
        "LOCATION_COORDINATES",
        re.compile(r"\b-?\d{1,3}\.\d{4,}\s*,\s*-?\d{1,3}\.\d{4,}\b"),
    ),
    (
        "IBAN_CODE",
        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
    ),
    (
        "CREDIT_CARD_NUMBER",
        re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"),
    ),
    (
        "US_SOCIAL_SECURITY_NUMBER",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    ),
    (
        "US_EMPLOYER_IDENTIFICATION_NUMBER",
        re.compile(r"\b\d{2}-\d{7}\b"),
    ),
    (
        "PHONE_NUMBER",
        re.compile(
            r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?!\d)"
        ),
    ),
    (
        "DATE_OF_BIRTH",
        re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b"),
    ),
    (
        "VEHICLE_IDENTIFICATION_NUMBER",
        re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"),
    ),
    (
        "STREET_ADDRESS",
        re.compile(
            r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s+){1,3}"
            r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct)\b\.?",
        ),
    ),
    (
        "PASSWORD",
        re.compile(r"\bpassword\b\s*[:=]\s*\S+", re.IGNORECASE),
    ),
    (
        "AGE",
        re.compile(r"\b\d{1,3}\s+years?\s+old\b", re.IGNORECASE),
    ),
    (
        "PERSON_NAME",
        re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b"),
    ),
]


def _stars(match: re.Match[str]) -> str:
    return "*" * len(match.group(0))


def _mask_name(match: re.Match[str]) -> str:
    words = match.group(0).split()
    if any(word.casefold() in _NAME_STOP for word in words):
        return match.group(0)
    return "*" * len(match.group(0))


def mask_sensitive_data(text: str) -> str:
    """Replace each PII span with the same number of asterisks."""
    masked = text
    for name, pattern in _PATTERNS:
        repl = _mask_name if name == "PERSON_NAME" else _stars
        masked = pattern.sub(repl, masked)
    return masked
