"""Список покупок из открытого API racion.app (https://racion.app/openapi.json)."""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field

API = "https://racion.app"
UA = "racion2cart/0.1 (+personal use)"


@dataclass
class Need:
    """Одна позиция списка покупок Рациона."""

    key: str  # ingredientId или extra:<id>
    name: str
    group: str
    unit: str  # g | ml | pcs | "" (свой товар без количества)
    needed: float  # сколько уйдёт в блюда
    buy: float  # сколько советует купить Рацион
    packs: int
    pack: float
    loose: bool
    racion_cost: float
    used_in: list[str] = field(default_factory=list)
    qty_text: str = ""  # для своих товаров: количество как написал человек


def plan_id(url_or_id: str) -> str:
    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", url_or_id)
    if not m:
        raise ValueError(f"не вижу id плана в {url_or_id!r}")
    return m.group(0)


def _get(path: str):
    req = urllib.request.Request(API + path, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def load(url_or_id: str, include_pantry: bool = False, include_checked: bool = False) -> tuple[dict, list[Need]]:
    """План и позиции, которые надо купить.

    Повторяет логику кнопки «Собрать корзину» в Рационе: пропускает отмеченное «куплено»,
    «обычно есть дома» (pantry) и то, что уже есть дома (atHome); свои товары добавляет в конец.
    """
    pid = plan_id(url_or_id)
    plan = _get(f"/api/plans/{pid}?lang=ru")
    checked = set(_get(f"/api/plans/{pid}/checks") or []) if not include_checked else set()
    extras = _get(f"/api/plans/{pid}/extras") or []

    needs: list[Need] = []
    for g in plan.get("shopping", []):
        for it in g.get("items", []):
            if it["ingredientId"] in checked or it.get("atHome"):
                continue
            if it.get("pantry") and not include_pantry:
                continue
            needs.append(
                Need(
                    key=it["ingredientId"],
                    name=it["name"],
                    group=g.get("label", ""),
                    unit=it["unit"],
                    needed=float(it["needed"]),
                    buy=float(it["buy"]),
                    packs=int(it.get("packs") or 0),
                    pack=float(it.get("pack") or 0),
                    loose=bool(it.get("loose")),
                    racion_cost=float(it.get("cost") or 0),
                    used_in=list(it.get("usedIn") or []),
                )
            )
    for e in extras:
        key = f"extra:{e['id']}"
        if key in checked:
            continue
        needs.append(
            Need(key=key, name=e["name"], group="Своё", unit="", needed=0, buy=0, packs=0, pack=0,
                 loose=False, racion_cost=0, qty_text=e.get("qty") or "")
        )
    return plan, needs
