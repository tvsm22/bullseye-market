"""Render a screen draw-list to PNG the way the device does, for previewing."""

import importlib.util
import json
import sys

from PIL import Image, ImageDraw, ImageFont

spec = importlib.util.spec_from_file_location("u", ".github/scripts/update_screen.py")
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)

# The device draws with the Adafruit GFX 6x8 bitmap font, scaled by s.
FONT = ImageFont.load_default()


def draw_text(d, p):
    x, y, s = p["x"], p["y"], p.get("s", 1)
    v, c = p["v"], p["c"]
    tmp = Image.new("RGB", (len(v) * 6, 8), (0, 0, 0))
    ImageDraw.Draw(tmp).text((0, 0), v, font=FONT, fill=c)
    tmp = tmp.resize((len(v) * 6 * s, 8 * s), Image.NEAREST)
    d.bitmap((x, y), tmp.convert("L").point(lambda q: 255 if q > 40 else 0, mode="1"), fill=c)


def draw_icon(d, p):
    x, y, s, c = p["x"], p["y"], p.get("s", 1), p["c"]
    box = 24 * s
    cx = x + box // 2
    if p["v"] == "arrow-up":
        d.polygon([(cx, y + 4 * s), (x + 4 * s, y + box - 6 * s), (x + box - 4 * s, y + box - 6 * s)], fill=c)
    elif p["v"] == "arrow-down":
        d.polygon([(cx, y + box - 4 * s), (x + 4 * s, y + 6 * s), (x + box - 4 * s, y + 6 * s)], fill=c)


def render(screen, path):
    img = Image.new("RGB", (240, 240), screen.get("bg", "#000000"))
    d = ImageDraw.Draw(img)
    for p in screen["draw"]:
        t = p["t"]
        if t == "fill":
            d.rectangle([0, 0, 239, 239], fill=p["c"])
        elif t == "rect":
            d.rectangle([p["x"], p["y"], p["x"] + p["w"] - 1, p["y"] + p["h"] - 1], fill=p["c"])
        elif t == "circle":
            r = p["r"]
            d.ellipse([p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r], fill=p["c"])
        elif t == "line":
            d.line([p["x"], p["y"], p["x2"], p["y2"]], fill=p["c"])
        elif t == "text":
            draw_text(d, p)
        elif t == "icon":
            draw_icon(d, p)
    img.save(path)
    print("wrote", path)


if __name__ == "__main__":
    btc_price, btc_chg = u.fetch_btc()
    imoex_price, imoex_chg = u.fetch_imoex()
    try:
        moex_open = u.fetch_moex_is_open()
    except Exception:
        moex_open = None

    normal = u.build_screen(btc_price, btc_chg, imoex_price, imoex_chg, moex_open, None)
    egg = u.build_screen(btc_price, btc_chg, imoex_price, imoex_chg, moex_open, "BULLSEYE QUEEN")

    for name, screen in (("preview_normal.png", normal), ("preview_egg.png", egg)):
        payload = json.dumps(screen, separators=(",", ":"))
        print(name, len(payload), "bytes")
        render(screen, name)
