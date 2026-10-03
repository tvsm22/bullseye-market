"""Таблица сопоставления: markdown для глаз и CSV для этапа 2."""

from __future__ import annotations

import csv
from pathlib import Path

from .matcher import Match, Option, price_of

MARK = {"high": "🟢 высокая", "medium": "🟡 средняя", "low": "🔴 низкая", "none": "⚫ не найдено"}


def _need_label(m: Match) -> str:
    n = m.need
    if not n.unit:
        return f"{n.name} {n.qty_text}".strip()
    unit = {"g": "г", "ml": "мл", "pcs": "шт"}[n.unit]
    return f"{n.name}, {n.needed:g} {unit}"


def _money(x: float | None) -> str:
    return "—" if x is None else f"{x:,.2f}".replace(",", " ").replace(".00", "")


def _opt_short(o: Option) -> str:
    now, _ = price_of(o.product)
    return f"[{o.name}]({o.url}) · {o.pack_label} · {_money(now)} ₽ × {o.qty_label} = {_money(o.cost)} ₽"


def write(matches: list[Match], out_dir: Path, store: dict, plan: dict) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md, cs = out_dir / "table.md", out_dir / "table.csv"

    total = sum(m.best.cost or 0 for m in matches if m.best)
    racion_total = sum(m.need.racion_cost for m in matches)
    by_conf = {k: sum(1 for m in matches if m.confidence == k) for k in MARK}

    lines = [
        f"# Корзина Пятёрочки по плану Рациона",
        "",
        f"Магазин доставки: **{store.get('sap_code')}** {store.get('shop_address', '')}  ",
        f"Неделя с {plan.get('params', {}).get('startDate', '?')}, позиций: {len(matches)}  ",
        f"Уверенность: " + ", ".join(f"{MARK[k]} {v}" for k, v in by_conf.items() if v),
        "",
        "| # | Нужно (Рацион) | Товар 5ka | Фасовка | Кол-во | Цена | Сумма | Уверенность |",
        "|---|---|---|---|---|---|---|---|",
    ]
    group = None
    for i, m in enumerate(matches, 1):
        if m.need.group != group:
            group = m.need.group
            lines.append(f"| | **{group}** | | | | | | |")
        b = m.best
        if b:
            now, regular = price_of(b.product)
            price = _money(now) + (f" ~~{_money(regular)}~~" if regular and now and now < regular else "")
            lines.append(f"| {i} | {_need_label(m)} | [{b.name}]({b.url}) | {b.pack_label} | {b.qty_label} | "
                         f"{price} | {_money(b.cost)} | {MARK[m.confidence]} |")
        else:
            lines.append(f"| {i} | {_need_label(m)} | — | | | | | {MARK['none']} |")
    lines += [
        "",
        f"**Итого по 5ka: {_money(total)} ₽** (оценка Рациона по этим же позициям: {_money(racion_total)} ₽)",
        "",
    ]

    doubtful = [m for m in matches if m.confidence in ("medium", "low", "none")]
    if doubtful:
        lines += ["## Проверить", ""]
        for m in doubtful:
            lines.append(f"**{_need_label(m)}**: {MARK[m.confidence]}. Запрос «{m.query}». {m.reason}")
            for o in m.alternatives:
                lines.append(f"- {_opt_short(o)}")
            lines.append("")
        lines.append("Чтобы закрепить выбор, допиши в config.toml: `[ingredients.<id>] plu = \"…\"`, "
                     "а чтобы поменять поиск: `query = \"…\"`. id позиций указаны в CSV.")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with cs.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ingredient_id", "group", "need", "need_unit", "query", "plu", "product", "pack", "qty",
                    "price", "sum", "confidence", "url", "note", "alt_plu", "alt_names"])
        for m in matches:
            b = m.best
            now = price_of(b.product)[0] if b else None
            w.writerow([
                m.need.key, m.need.group, m.need.needed or m.need.qty_text, m.need.unit, m.query,
                b.plu if b else "", b.name if b else "", b.pack_label if b else "",
                b.qty if b else "", now or "", b.cost if b and b.cost is not None else "",
                m.confidence, b.url if b else "", m.reason,
                " | ".join(o.plu for o in m.alternatives), " | ".join(o.name for o in m.alternatives),
            ])
    return md, cs
