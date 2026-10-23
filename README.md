# Zervo

регистрация аккаунтов zervo / account registration cli

файлы / files:
- autoreg.py — cli
- zervo/client.py — api
- zervo/mail.py — temp mail
- zervo/proxy.py — proxies
- proxies.txt — proxy list, not in git
- requirements.txt

запуск / run:
pip install -r requirements.txt
python autoreg.py
python autoreg.py --no-prompt --count 10 --workers 2

аккаунты падают в logs/accounts.json

прокси / proxies, один на строку:
host:port
host:port:user:pass
user:pass@host:port
после | ссылка смены ip, без неё прокси считается rotating
