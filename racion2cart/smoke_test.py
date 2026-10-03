"""Этап 0: проверка pyaterochka_api вживую.

Запускать на своей машине с российского IP (из зарубежных/облачных IP 5ka.ru не пускает).

    pip install "git+https://github.com/Open-Inflation/pyaterochka_api"
    python -m camoufox fetch
    python smoke_test.py --street "Невский проспект" --house 28 --query "молоко 3,2%"
"""

import argparse
import asyncio
import json

from pyaterochka_api import PyaterochkaAPI
from pyaterochka_api.enums import PurchaseMode


async def main(args: argparse.Namespace) -> None:
    async with PyaterochkaAPI(headless=args.headless) as api:
        print("заголовки из прогрева:", api.unstandard_headers)

        geo = (await api.Geolocation.geocode(city="Санкт-Петербург", street=args.street, house=args.house)).json()
        pos = geo["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["Point"]["pos"]
        lon, lat = (float(v) for v in pos.split())
        print(f"геокод: lat={lat} lon={lon}")

        store = (await api.Geolocation.find_store(longitude=lon, latitude=lat)).json()
        print("магазин доставки:", json.dumps(store, ensure_ascii=False))
        sap = store["sap_code"]

        await asyncio.sleep(1.5)
        resp = await api.Catalog.search(sap_code_store_id=sap, query=args.query, mode=PurchaseMode.DELIVERY, limit=10)
        data = resp.json()
        for p in data.get("products", []):
            prices = p.get("prices") or {}
            print(
                f"{p['plu']:>8} | {p['name'][:60]:60} | {p.get('property_clarification')!s:>8} | "
                f"{prices.get('regular')} / {prices.get('discount')} ₽ | uom={p.get('uom')} step={p.get('step')} "
                f"| в наличии={p.get('is_available')}"
            )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--street", default="Невский проспект")
    ap.add_argument("--house", default="28")
    ap.add_argument("--query", default="молоко 3,2%")
    ap.add_argument("--headless", action="store_true")
    asyncio.run(main(ap.parse_args()))
