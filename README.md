# crypto-orderflow

Проект для анализа ордерфлоу по криптовалютам (лимитные ордера, дельта, сигналы поглощения) с простым backend на FastAPI и frontend на Lightweight Charts.

## Структура проекта

├── backend/
│ ├── control_server.py # FastAPI-сервер: /api/price/history, /api/delta/history, /api/delta/latest
│ └── vent_delta.py # сбор дельты и запись в Redis
├── frontend/
│ └── delta_cvd.html # веб-страница с графиком и сигналами поглощения
├── LICENSE
└── README.md


### backend

- `control_server.py`
  - Поднимает FastAPI на порту 8088.
  - Эндпоинты:
    - `GET /api/price/history?symbol=SYMBOL&interval=TF`
    - `GET /api/delta/history?symbol=SYMBOL&tf=SECONDS`
    - `GET /api/delta/latest`
    - `GET /` → `{"status": "ok"}`

- `vent_delta.py`
  - Подключается к бирже (Binance).
  - Считает дельту (buy/sell) по времени.
  - Пишет данные в Redis под ключами вида:
    - `delta:{symbol}:{tf}:bar`
    - `delta:{symbol}:{tf}:current`
    - `delta:{symbol}:{tf}:history`

### frontend

- `frontend/delta_cvd.html`
  - Один график свечей (Lightweight Charts).
  - Подтягивает свечи с `/api/price/history`.
  - Подтягивает дельту с `/api/delta/history`.
  - Строит сигналы поглощения:
    - **B** — сильное buy-absorptions (зелёный круг).
    - **S** — сильное sell-absorptions (красный круг).
    - **•** — более слабые зоны поглощения (жёлтая точка).
  - Таймер закрытия текущей свечи справа возле цены.
  - Обновление данных примерно раз в 1 секунду.

## Запуск backend (пример)

Внутри виртуального окружения, где уже стоят зависимости:

```bash
cd /root
./.venv/bin/python vent_delta.py    # поток дельты
./.venv/bin/python control_server.py # API (порт 8088)

