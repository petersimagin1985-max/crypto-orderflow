# vent_delta.py — стабильная версия
import asyncio, json, os, time
import websockets
import redis.asyncio as redis
from datetime import datetime

SYMBOL    = "btcusdt"
TF_SEC    = 60
REDIS_URL = "redis://localhost:6379/0"

WS_URL    = f"wss://fstream.binance.com/ws/{SYMBOL}@aggTrade"

KEY_BAR   = f"delta:{SYMBOL}:{TF_SEC}:bar"
KEY_CURR  = f"delta:{SYMBOL}:{TF_SEC}:current"
KEY_CVD   = f"cvd:{SYMBOL}:{TF_SEC}:current"
KEY_HIST  = f"delta:{SYMBOL}:{TF_SEC}:history"

CHAN      = f"delta:{SYMBOL}:{TF_SEC}:stream"


# ================================================================
#   ПРИВЯЗКА ts К ОТКРЫТИЮ СВЕЧИ (как Binance)
# ================================================================
def bucket_ts(unix_time: int) -> int:
    """
    Превращает обычный timestamp в открытие текущей свечи.
    Т.е. 18:32:45 -> 18:32:00
    """
    return unix_time - (unix_time % TF_SEC)


async def vent():
    r = redis.from_url(REDIS_URL, decode_responses=True)

    backoff = 1
    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=15, ping_timeout=15) as ws:
                print(f"[vent] CONNECTED → {WS_URL}")
                backoff = 1

                bid_vol = 0.0
                ask_vol = 0.0
                delta   = 0.0

                cvd = float(await r.get(KEY_CVD) or 0.0)

                last_bucket = bucket_ts(int(time.time()))

                async for msg in ws:
                    d = json.loads(msg)
                    price = float(d["p"])
                    qty   = float(d["q"])
                    is_sell = d["m"]  # True — агрессивный продавец

                    if is_sell:
                        bid_vol += qty
                        delta   -= qty
                    else:
                        ask_vol += qty
                        delta   += qty

                    now = int(time.time())
                    now_bucket = bucket_ts(now)

                    # -------------------------------------------------------
                    #  Закрываем свечу (дельтовую)
                    # -------------------------------------------------------
                    if now_bucket > last_bucket:
                        ts = last_bucket  # закрытая минута

                        cvd += delta

                        bar = {
                            "symbol": SYMBOL,
                            "tf_sec": TF_SEC,
                            "ts": ts,
                            "bid_vol": round(bid_vol, 8),
                            "ask_vol": round(ask_vol, 8),
                            "delta":   round(delta, 8),
                            "cvd":     round(cvd, 8)
                        }

                        # запись последней закрытой дельты
                        await r.hset(KEY_BAR, mapping=bar)
                        await r.set(KEY_CVD, bar["cvd"])

                        # история (список JSON)
                        await r.rpush(KEY_HIST, json.dumps(bar))
                        await r.ltrim(KEY_HIST, -500, -1)   # храним 500 баров

                        # публикация по каналу
                        await r.publish(CHAN, json.dumps({"type": "bar", "data": bar}))

                        # Сбрасываем ведро
                        bid_vol = ask_vol = 0.0
                        delta   = 0.0
                        last_bucket = now_bucket

                    # -------------------------------------------------------
                    #  Текущая (незакрытая) минута
                    # -------------------------------------------------------
                    await r.hset(KEY_CURR, mapping={
                        "symbol": SYMBOL,
                        "tf_sec": TF_SEC,
                        "ts": now_bucket,
                        "bid_vol": round(bid_vol, 8),
                        "ask_vol": round(ask_vol, 8),
                        "delta":   round(delta, 8),
                        "cvd":     round(cvd + delta, 8)
                    })

                    await asyncio.sleep(0)

        except Exception as e:
            print(f"[vent] ERROR → reconnect in {backoff}s: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    asyncio.run(vent())
