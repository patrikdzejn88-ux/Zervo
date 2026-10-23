import os
import random
import secrets
import time

import requests

HOST = os.environ.get("ZERVO_HOST", "https://api.zervo.me")
APP_VERSION = "235"
UA = "Dart/3.10 (dart:io)"

HTTP_RETRIES = 4
RETRYABLE_STATUS = (429, 500, 502, 503, 504)
BACKOFF_BASE = 8.0


def rand_did():
    return "v2:" + secrets.token_hex(16)


def birthday(years=21):
    y = time.gmtime().tm_year - years
    return f"{y}-06-15 12:00:00.000Z"


class ZervoClient:
    def __init__(self, language="ru_RU", proxy=None, log=None):
        self.did = rand_did()
        self.language = language
        self.log = log or print
        self.s = requests.Session()
        if proxy:
            self.s.proxies.update({"http": proxy, "https": proxy})
        self.s.headers.update(
            {
                "accept-encoding": "gzip",
                "app": "zervo",
                "app-version": APP_VERSION,
                "did": self.did,
                "language": language,
                "platform": "0",
                "sv": "4",
                "user-agent": UA,
            }
        )

    def _post(self, path, *, data=None, json_body=None, ctype):
        r = None
        for attempt in range(1, HTTP_RETRIES + 1):
            r = self.s.post(
                HOST + path,
                data=data,
                json=json_body,
                headers={"content-type": ctype},
                timeout=30,
            )
            if r.status_code not in RETRYABLE_STATUS:
                break
            if attempt < HTTP_RETRIES:
                pause = BACKOFF_BASE * (2 ** (attempt - 1)) + random.uniform(0, 3)
                self.log(
                    f"http {r.status_code} {path.rsplit('/', 1)[-1]}, "
                    f"retry {attempt}/{HTTP_RETRIES - 1} in {pause:.0f}s"
                )
                time.sleep(pause)
        r.raise_for_status()
        return r.json()

    def _form(self, path, data):
        return self._post(path, data=data, ctype="application/x-www-form-urlencoded")

    def _json(self, path, body):
        return self._post(path, json_body=body, ctype="application/json")

    def _get(self, path, params=None):
        r = self.s.get(HOST + path, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def set_auth(self, token):
        self.s.headers["pinpon-auth"] = token

    def login_email(self, email, password):
        return self._form(
            "/pinpon-app-auth/v3/auth/login/email",
            {"email": email, "password": password},
        )

    def query_email(self, email):
        return self._get("/pinpon-app-system/app-user/query/email", {"email": email})

    def send_mail_code(self, email, typ=2):
        return self._form(
            "/pinpon-app-system/v2/app-user/mail",
            {"email": email, "type": str(typ), "language": self.language},
        )

    def valid_code(self, email, code):
        return self._form(
            "/pinpon-app-system/app-user/valid/code",
            {"email": email, "code": code},
        )

    def register(self, email, password, code, nickname, sex=1):
        return self._json(
            "/pinpon-app-system/v3/app-user/register",
            {
                "email": email,
                "password": password,
                "source": "email",
                "uid": "",
                "code": code,
                "nickname": nickname,
                "birthday": birthday(),
                "sex": sex,
            },
        )

    def currency_owned(self):
        return self._get("/api/currency/owned")
