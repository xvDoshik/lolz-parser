EN | [RU](docs/README_RU.md)

## Lolz Parser 🎮

Parser and analytics for **Brawl Stars** listings from [lzt.market](https://lzt.market) (Lolzteam): Playwright skin crawler, SQLite database, deal ranking, Telegram alerts and web panel.

> Before running: `cp .env.example .env`, `cp .notify_config.example.json .notify_config.json`.

---

## ✨ Features

| UI section | What it does |
|------------|--------------|
| **Parse** | Playwright crawler over `brawl-stars-skin-urls.txt` → `skins.sqlite` |
| **Search** | Filters by skins, level, trophies, price |
| **DB** | Listings table with links to `lzt.market/{id}` |
| **Opt** | Top deals (scoring) |
| **OptPrm** | Optimization for a given skin set |
| **Sell** | Bundle builder for sale by listing ID |
| **Notification** | Rules + Telegram bot token → alerts on new matches |

Additionally:

- **Auth gate** - bcrypt password for the entire site (`SONIC_GATE_PASSWORD_HASH`)
- **Resume** - `.crawl_resume.json` continues parsing from where it stopped
- **Deploy** - systemd + nginx reverse proxy

---

## Stack

- **Backend:** Python 3.11+, FastAPI, uvicorn, Playwright
- **Frontend:** React + Vite + TypeScript
- **DB:** SQLite (`skins.sqlite`, WAL)
- **HTML parsing:** `market_listing.py` - lzt.market card parser

---

## 🚀 Quick start (local)

```bash
cd lolz-parser
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
cp .notify_config.example.json .notify_config.json

cd frontend && npm ci && npm run build && cd ..

python main.py
```

Open `http://127.0.0.1:13337/`

Password hash:

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'your-password', bcrypt.gensalt()).decode())"
```

---

## ⚙️ Environment variables

| Variable | Description |
|----------|-------------|
| `SONIC_GATE_PASSWORD_HASH` | bcrypt hash; empty = gate disabled |
| `SONIC_GATE_ALLOWED_HOSTS` | Allowed Host values (comma-separated) |
| `SONIC_GATE_ALLOW_HTTP` | `1` - no HTTPS in dev |

### `.notify_config.json`

```json
{
  "telegram_bot_token": "",
  "telegram_chat_ids": "123,456",
  "interval_sec": 60,
  "rules": []
}
```

Empty token - background notifications are not sent.

---

## Production deploy

```bash
sudo install -m 644 deploy/lolz-parser.service /etc/systemd/system/lolz-parser.service
sudo install -m 644 deploy/nginx-lolz.example.conf /etc/nginx/sites-available/lolz.example.com
sudo ln -sf /etc/nginx/sites-available/lolz.example.com /etc/nginx/sites-enabled/

sudo systemctl daemon-reload
sudo systemctl enable --now lolz-parser
sudo nginx -t && sudo systemctl reload nginx
```

Uvicorn listens on `127.0.0.1:13337`, nginx proxies from outside.

---

## Structure

```
lolz-parser/
├── main.py
├── crawl_worker.py
├── market_listing.py
├── skins_db.py
├── optimize_rank.py
├── sell_listing.py
├── notifications.py
├── auth_gate.py
├── brawl-stars-skin-urls.txt
├── frontend/
└── deploy/
```

---

## API (after gate login)

| Endpoint | Description |
|----------|-------------|
| `POST /api/gate/login` | Login |
| `GET /api/parse/status` | Crawler status |
| `POST /api/parse/start` | Start parsing |
| `POST /api/parse/stop` | Stop |
| `GET /api/search` | DB search |
| `GET /api/optimized` | Top deals |
| `GET/PUT /api/notifications` | Alert config |

---

## Security

- Do not commit `.env`, `.notify_config.json`, `skins.sqlite`
- Gate is required on a public domain
- Playwright requires `chromium`; on Linux you often need `playwright install-deps chromium`

---

## License

MIT
