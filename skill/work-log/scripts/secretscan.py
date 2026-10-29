"""Spot values that look like credentials before they reach a file, so they are refused instead of written."""

import re

# Prefix patterns start at a word boundary so ordinary words such as "task-..." do not match.
SECRET_PATTERNS = (
    re.compile(r"\bxox[abprs]-"),
    re.compile(r"\bgh[pousr]_"),
    re.compile(r"\bgithub_pat_"),
    re.compile(r"\bAKIA[0-9A-Z]{16}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN"),
    re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+"),
    re.compile(r"[?&](?:sig|key|secret)=[^&#\s]", re.IGNORECASE),
    # Signed URLs and API callbacks name the key in many ways (X-Amz-Signature, access_token, db_password)
    re.compile(r"[?&][\w.-]*(?:signature|token|api_?key|access_key|password)[\w.-]*=[^&#\s]", re.IGNORECASE),
)


def looks_secret(text: str) -> bool:
    return any(p.search(text) for p in SECRET_PATTERNS)


def secret_fields(value, where: str = "") -> list[str]:
    """Paths (like projects[0].items[1].text) of every string in value that looks like a credential."""
    if isinstance(value, str):
        return [where or "value"] if looks_secret(value) else []
    if isinstance(value, dict):
        return [f for k, v in value.items() for f in secret_fields(v, f"{where}.{k}" if where else str(k))]
    if isinstance(value, list):
        return [f for i, v in enumerate(value) for f in secret_fields(v, f"{where}[{i}]")]
    return []


def secret_message(fields: list[str]) -> str:
    # The value itself is never echoed: the message may end up in a log or a report.
    return f"secret-like value in {', '.join(fields)}; remove it and retry"
