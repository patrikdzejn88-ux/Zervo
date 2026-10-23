from __future__ import annotations

import argparse
import json
import random
import re
import secrets
import string
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from colorama import Fore, Style, init

from zervo import ZervoClient, mail
from zervo import proxy as proxy_util

init(autoreset=True)

ROOT = Path(__file__).resolve().parent
LOGS = ROOT / "logs"
ACCOUNTS = LOGS / "accounts.json"

DEFAULT_WORKERS = 5
CODE_TIMEOUT = 120
RETRY = 2

BANNER = f"""
{Fore.MAGENTA}╔═╗╔═╗╦═╗╦  ╦╔═╗
{Fore.MAGENTA}╔═╝║╣ ╠╦╝╚╗╔╝║ ║
{Fore.WHITE}╚═╝╚═╝╩╚═ ╚╝ ╚═╝{Style.RESET_ALL}
"""

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_print_lock = threading.Lock()
_save_lock = threading.Lock()


def _vlen(s: object) -> int:
    return len(_ANSI_RE.sub("", str(s)))


def _panel(title: str, lines: list[tuple[str, str]], col=Fore.CYAN, w: int = 40) -> None:
    inner = w - 4
    bar = "─" * max(w - len(title) - 7, 1)
    print(f" {col}┌── {title} {bar}┐{Style.RESET_ALL}")
    for lbl, val in lines:
        gap = max(inner - _vlen(lbl) - _vlen(val), 1)
        print(f" {col}│{Style.RESET_ALL} {lbl}{' ' * gap}{val} {col}│{Style.RESET_ALL}")
    print(f" {col}└{'─' * (w - 2)}┘{Style.RESET_ALL}")


def log(msg: str) -> None:
    with _print_lock:
        print(msg)


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"  {prompt}{suffix}: ").strip()
    except EOFError:
        val = ""
    return val if val else default


def _ask_int(prompt: str, default: int) -> int:
    try:
        return max(1, int(_ask(prompt, str(default))))
    except ValueError:
        return default


def _rand_nick(n: int = 8) -> str:
    return "z" + "".join(random.choices(string.ascii_lowercase + string.digits, k=n - 1))


def save_account(row: dict) -> None:
    with _save_lock:
        LOGS.mkdir(parents=True, exist_ok=True)
        data: list = []
        if ACCOUNTS.exists():
            try:
                parsed = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
                if not isinstance(parsed, list):
                    raise ValueError("accounts.json: expected a JSON list")
                data = parsed
            except Exception as e:
                bak = ACCOUNTS.with_name(ACCOUNTS.name + ".bak")
                try:
                    ACCOUNTS.replace(bak)
                    log(
                        f"  {Fore.RED}accounts.json read error ({e}) — бэкап в "
                        f"{bak.name}; аккаунт НЕ сохранён{Style.RESET_ALL}"
                    )
                except Exception as be:
                    log(
                        f"  {Fore.RED}accounts.json read error ({e}); бэкап не удался "
                        f"({be}) — аккаунт НЕ сохранён{Style.RESET_ALL}"
                    )
                return
        by_email = {a.get("email"): a for a in data if a.get("email")}
        by_email[row["email"]] = row
        ACCOUNTS.write_text(
            json.dumps(list(by_email.values()), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def load_count() -> int:
    if not ACCOUNTS.exists():
        return 0
    try:
        return len(json.loads(ACCOUNTS.read_text(encoding="utf-8")))
    except Exception:
        return 0


def _attempt(
    tag: str,
    password: str,
    nickname: Optional[str],
    language: str,
    proxy: Optional[dict],
    sex: int,
    wait: float,
) -> tuple[bool, str]:
    nick = nickname or _rand_nick(8)
    pwd = password or secrets.token_urlsafe(12)
    purl = proxy["url"] if proxy else None
    client = ZervoClient(language=language, proxy=purl, log=log)
    mail_s = requests.Session()
    if purl:
        mail_s.proxies.update({"http": purl, "https": purl})

    mtok = mail.authorize(mail_s)
    email = mail.generate_email()
    log(f"  {tag}  {Fore.CYAN}···{Style.RESET_ALL}  {email}")

    login = client.login_email(email, pwd)
    if login.get("code") not in (201, 200):
        return False, f"  {tag}  {Fore.RED}fail{Style.RESET_ALL}  login"

    send = client.send_mail_code(email, typ=2)
    if not send.get("success"):
        return False, f"  {tag}  {Fore.RED}fail{Style.RESET_ALL}  send"

    code = mail.wait_code(mail_s, mtok, email, timeout=wait, poll=3)
    if not code:
        return False, f"  {tag}  {Fore.RED}fail{Style.RESET_ALL}  {email}  no code"

    valid = client.valid_code(email, code)
    if not valid.get("success"):
        return False, f"  {tag}  {Fore.RED}fail{Style.RESET_ALL}  verify"

    reg = client.register(email, pwd, code, nick, sex=sex)
    if not reg.get("success"):
        return False, f"  {tag}  {Fore.RED}fail{Style.RESET_ALL}  reg {reg.get('msg')}"

    data = reg.get("data") or {}
    pin = (data.get("pinponToken") or {}).get("token") or ""
    gold = None
    if pin:
        client.set_auth(pin)
        try:
            gold = (client.currency_owned().get("data") or {}).get("gold")
        except Exception as e:
            log(f"  {tag}  gold skip: {e}")

    save_account(
        {
            "ts": int(time.time()),
            "registered_at": datetime.now().isoformat(timespec="seconds"),
            "email": email,
            "password": pwd,
            "nickname": nick,
            "appUserId": data.get("appUserId"),
            "id": data.get("id"),
            "pinpon_token": pin,
            "tencent_token": data.get("tencentToken"),
            "did": client.did,
            "gold": gold,
        }
    )
    g = f"  gold {gold}" if gold is not None else ""
    return True, (
        f"  {tag}  {Fore.GREEN}ok{Style.RESET_ALL}  "
        f"{email}  pass={pwd}  {Fore.WHITE}{nick}{Style.RESET_ALL}{g}"
    )


def reg_one(
    idx: int,
    total: int,
    password: str,
    nickname: Optional[str],
    language: str,
    proxy: Optional[dict],
    sex: int,
    wait: float,
) -> tuple[bool, str]:
    tag = f"{Fore.WHITE}[{idx}/{total}]{Style.RESET_ALL}"
    last = f"  {tag}  {Fore.RED}fail{Style.RESET_ALL}"
    for attempt in range(1, RETRY + 1):
        try:
            if proxy:
                proxy_util.rotate(proxy)
            nick = nickname
            if nick and total > 1:
                nick = f"{nick}{random.randint(10, 99)}"
            ok, line = _attempt(tag, password, nick, language, proxy, sex, wait)
            if ok:
                return True, line
            last = line
        except Exception as e:
            last = f"  {tag}  {Fore.RED}fail{Style.RESET_ALL}  {e}"
        if attempt < RETRY:
            time.sleep(2)
    return False, last


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--password", default="")
    ap.add_argument("--nickname", default="")
    ap.add_argument("--count", type=int, default=0)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--language", default="ru_RU")
    ap.add_argument("--wait", type=float, default=CODE_TIMEOUT)
    ap.add_argument("--proxy", default="", help="один прокси, любой формат")
    ap.add_argument("--change-link", default="", help="ссылка смены IP для --proxy")
    ap.add_argument("--proxies", default=str(ROOT / "proxies.txt"), help="файл со списком прокси")
    ap.add_argument("--sex", type=int, default=1)
    ap.add_argument("--no-prompt", action="store_true")
    args = ap.parse_args()

    plist: list[dict] = []
    if args.proxy:
        plist = [proxy_util.make(proxy_util.normalize(args.proxy), args.change_link)]
    elif Path(args.proxies).is_file():
        plist = proxy_util.load(args.proxies)

    t0 = time.time()
    print(BANNER)

    password = args.password
    nickname = args.nickname
    count = args.count if args.count > 0 else 1
    workers = args.workers if args.workers > 0 else DEFAULT_WORKERS

    if not args.no_prompt:
        print(f"  {Fore.WHITE}setup{Style.RESET_ALL}")
        password = _ask("password", password)
        nickname = _ask("nickname (empty=random)", nickname)
        count = _ask_int("accounts", count)
        workers = _ask_int("threads", workers)
        print()

    workers = max(1, min(workers, count))

    _panel(
        "config",
        [
            ("accounts", f"{Fore.CYAN}{count}{Style.RESET_ALL}"),
            ("threads", f"{Fore.CYAN}{workers}{Style.RESET_ALL}"),
            ("password", "*" * len(password)),
            ("nickname", nickname or "random"),
            ("proxies", str(len(plist)) if plist else "off"),
            ("saved", str(load_count())),
        ],
    )
    print()

    ok = fail = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [
            pool.submit(
                reg_one,
                i,
                count,
                password,
                nickname or None,
                args.language,
                plist[(i - 1) % len(plist)] if plist else None,
                args.sex,
                args.wait,
            )
            for i in range(1, count + 1)
        ]
        for fut in as_completed(futs):
            success, line = fut.result()
            log(line)
            if success:
                ok += 1
            else:
                fail += 1

    print()
    _panel(
        "done",
        [
            ("ok", f"{Fore.GREEN}{ok}{Style.RESET_ALL}"),
            ("fail", f"{Fore.RED}{fail}{Style.RESET_ALL}"),
            ("file", "logs/accounts.json"),
            ("time", f"{time.time() - t0:.1f}s"),
        ],
    )
    print()
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
