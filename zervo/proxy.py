import threading
import time
from pathlib import Path

import requests

ROTATE_WAIT = 8


def make(url, change=""):
    return {"url": url, "change": change, "lock": threading.Lock()}


def normalize(p):
    p = p.strip()
    scheme = "http"
    if "://" in p:
        scheme, p = p.split("://", 1)
    if "@" in p:
        return f"{scheme}://{p}"
    parts = p.split(":")
    if len(parts) == 4:
        host, port, user, pwd = parts
        return f"{scheme}://{user}:{pwd}@{host}:{port}"
    return f"{scheme}://{p}"


def load(path):
    out = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        change = ""
        if "|" in line:
            line, change = (x.strip() for x in line.split("|", 1))
        out.append(make(normalize(line), change))
    return out


def rotate(p):
    link = p.get("change")
    if not link:
        return
    with p["lock"]:
        try:
            requests.get(link, timeout=20)
        except Exception:
            pass
        time.sleep(ROTATE_WAIT)
