"""Клиент каталога 5ka.ru через настоящий браузер.

Антибот Servicepipe пропускает только живой браузер, поэтому запросы к 5d.5ka.ru делаются
`fetch`-ем изнутри открытой страницы 5ka.ru: с её куками и служебными заголовками
(x-app-version, x-device-id, x-platform), которые подсматриваем у собственных запросов сайта.
Профиль браузера постоянный (.profile/): адрес доставки и логин, выставленные руками один раз,
переживают перезапуски, и этот же профиль понадобится на этапе 2.

Только чтение каталога. Корзину этот модуль не трогает.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
import urllib.parse
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

SITE = "https://5ka.ru"
API = "https://5d.5ka.ru/api"
SNIFF = ("x-app-version", "x-device-id", "x-platform")


class Blocked(RuntimeError):
    """Антибот не пустил: 403 / страница-заглушка вместо JSON."""


class FiveKa:
    def __init__(self, profile_dir: Path, cache_dir: Path, *, headless: bool = False,
                 pause: tuple[float, float] = (1.5, 3.0), cache_ttl_h: float = 12,
                 channel: str | None = "chrome"):
        self.profile_dir = profile_dir
        self.cache_dir = cache_dir
        self.headless = headless
        self.pause = pause
        self.cache_ttl = cache_ttl_h * 3600
        self.channel = channel
        self.headers: dict[str, str] = {}
        self._last = 0.0
        self._pw = None
        self.ctx: BrowserContext | None = None
        self.page: Page | None = None

    # ── жизненный цикл ──
    async def __aenter__(self) -> "FiveKa":
        self._pw = await async_playwright().start()
        opts = dict(headless=self.headless, locale="ru-RU", timezone_id="Europe/Moscow",
                    viewport={"width": 1366, "height": 860})
        try:
            self.ctx = await self._pw.chromium.launch_persistent_context(
                str(self.profile_dir), channel=self.channel, **opts)
        except Exception:
            # нет установленного Google Chrome: берём Chromium из playwright install
            self.ctx = await self._pw.chromium.launch_persistent_context(str(self.profile_dir), **opts)
        self.page = self.ctx.pages[0] if self.ctx.pages else await self.ctx.new_page()
        self.page.on("request", self._sniff)
        await self.page.goto(SITE, wait_until="domcontentloaded", timeout=60000)
        await self._wait_headers()
        return self

    async def __aexit__(self, *exc) -> None:
        if self.ctx:
            await self.ctx.close()
        if self._pw:
            await self._pw.stop()

    def _sniff(self, request) -> None:
        if request.url.startswith(API):
            for h in SNIFF:
                v = request.headers.get(h)
                if v:
                    self.headers[h] = v

    async def _wait_headers(self, timeout_s: float = 90) -> None:
        """Ждём, пока сайт сам сходит в API. Если висит капча, человек решает её в окне браузера."""
        t0 = time.monotonic()
        warned = False
        while not all(h in self.headers for h in SNIFF):
            if time.monotonic() - t0 > 8 and not warned:
                print("… жду, пока 5ka.ru загрузится. Если в окне капча или «я не робот», пройди её руками.")
                warned = True
            if time.monotonic() - t0 > timeout_s:
                raise Blocked("5ka.ru так и не открылся (антибот или не российский IP)")
            await asyncio.sleep(0.5)

    # ── запросы ──
    async def _pace(self) -> None:
        wait = self._last + random.uniform(*self.pause) - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = time.monotonic()

    async def get(self, path: str, params: dict | None = None, *, cache: bool = True):
        url = f"{API}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        cfile = self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".json")
        if cache and cfile.exists() and time.time() - cfile.stat().st_mtime < self.cache_ttl:
            return json.loads(cfile.read_text(encoding="utf-8"))

        for attempt in range(3):
            await self._pace()
            res = await self.page.evaluate(
                """async ({url, headers}) => {
                    const r = await fetch(url, {headers: {...headers, Accept: 'application/json, text/plain, */*'},
                                                credentials: 'include', mode: 'cors'});
                    return {status: r.status, text: await r.text()};
                }""",
                {"url": url, "headers": self.headers},
            )
            if res["status"] == 200 and res["text"].lstrip().startswith(("{", "[")):
                data = json.loads(res["text"])
                if cache:
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    cfile.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return data
            if res["status"] in (403, 429) or "<html" in res["text"][:200].lower():
                # антибот: даём сайту перезагрузиться и обновить куки, потом пробуем ещё раз
                await asyncio.sleep(5 * (attempt + 1))
                await self.page.reload(wait_until="domcontentloaded")
                await self._wait_headers()
                continue
            raise RuntimeError(f"GET {path}: HTTP {res['status']}: {res['text'][:200]}")
        raise Blocked(f"GET {path}: антибот не пускает после 3 попыток")

    # ── магазин доставки ──
    async def selected_store(self) -> dict | None:
        """Магазин, выбранный в шапке сайта (адрес доставки, выставленный руками)."""
        raw = await self.page.evaluate("() => localStorage.getItem('DeliveryPanelStore')")
        if not raw:
            return None
        d = json.loads(raw)
        st = d.get("selectedStore") or {}
        if st.get("sapCode"):
            return {"sap_code": st["sapCode"], "shop_address": st.get("shopAddress", "")}
        return None

    async def store_by_address(self, address: str) -> dict:
        await self._pace()
        url = f"{SITE}/api/maps/geocode/?geocode={urllib.parse.quote(address)}"
        geo = await self.page.evaluate(
            "async (u) => { const r = await fetch(u, {credentials: 'include'}); return await r.json(); }", url)
        pos = geo["response"]["GeoObjectCollection"]["featureMember"][0]["GeoObject"]["Point"]["pos"]
        lon, lat = pos.split()[:2]
        return await self.get("/orders/v1/orders/stores/", {"lat": lat, "lon": lon}, cache=False)

    # ── каталог ──
    async def search(self, sap: str, query: str, mode: str = "delivery", limit: int = 20) -> list[dict]:
        data = await self.get(f"/catalog/v3/stores/{sap}/search",
                              {"mode": mode, "include_restrict": "true", "q": query, "limit": limit})
        return list(data.get("products") or [])

    async def product(self, sap: str, plu: str | int, mode: str = "delivery") -> dict:
        return await self.get(f"/catalog/v2/stores/{sap}/products/{plu}",
                              {"mode": mode, "include_restrict": "true"})
