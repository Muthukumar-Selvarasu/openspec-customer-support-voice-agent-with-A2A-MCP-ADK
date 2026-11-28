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

_SALUTATIONS = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "dear",
        "thanks",
        "thank",
        "welcome",
    }
)

_NAME_STOP = frozenset(
    {
        "order",
        "orders",
        "status",
        "premium",
        "processing",
        "shipped",
        "delivered",
        "cancelled",
        "returned",
        "chair",
        "office",
        "ergonomic",
        "mouse",
        "wireless",
        "keyboard",
        "mechanical",
        "hub",
        "laptop",
        "gaming",
        "headset",
        "monitor",
        "curved",
        "batteries",
        "pack",
        "watch",
        "smart",
        "shoes",
        "running",
        "desk",
        "skincare",
        "gift",
        "set",
        "speaker",
        "bluetooth",
        "notebook",
        "camera",
        "lens",
        "professional",
        "coffee",
        "beans",
        "descaling",
        "kit",
        "option",
        "grade",
        "plan",
        "tier",
        "item",
        "items",
        "size",
        "type",
        "model",
        "usb",
        "gen",
        "hi",
        "hello",
        "hey",
        "dear",
        "thanks",
        "thank",
        "welcome",
    }
)

_ADDRESS_CLAUSE_STOP = _NAME_STOP | frozenset(
    {
        "please",
        "is",
        "was",
        "your",
        "and",
        "for",
        "on",
        "with",
        "we",
        "i",
        "the",
        "delivery",
        "confirm",
        "total",
        "date",
        "amount",
        "it",
        "this",
        "that",
        "here",
        "there",
        "let",
        "if",
        "would",
        "can",
        "could",
        "should",
        "will",
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
        re.compile(
            r"\b(?:dob|date\s+of\s+birth|birth\s*date|born(?:\s+on)?|birthday)\b"
            r"\s*[:=]?\s*(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b",
            re.IGNORECASE,
        ),
    ),
    (
        "VEHICLE_IDENTIFICATION_NUMBER",
        re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"),
    ),
    (
        "STREET_ADDRESS",
        re.compile(
            r"(?P<street>\b\d{1,5}\s+(?:(?:\d+(?:st|nd|rd|th)|[A-Z][a-z]+)\s+){1,3}"
            r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|"
            r"Parkway|Pkwy|Path|Way|Place|Pl|Circle|Cir|Terrace|Ter|Trail|Trl)\b\.?"
            r"(?:,?\s+(?:(?:Apt|Apartment|Suite|Ste|Unit)\s*#?|#)\s*[A-Za-z0-9-]+)?)"
            r"(?P<city_sep>,\s+(?P<city>[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?))?",
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
        re.compile(r"\b[A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+\b|[A-Z]\.?))+"),
    ),
]


def _stars(match: re.Match[str]) -> str:
    return "*" * len(match.group(0))


def _mask_address(match: re.Match[str]) -> str:
    street = match.group("street")
    city_sep = match.group("city_sep")
    city = match.group("city")
    if not city_sep or not city:
        return "*" * len(street)
    words = city.split()
    if words[0].casefold() in _ADDRESS_CLAUSE_STOP:
        return ("*" * len(street)) + city_sep
    if len(words) == 2 and words[1].casefold() in _ADDRESS_CLAUSE_STOP:
        first_part = city_sep[: city_sep.rindex(words[1])]
        trailing_ws = ""
        while first_part and first_part[-1].isspace():
            trailing_ws = first_part[-1] + trailing_ws
            first_part = first_part[:-1]
        return ("*" * (len(street) + len(first_part))) + trailing_ws + words[1]
    return "*" * len(match.group(0))


def _mask_name(match: re.Match[str]) -> str:
    full = match.group(0)
    prefix = ""
    rest = full
    while True:
        split = re.match(r"^([A-Za-z]+)(\s+)(.*)$", rest)
        if not split:
            break
        first_word, sep, tail = split.group(1), split.group(2), split.group(3)
        if first_word.casefold() in _SALUTATIONS:
            prefix += first_word + sep
            rest = tail
        else:
            break
    words = rest.split()
    if len(words) < 2:
        return full
    if any(word.rstrip(".").casefold() in _NAME_STOP for word in words):
        return full
    return prefix + ("*" * len(rest))


def mask_sensitive_data(text: str) -> str:
    """Replace each PII span with the same number of asterisks."""
    masked = text
    for name, pattern in _PATTERNS:
        if name == "PERSON_NAME":
            repl = _mask_name
        elif name == "STREET_ADDRESS":
            repl = _mask_address
        else:
            repl = _stars
        masked = pattern.sub(repl, masked)
    return masked
