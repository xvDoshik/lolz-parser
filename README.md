# Lolz Parser

Парсер и аналитика лотов **Brawl Stars** с [lzt.market](https://lzt.market) (Lolzteam): краулинг скинов через Playwright, SQLite-база, ранжирование сделок, Telegram-алерты и веб-панель.

**Автор:** xv_Dosha

> Перед запуском: `cp .env.example .env`, `cp .notify_config.example.json .notify_config.json`.

---

## Возможности

| Раздел UI | Что делает |
|-----------|------------|
| **Парс** | Playwright-краулер по `brawl-stars-skin-urls.txt` → `skins.sqlite` |
| **Поиск** | Фильтры по скинам, уровню, трофеям, цене |
| **БД** | Таблица лотов с ссылками на `lzt.market/{id}` |
| **Opt** | Топ выгодных лотов (scoring) |
| **OptPrm** | Оптимизация по заданному набору скинов |
| **Sell** | Сборка bundle для продажи по ID лота |
| **Notification** | Правила + Telegram bot token → алерты при новых матчах |

Дополнительно:

- **Auth gate** — bcrypt-пароль на весь сайт (`SONIC_GATE_PASSWORD_HASH`)
- **Resume** — `.crawl_resume.json` продолжает парс с места остановки
- **Deploy** — systemd + nginx reverse proxy

---

## Стек

- **Backend:** Python 3.11+, FastAPI, uvicorn, Playwright
- **Frontend:** React + Vite + TypeScript
- **DB:** SQLite (`skins.sqlite`, WAL)
- **Парсинг HTML:** `market_listing.py` — разбор карточек lzt.market

---

## Быстрый старт (локально)

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

Открой `http://127.0.0.1:13337/`

Хеш пароля:

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'your-password', bcrypt.gensalt()).decode())"
```

---

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `SONIC_GATE_PASSWORD_HASH` | bcrypt-хеш; пусто = gate выключен |
| `SONIC_GATE_ALLOWED_HOSTS` | Разрешённые Host (через запятую) |
| `SONIC_GATE_ALLOW_HTTP` | `1` — без HTTPS в dev |

### `.notify_config.json`

```json
{
  "telegram_bot_token": "",
  "telegram_chat_ids": "123,456",
  "interval_sec": 60,
  "rules": []
}
```

Пустой token — фоновые уведомления не отправляются.

---

## Продакшн-деплой

```bash
sudo install -m 644 deploy/lolz-parser.service /etc/systemd/system/lolz-parser.service
sudo install -m 644 deploy/nginx-lolz.example.conf /etc/nginx/sites-available/lolz.example.com
sudo ln -sf /etc/nginx/sites-available/lolz.example.com /etc/nginx/sites-enabled/

sudo systemctl daemon-reload
sudo systemctl enable --now lolz-parser
sudo nginx -t && sudo systemctl reload nginx
```

Uvicorn слушает `127.0.0.1:13337`, nginx проксирует снаружи.

---

## Структура

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

## API (после входа в gate)

| Endpoint | Описание |
|----------|----------|
| `POST /api/gate/login` | Логин |
| `GET /api/parse/status` | Статус краулера |
| `POST /api/parse/start` | Старт парсинга |
| `POST /api/parse/stop` | Стоп |
| `GET /api/search` | Поиск по БД |
| `GET /api/optimized` | Топ сделок |
| `GET/PUT /api/notifications` | Конфиг алертов |

---

## Безопасность

- Не коммить `.env`, `.notify_config.json`, `skins.sqlite`
- Gate обязателен на публичном домене
- Playwright требует `chromium`; на Linux часто нужен `playwright install-deps chromium`

---

## License

MIT
