import json
import os
import random
import sys
import urllib.request

MOEX_URL = (
    "https://iss.moex.com/iss/engines/stock/markets/index/securities/"
    "IMOEX.json?iss.meta=off&iss.only=marketdata"
)


def fetch_imoex():
    with urllib.request.urlopen(MOEX_URL, timeout=15) as r:
        d = json.load(r)["marketdata"]
    if not d["data"]:
        raise RuntimeError("MOEX returned no data rows")
    rec = dict(zip(d["columns"], d["data"][0]))
    price = rec.get("CURRENTVALUE") or rec.get("LASTVALUE")
    return {
        "symbol": "IMOEX",
        "name": "IMOEX",
        "price": price,
        "currency": "",
        "change": rec.get("LASTCHANGE"),
        "changePct": rec.get("LASTCHANGEPRC"),
        "range": "1D",
        "ok": price is not None,
    }


def shot_spark():
    # Flat "steady hands" baseline, then a sharp spike - like a shot landing dead
    # center. Small jitter on the baseline so it doesn't look like a flat line bug.
    n = 18
    spark = [4 + random.uniform(-0.4, 0.4) for _ in range(n - 2)]
    spark += [9.5, 10]
    return spark


def easter_egg():
    lines = [
        "PERFECT SCORE",
        "STEADIEST HANDS ALIVE",
        "GOLD MEDAL FORM",
        "BULLSEYE QUEEN",
        "10/10 EVERY TIME",
    ]
    return {
        "symbol": "IMOEX",
        "name": "MARIA - " + random.choice(lines),
        "price": 10,
        "currency": "",
        "change": 6,
        "changePct": 150,
        "spark": shot_spark(),
        "range": "1D",
        "ok": True,
    }


def main():
    payload = fetch_imoex()
    print("fetched:", payload, file=sys.stderr)

    forced = os.environ.get("FORCE_EGG", "").lower() == "true"
    if forced or random.random() < 1 / 130:
        payload = easter_egg()
        print(("forced " if forced else "") + "easter egg fired:", payload, file=sys.stderr)

    os.makedirs("quotes", exist_ok=True)
    with open("quotes/imoex.json", "w") as f:
        json.dump(payload, f)
    print("wrote quotes/imoex.json:", payload, file=sys.stderr)


if __name__ == "__main__":
    main()
