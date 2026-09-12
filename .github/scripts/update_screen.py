import json
import os
import random
import sys
import time
import urllib.request

import paho.mqtt.client as mqtt

MOEX_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/index/securities/"
    "IMOEX.json?iss.meta=off&iss.only=marketdata"
)
BTC_URL = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
SBER_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/shares/boards/TQBR/securities/"
    "SBER.json?iss.meta=off&iss.only=marketdata"
)

BROKER_HOST = "test.mosquitto.org"
BROKER_PORT = 1883
HOSTNAME = "smalltv"
TOPIC = f"smalltv/{HOSTNAME}/screen/main"

BG = "#0A0A16"
PANEL = "#141428"
ORANGE = "#F7931A"
BLUE = "#3CAAFF"
WHITE = "#EBEBF5"
GREEN = "#3CDC78"
RED = "#F04646"
GREY = "#6E6E8C"


def fetch_btc():
    with urllib.request.urlopen(BTC_URL, timeout=15) as r:
        d = json.load(r)["bitcoin"]
    return d["usd"], d["usd_24h_change"]


def fetch_imoex():
    with urllib.request.urlopen(MOEX_URL, timeout=15) as r:
        d = json.load(r)["marketdata"]
    if not d["data"]:
        raise RuntimeError("MOEX returned no data rows")
    rec = dict(zip(d["columns"], d["data"][0]))
    price = rec.get("CURRENTVALUE") or rec.get("LASTVALUE")
    return price, rec.get("LASTCHANGEPRC")


def fetch_moex_is_open():
    # The index board carries no live trading-status flag; SBER on the main
    # equities board does, and it follows the same session as the index.
    with urllib.request.urlopen(SBER_URL, timeout=15) as r:
        d = json.load(r)["marketdata"]
    rec = dict(zip(d["columns"], d["data"][0]))
    return rec.get("TRADINGSTATUS") == "T"


def rect(x, y, w, h, c):
    return {"t": "rect", "x": x, "y": y, "w": w, "h": h, "c": c}


def text(x, y, v, c, s=1):
    return {"t": "text", "x": x, "y": y, "v": v, "c": c, "s": s}


def icon(x, y, v, c, s=1):
    return {"t": "icon", "x": x, "y": y, "v": v, "c": c, "s": s}


def circle(x, y, r, c):
    return {"t": "circle", "x": x, "y": y, "r": r, "c": c}


def panel(y0, label, color, price_str, chg_pct):
    up = chg_pct >= 0
    arrow_color = GREEN if up else RED
    draw = [
        rect(6, y0, 228, 100, PANEL),
        text(14, y0 + 12, label, color, s=2),
        text(14, y0 + 38, price_str, WHITE, s=3),
        icon(14, y0 + 74, "arrow-up" if up else "arrow-down", arrow_color, s=1),
        text(40, y0 + 75, f"{chg_pct:+.2f}%", arrow_color, s=2),
    ]
    return draw


def bullseye_panel(y0, line):
    cx, cy = 60, y0 + 50
    draw = [
        rect(6, y0, 228, 100, PANEL),
        circle(cx, cy, 34, WHITE),
        circle(cx, cy, 24, RED),
        circle(cx, cy, 14, WHITE),
        circle(cx, cy, 5, RED),
        text(112, y0 + 30, "MARIA", RED, s=2),
        text(112, y0 + 58, line, WHITE, s=1),
    ]
    return draw


def status_badge(y0, is_open):
    label = "OPEN" if is_open else "CLOSED"
    # Right-align by hand: the 6x8 font is 6*s px per character.
    x = 228 - len(label) * 6
    return text(x, y0 + 14, label, GREEN if is_open else GREY, s=1)


def build_screen(btc_price, btc_chg, imoex_price, imoex_chg, moex_open, egg_line):
    draw = []
    draw += panel(8, "BTC", ORANGE, f"${btc_price:,.0f}", btc_chg)
    if egg_line:
        draw += bullseye_panel(114, egg_line)
    else:
        draw += panel(114, "IMOEX", BLUE, f"{imoex_price:,.1f}", imoex_chg)
        if moex_open is not None:
            draw.append(status_badge(114, moex_open))
    return {"bg": BG, "ttl": 600, "draw": draw}


def main():
    btc_price, btc_chg = fetch_btc()
    imoex_price, imoex_chg = fetch_imoex()
    try:
        moex_open = fetch_moex_is_open()
    except Exception as e:      # a missing badge beats a missing screen
        print("trading status unavailable:", e, file=sys.stderr)
        moex_open = None
    print("BTC:", btc_price, btc_chg, file=sys.stderr)
    print("IMOEX:", imoex_price, imoex_chg, "open:", moex_open, file=sys.stderr)

    lines = [
        "PERFECT SCORE",
        "STEADY HANDS",
        "GOLD MEDAL FORM",
        "BULLSEYE QUEEN",
        "10/10 EVERY TIME",
    ]
    forced = os.environ.get("FORCE_EGG", "").lower() == "true"
    egg_line = random.choice(lines) if (forced or random.random() < 1 / 130) else None
    if egg_line:
        print("easter egg:", egg_line, file=sys.stderr)

    screen = build_screen(btc_price, btc_chg, imoex_price, imoex_chg, moex_open, egg_line)
    payload = json.dumps(screen, separators=(",", ":"))
    print("payload bytes:", len(payload), file=sys.stderr)
    print(payload, file=sys.stderr)

    # PubSubClient on the ESP8266 has a 768 B buffer for the WHOLE packet:
    # payload + topic (27 B) + header. Oversized packets are dropped silently.
    limit = 768 - len(TOPIC) - 10
    if len(payload) > limit:
        raise SystemExit(f"payload {len(payload)} B exceeds the device limit of {limit} B")

    client_id = "bullseye-market-" + str(random.randint(0, 999999))
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        protocol=mqtt.MQTTv311,
    )
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=15)
    client.loop_start()
    info = client.publish(TOPIC, payload=payload, qos=1, retain=True)
    info.wait_for_publish(timeout=10)
    time.sleep(2)
    client.loop_stop()
    client.disconnect()
    print("published to", TOPIC, "via", BROKER_HOST, file=sys.stderr)


if __name__ == "__main__":
    main()
