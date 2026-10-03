"""Сопоставление позиции Рациона с товарами 5ka: название → фасовка → цена."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from .racion import Need

# Где названия Рациона и 5ka расходятся. Перекрывается [ingredients.<id>].query в config.toml.
DEFAULT_QUERIES = {
    "tomato": "томаты",
    "cherry_tomatoes": "томаты черри",
    "cucumber": "огурцы",
    "eggs": "яйца куриные",
    "milk": "молоко 2,5%",
    "ground_mixed": "фарш свино-говяжий",
    "cheese_hard": "сыр полутвердый",
    "cottage_soft": "творог мягкий",
    "lettuce": "салат листовой",
    "green_onion": "лук зеленый",
    "onion": "лук репчатый",
    "bell_pepper": "перец сладкий",
    "chicken_breast": "филе куриное грудки",
    "chicken_thigh": "бедро куриное",
    "liver_chicken": "печень куриная",
    "turkey_fillet": "филе индейки",
    "salmon_fillet": "филе лосося",
    "tomatoes_can": "томаты в собственном соку",
    "beans_can": "фасоль красная",
    "corn_can": "кукуруза консервированная",
    "tuna_can": "тунец консервированный",
    "shrimp": "креветки очищенные",
    "yogurt_plain": "йогурт натуральный",
    "yogurt_greek": "йогурт греческий",
    "bread_wholegrain": "хлеб цельнозерновой",
    "sausage_boiled": "колбаса вареная",
    "squid": "кальмар",
}

STOP = {"для", "без", "или", "из", "в", "с", "со", "и", "на", "по", "свежий", "свежая", "свежие"}
UNIT_RE = r"(кг|г|гр|л|мл|шт)\.?"
NUM = r"(\d+(?:[.,]\d+)?)"


def norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"\(.*?\)", " ", s)
    return re.sub(r"[^\w%,.\s-]", " ", s)


def stem(w: str) -> str:
    if len(w) > 5:
        return w[:5]
    return w[:-1] if len(w) > 3 else w


def words(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-zа-я]+", norm(s)) if len(w) >= 2 and w not in STOP]


def percent(s: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", s)
    return float(m.group(1).replace(",", ".")) if m else None


def parse_pack(text: str) -> tuple[float, str] | None:
    """«930 мл» → (930, ml); «6х100г» → (600, g); «1,5 кг» → (1500, g); «10 шт» → (10, pcs)."""
    t = norm(text)
    to_base = {"кг": (1000, "g"), "г": (1, "g"), "гр": (1, "g"), "л": (1000, "ml"), "мл": (1, "ml"), "шт": (1, "pcs")}
    m = list(re.finditer(rf"(\d+)\s*[xх×*]\s*{NUM}\s*{UNIT_RE}(?![a-zа-я])", t))
    if m:
        k, v, u = m[-1].groups()
        mul, base = to_base[u]
        return int(k) * float(v.replace(",", ".")) * mul, base
    m = list(re.finditer(rf"{NUM}\s*{UNIT_RE}(?![a-zа-я])", t))
    if m:
        v, u = m[-1].groups()
        mul, base = to_base[u]
        return float(v.replace(",", ".")) * mul, base
    return None


def price_of(p: dict) -> tuple[float | None, float | None]:
    """(цена сейчас, обычная цена). В поиске prices — словарь, в карточке — список."""
    pr = p.get("prices")
    if isinstance(pr, list):
        vals = {x.get("placement_type"): float(x["value"]) for x in pr if x.get("value")}
        regular = vals.get("regular_primary") or (min(vals.values()) if vals else None)
        return (min(vals.values()) if vals else None), regular
    pr = pr or {}
    regular = float(pr["regular"]) if pr.get("regular") else None
    cands = [float(pr[k]) for k in ("discount", "cpd_promo_price") if pr.get(k)]
    now = min(cands + ([regular] if regular else [])) if (cands or regular) else None
    return now, regular


@dataclass
class Option:
    product: dict
    relevance: float
    pack: tuple[float, str] | None
    loose: bool
    qty: float  # штук, или кг для весовых
    qty_label: str
    cost: float | None
    leftover: float  # сколько останется сверх needed, доля от needed
    note: str = ""

    @property
    def plu(self) -> str:
        return str(self.product.get("plu"))

    @property
    def name(self) -> str:
        return self.product.get("name", "")

    @property
    def url(self) -> str:
        return f"https://5ka.ru/product/{self.plu}/"

    @property
    def pack_label(self) -> str:
        if self.loose:
            return "весовой"
        return self.product.get("property_clarification") or (f"{self.pack[0]:g} {self.pack[1]}" if self.pack else "?")


@dataclass
class Match:
    need: Need
    query: str
    best: Option | None
    alternatives: list[Option] = field(default_factory=list)
    confidence: str = "low"  # high | medium | low | none
    reason: str = ""


def relevance(query: str, name: str, prefs: dict) -> float:
    q = [stem(w) for w in words(query)]
    if not q:
        return 0.0
    n_words = words(name)
    n_stems = [stem(w) for w in n_words]
    hit = sum(1 for s in q if any(ns.startswith(s) or s.startswith(ns) for ns in n_stems if len(ns) >= 3))
    r = hit / len(q)
    # главное слово запроса должно быть в начале названия: «сыр» ≠ «чипсы со вкусом сыра»
    if not any(ns.startswith(q[0]) or q[0].startswith(ns) for ns in n_stems[:2] if len(ns) >= 3):
        r *= 0.6
    qp, npct = percent(query), percent(name)
    if qp is not None and npct is not None and abs(qp - npct) > 0.05:
        r *= 0.5
    low = norm(name)
    if any(b.lower() in low for b in prefs.get("prefer_brands", [])):
        r += 0.1
    return min(r, 1.1)


def _qty(need: Need, p: dict, tolerance: float) -> tuple[float, str, float | None, float, tuple | None, bool, str]:
    """Сколько брать этого товара: (qty, подпись, стоимость, остаток, фасовка, весовой, заметка)."""
    now, _ = price_of(p)
    loose = (p.get("uom") or "").lower() in ("кг", "kg")
    goal = need.needed * (1 - tolerance)
    if loose:
        step = float(p.get("step") or p.get("initial_weight_step") or 0.1) or 0.1
        minw = float(p.get("min_weight") or step)
        kg = need.needed / 1000 if need.unit in ("g", "ml") else need.needed * 0.2
        q = round(max(minw, math.ceil(kg * (1 - tolerance) / step - 1e-9) * step), 3)
        note = "" if need.unit in ("g", "ml") else "штуки переведены в вес грубо (0,2 кг/шт)"
        return q, f"{q:g} кг", (now * q if now else None), (q - kg) / kg if kg else 0, None, True, note
    pack = parse_pack(p.get("property_clarification") or "") or parse_pack(p.get("name") or "")
    note = ""
    if pack is None or need.unit == "":
        return 1, "1 шт", now, 0, pack, False, "фасовка не распознана, взял 1 шт" if need.unit else ""
    amount, unit = pack
    if unit != need.unit:
        if {unit, need.unit} == {"g", "ml"}:
            note = "г≈мл"
        else:
            # нужно в граммах, а продают штуками (или наоборот): берём штуку и предупреждаем
            n = 1 if need.unit == "pcs" and unit != "pcs" else max(1, math.ceil(need.needed / 1000))
            return n, f"{n} шт", (now * n if now else None), 0, pack, False, f"нужно {need.needed:g} {need.unit}, продают «{p.get('property_clarification') or unit}»: проверь количество"
    n = max(1, math.ceil(goal / amount - 1e-9))
    leftover = (n * amount - need.needed) / need.needed if need.needed else 0
    return n, f"{n} шт", (now * n if now else None), leftover, pack, False, note


def query_for(need: Need, cfg: dict) -> str:
    over = cfg.get("ingredients", {}).get(need.key, {})
    return over.get("query") or DEFAULT_QUERIES.get(need.key) or re.sub(r"\(.*?\)", "", need.name).strip()


def match(need: Need, products: list[dict], cfg: dict) -> Match:
    over = cfg.get("ingredients", {}).get(need.key, {})
    query = query_for(need, cfg)
    prefs = {
        "prefer_brands": cfg.get("prefer_brands", []) + over.get("prefer_brands", []),
    }
    avoid = [norm(w) for w in cfg.get("avoid_words", []) + over.get("avoid_words", [])]
    tol = float(cfg.get("tolerance", 0.03))
    pin = str(over.get("plu") or "")

    opts: list[Option] = []
    for p in products:
        if p.get("is_available") is False:
            continue
        low = norm(p.get("name", ""))
        if any(a and a in low for a in avoid):
            continue
        rel = 1.2 if pin and str(p.get("plu")) == pin else relevance(query, p.get("name", ""), prefs)
        q, label, cost, left, pack, loose, note = _qty(need, p, tol)
        opts.append(Option(p, rel, pack, loose, q, label, cost, left, note))

    m = Match(need, query, None)
    if not opts:
        m.confidence, m.reason = "none", "ничего не нашлось"
        return m

    top = max(o.relevance for o in opts)
    band = [o for o in opts if o.relevance >= max(0.5, top - 0.15)] or sorted(opts, key=lambda o: -o.relevance)[:3]
    # фасовка «ближайшая ≥ нужного» (остаток корзинами по 25 %), затем цена, затем меньше упаковок
    band.sort(key=lambda o: (-(o.relevance >= 1.2), math.floor(o.leftover / 0.25),
                             o.cost if o.cost is not None else 1e9, o.qty))
    m.best = band[0]
    rest = sorted((o for o in opts if o is not m.best), key=lambda o: (-o.relevance, o.cost or 1e9))
    m.alternatives = rest[:3]

    b = m.best
    if b.relevance >= 1.2:
        m.confidence, m.reason = "high", "закреплён в config.toml"
    elif b.relevance >= 0.85 and not b.note and (b.pack or b.loose):
        m.confidence = "high"
    elif b.relevance >= 0.6:
        m.confidence = "medium"
    else:
        m.confidence = "low"
    if not m.reason:
        m.reason = "; ".join(x for x in (b.note, f"совпадение названия {b.relevance:.0%}") if x)
    if m.confidence == "high":
        m.alternatives = m.alternatives[:1]
    return m
