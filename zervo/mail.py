from __future__ import annotations

import random
import re
import secrets
import time
from typing import Optional

import requests

MAIL_SITE_URL = "https://mailporary.com/ru"
MAIL_API_URL = "https://web.mailporary.com/api/v1"
# Zervo delivery: suarj / mfxis / anogz.
MAIL_DOMAINS = [
    "suarj.com",
    "mfxis.com",
    "anogz.com",
]


_CODE_LINE_RE = re.compile(r"(?m)^\s*(\d{4,8})\s*$")
_CODE_RE = re.compile(r"\b(\d{4,8})\b")


def _request_id() -> str:
    return secrets.token_hex(16)


def generate_email() -> str:
    local = "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(10))
    return f"{local}@{random.choice(MAIL_DOMAINS)}"


def authorize(session: Optional[requests.Session] = None) -> str:
    s = session or requests.Session()
    r = s.get(MAIL_SITE_URL, timeout=30)
    r.raise_for_status()
    m = re.search(r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+", r.text)
    if not m:
        raise RuntimeError("mailporary: JWT not found")
    return m.group(0)


def _headers(token: str) -> dict:
    return {
        "authorization": f"Bearer {token}",
        "x-request-id": _request_id(),
        "x-timestamp": str(int(time.time())),
    }


def inbox(session: requests.Session, token: str, mail: str) -> list:
    r = session.get(
        f"{MAIL_API_URL}/mailbox/{mail}",
        headers=_headers(token),
        timeout=30,
    )
    if r.status_code != 200:
        return []
    data = r.json()
    return data if isinstance(data, list) else []


def message_text(session: requests.Session, token: str, mail: str, msg_id: str) -> Optional[str]:
    r = session.get(
        f"{MAIL_API_URL}/mailbox/{mail}/{msg_id}",
        headers=_headers(token),
        timeout=30,
    )
    if r.status_code != 200:
        return None
    data = r.json()
    body = data.get("body") or {}
    text = body.get("text") or body.get("html") or ""
    subject = data.get("subject") or ""
    return f"{subject}\n{text}"


def extract_code(text: str) -> Optional[str]:
    if not text:
        return None
    m = _CODE_LINE_RE.search(text)
    if m:
        return m.group(1)
    m = _CODE_RE.search(text)
    return m.group(1) if m else None


def wait_code(
    session: requests.Session,
    token: str,
    mail: str,
    timeout: float = 120,
    poll: float = 4,
    seen_ids: Optional[set] = None,
) -> Optional[str]:
    seen = seen_ids if seen_ids is not None else set()
    end = time.time() + timeout
    while time.time() < end:
        for msg in inbox(session, token, mail):
            mid = str(msg.get("id", ""))
            if not mid or mid in seen:
                continue
            seen.add(mid)
            text = message_text(session, token, mail, mid)
            code = extract_code(text or "")
            if code:
                return code
        time.sleep(poll)
    return None
