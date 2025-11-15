# control_server.py — чистая рабочая сборка

import os
import json
import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

# ----------------------
# ENV
# ----------------------
SYMBOL    = "btcusdt"
TF_SEC    = 60
REDIS_URL = "redis://localhost:6379/0"

# ----------------------
# Redis
# ----------------------
r = redis.from_url(REDIS_URL, decode_responses=True)

KEY_BAR   = f"delta:{SYMBOL}:{TF_SEC}:bar"
KEY_CURR  = f"delta:{SYMBOL}:{TF_SEC}:current"
KEY_HIST  = f"delta:{SYMBOL}:{TF_SEC}:history"

# ----------------------
# FastAPI
# ----------------------
app = FastAPI(default_response_class=ORJSONResponse)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# ===========================================================
#   1) Последняя дельта с Redis
# ===========================================================
@app.get("/api/delta/latest")
async def delta_latest():
    bar  = await r.hgetall(KEY_BAR)
    curr = await r.hgetall(KEY_CURR)
    return {"bar": bar, "current": curr}


# ===========================================================
#   2) История дельты
# ===========================================================
@app.get("/api/delta/history")
async def delta_history(symbol: str = "btcusdt", tf: int = 60):
    key = f"delta:{symbol}:{tf}:history"
    items = await r.lrange(key, 0, -1)

    out = []
    for row in items:
        try:
            out.append(json.loads(row))
        except:
            pass

    return out


# ===========================================================
#   3) Binance candles (без CORS!)
# ===========================================================
# ===========================================================
#   3) Binance candles — поддержка 5s/10s/15s/30s
# ===========================================================
    # ===========================================================
#   3) Binance candles — эмуляция 5s/10s/15s/30s на основе 1m
# ===========================================================
@app.get("/api/price/history")
async def price_history(symbol: str = "btcusdt", interval: str = "1m"):
    interval = interval.lower()

    # Если нужно меньше минуты → используем 1m и дробим
    sub_tf = None
    if interval.endswith("s"):
        try:
            sub_tf = int(interval[:-1])  # "5s" -> 5
        except:
            return {"error": "bad interval"}

        if sub_tf not in [5, 10, 15, 30]:
            return {"error": "only 5s/10s/15s/30s supported"}

        # Устанавливаем базовый запрос = 1m
        interval = "1m"

    # Загружаем 1m свечи с Binance
    url = (
        f"https://api.binance.com/api/v3/klines?"
        f"symbol={symbol.upper()}&interval={interval}&limit=500"
    )

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url)
            r.raise_for_status()
            j = r.json()
    except Exception as e:
        return {"error": "binance_down", "detail": str(e)}

    # Если обычный минутный/часовой ТФ → просто отдаём его
    if sub_tf is None:
        out = []
        for x in j:
            out.append({
                "time":  x[0] // 1000,
                "open":  float(x[1]),
                "high":  float(x[2]),
                "low":   float(x[3]),
                "close": float(x[4]),
            })
        return out

    # --------------------------------------------------------
    # Эмуляция 5s, 10s, 15s, 30s
    # --------------------------------------------------------
    result = []
    for x in j:
        t = x[0] // 1000
        o = float(x[1])
        h = float(x[2])
        l = float(x[3])
        c = float(x[4])

        segments = 60 // sub_tf
        step = (c - o) / segments if segments > 0 else 0

        # Приблизительная средняя цена для high/low
        mid = (o + c) / 2
        spread = abs(h - l) * 0.25  # мягкое распределение

        for i in range(segments):
            t0 = t + i * sub_tf
            o0 = o + step * i
            c0 = o + step * (i + 1)

            result.append({
                "time": int(t0),
                "open": o0,
                "close": c0,
                "high": max(o0, c0) + spread,
                "low":  min(o0, c0) - spread,
            })

    return result




# ===========================================================
#   4) Root / ping
# ===========================================================
@app.get("/")
async def root():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "control_server:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8088)),
        reload=False
    )
