"""racion2cart: план racion.app → таблица товаров Пятёрочки (этап 1, только чтение).

    python -m r2c plan               список покупок из Рациона (5ka не нужен)
    python -m r2c probe              проверка 5ka: магазин доставки и пробный поиск
    python -m r2c match              сопоставление → out/table.md и out/table.csv
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tomllib
from pathlib import Path

from . import racion

ROOT = Path(__file__).resolve().parent.parent


def load_cfg(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"нет {path.name}: скопируй config.example.toml в config.toml и впиши ссылку на план")
    with path.open("rb") as f:
        return tomllib.load(f)


def cmd_plan(cfg: dict, args) -> None:
    plan, needs = racion.load(args.plan or cfg["plan"], cfg.get("include_pantry", False))
    group = None
    for n in needs:
        if n.group != group:
            group = n.group
            print(f"\n## {group}")
        qty = f"{n.needed:g} {n.unit}" if n.unit else n.qty_text
        print(f"  {n.key:22} {n.name:36} нужно {qty:>10}  (Рацион: {n.packs or ''}×{n.pack:g}, ~{n.racion_cost:g} ₽)")
    print(f"\nпозиций: {len(needs)}, оценка Рациона: {sum(n.racion_cost for n in needs):g} ₽")


async def _store(fk, cfg: dict) -> dict:
    if cfg.get("sap_code"):
        return {"sap_code": cfg["sap_code"], "shop_address": "(из config.toml)"}
    st = await fk.selected_store()
    if st:
        return st
    if cfg.get("address"):
        return await fk.store_by_address(cfg["address"])
    sys.exit("не знаю магазин: выставь адрес доставки на 5ka.ru в открывшемся окне или впиши address в config.toml")


async def cmd_probe(cfg: dict, args) -> None:
    from .fivka import FiveKa

    async with FiveKa(ROOT / ".profile", ROOT / ".cache", headless=args.headless) as fk:
        print("заголовки сайта:", fk.headers)
        print("выбран на сайте:", await fk.selected_store())
        if cfg.get("address"):
            print("по адресу из config:", await fk.store_by_address(cfg["address"]))
        st = await _store(fk, cfg)
        print("использую магазин:", st)
        for p in (await fk.search(st["sap_code"], args.query, cfg.get("mode", "delivery")))[:10]:
            print(f"  {p.get('plu'):>8} | {p.get('name', '')[:60]:60} | {p.get('property_clarification')!s:>8} | "
                  f"{p.get('prices')} | uom={p.get('uom')} step={p.get('step')} | в наличии={p.get('is_available')}")
        if args.wait:
            input("Окно открыто: выставь адрес / залогинься, потом нажми Enter…")


async def cmd_match(cfg: dict, args) -> None:
    from .fivka import FiveKa
    from .matcher import match, query_for
    from .report import write

    plan, needs = racion.load(args.plan or cfg["plan"], cfg.get("include_pantry", False))
    skip = set(cfg.get("skip", []))
    needs = [n for n in needs if n.key not in skip]
    if args.only:
        only = set(args.only.split(","))
        needs = [n for n in needs if n.key in only]
    if args.limit:
        needs = needs[: args.limit]
    mode = cfg.get("mode", "delivery")

    async with FiveKa(ROOT / ".profile", ROOT / ".cache", headless=args.headless,
                      pause=tuple(cfg.get("pause_s", [1.5, 3.0]))) as fk:
        st = await _store(fk, cfg)
        print(f"магазин {st['sap_code']} {st.get('shop_address', '')}, позиций {len(needs)}")
        matches = []
        for i, n in enumerate(needs, 1):
            products = await fk.search(st["sap_code"], query_for(n, cfg), mode)
            m = match(n, products, cfg)
            matches.append(m)
            b = m.best
            print(f"[{i:>2}/{len(needs)}] {n.name[:28]:28} → {(b.name[:45] if b else '—'):45} {m.confidence}")
    md, cs = write(matches, ROOT / "out", st, plan)
    print(f"\nготово: {md}\n        {cs}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="r2c")
    ap.add_argument("cmd", choices=["plan", "probe", "match"])
    ap.add_argument("--config", default=str(ROOT / "config.toml"))
    ap.add_argument("--plan", help="ссылка на план, вместо plan из config.toml")
    ap.add_argument("--query", default="молоко 2,5%", help="probe: пробный запрос")
    ap.add_argument("--only", help="match: только эти ingredientId через запятую")
    ap.add_argument("--limit", type=int, help="match: первые N позиций (для пробы)")
    ap.add_argument("--headless", action="store_true", help="без окна (антибот пропускает хуже)")
    ap.add_argument("--wait", action="store_true", help="probe: не закрывать окно до Enter")
    args = ap.parse_args()
    cfg = load_cfg(Path(args.config))
    if args.cmd == "plan":
        cmd_plan(cfg, args)
    else:
        asyncio.run({"probe": cmd_probe, "match": cmd_match}[args.cmd](cfg, args))


if __name__ == "__main__":
    main()
