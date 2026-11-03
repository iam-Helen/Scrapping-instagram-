from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os, sys
OUT = sys.argv[1]
PHOTO = sys.argv[2]
W, H = 1080, 1350
FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Onest.ttf")
BOLD, XBOLD, MED, REG = 700, 800, 500, 400
def font(weight, size):
    f = ImageFont.truetype(FONT, size)
    f.set_variation_by_axes([weight])
    return f
CREAM = (247, 242, 234); INK = (28, 25, 23); ACCENT = (183, 84, 94); BROWN = (168, 143, 122)
HANDLE = "@ELENA_MYRLEN"

def wrap(draw, text, f, maxw):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= maxw: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def handle(draw, color=BROWN, y=1270):
    f = font(MED, 26)
    # letter-spaced handle
    text = HANDLE; sp = 3
    tw = sum(draw.textlength(c, font=f) for c in text) + sp * (len(text) - 1)
    x = (W - tw) / 2
    for c in text:
        draw.text((x, y), c, font=f, fill=color); x += draw.textlength(c, font=f) + sp

def arrow_tab(img):
    # dessin en 4x puis réduction : bords nets et lisses
    k = 4; y0, y1 = 615, 735; x0 = 990
    tw, th = (W - x0) * k, (y1 - y0) * k
    tab = Image.new("RGBA", (tw, th), (0, 0, 0, 0)); d = ImageDraw.Draw(tab)
    d.rounded_rectangle((0, 0, tw + 60 * k, th - 1), radius=36 * k, fill=BROWN + (255,))
    cx, cy, r = 50 * k, th // 2, 30 * k
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline="white", width=3 * k)
    d.line((cx - 13 * k, cy, cx + 13 * k, cy), fill="white", width=3 * k)
    d.line((cx + 3 * k, cy - 10 * k, cx + 14 * k, cy + 1 * k), fill="white", width=3 * k)
    d.line((cx + 3 * k, cy + 10 * k, cx + 14 * k, cy - 1 * k), fill="white", width=3 * k)
    tab = tab.resize((W - x0, y1 - y0), Image.LANCZOS)
    img.paste(tab, (x0, y0), tab)

def text_slide(paras, name, size=70, tab=True):
    """paras: list of (text, color, fontname, size or None)"""
    img = Image.new("RGB", (W, H), CREAM); d = ImageDraw.Draw(img)
    maxw = 860
    blocks = []
    for text, color, fname, sz in paras:
        f = font(fname, sz or size)
        lines = wrap(d, text, f, maxw)
        lh = int((sz or size) * 1.22)
        blocks.append((lines, f, color, lh))
    gap = int(size * 0.55)
    total = sum(len(l) * lh for l, _, _, lh in blocks) + gap * (len(blocks) - 1)
    y = (H - total) / 2 - 20
    for lines, f, color, lh in blocks:
        for ln in lines:
            tw = d.textlength(ln, font=f)
            d.text(((W - tw) / 2, y), ln, font=f, fill=color); y += lh
        y += gap
    handle(d)
    if tab: arrow_tab(img)
    img.save(os.path.join(OUT, name), quality=95)

def cover():
    src = Image.open(PHOTO).convert("RGB")
    bg = (158, 148, 139)
    crop = src.crop((800, 0, src.width, 2150))
    s = W / crop.width
    crop = crop.resize((W, int(crop.height * s)), Image.LANCZOS)
    img = Image.new("RGB", (W, H), bg)
    img.paste(crop, (0, 0))
    # fade photo bottom into background
    fade = 330; top = crop.height - fade
    grad = Image.new("L", (W, fade))
    for i in range(fade):
        ImageDraw.Draw(grad).line((0, i, W, i), fill=int(255 * (i / fade) ** 1.6))
    img.paste(Image.new("RGB", (W, fade), bg), (0, top), grad)
    d = ImageDraw.Draw(img)
    f = font(XBOLD, 112)
    lines = ["То, что вам", "не скажут", "друзья"]
    y = 800
    for ln in lines:
        d.text((70, y), ln, font=f, fill="white"); y += 112
    d.text((74, y + 22), "а психолог скажет", font=font(MED, 44), fill=(236, 230, 222))
    fh = font(MED, 26); x = 76; yh = 1268
    for c in HANDLE:
        d.text((x, yh), c, font=fh, fill="white"); x += d.textlength(c, font=fh) + 3
    img.save(os.path.join(OUT, "01_couverture.jpg"), quality=95)

cover()
slides = [
    ([("Вы не «слишком много чувствуете».", INK, BOLD, None),
      ("Вы слишком мало говорите о том, что чувствуете.", ACCENT, BOLD, None)], {}),
    ([("«Я не обижаюсь» часто значит", INK, BOLD, None),
      ("«я не верю, что мою обиду примут всерьёз»", ACCENT, BOLD, None)], {}),
    ([("«Я просто такой человек» чаще всего значит", INK, BOLD, None),
      ("«я не хочу ничего менять»", ACCENT, BOLD, None)], {}),
    ([("«Мне никто не нужен» часто значит", INK, BOLD, None),
      ("«я больше не хочу рисковать, что меня снова оставят»", ACCENT, BOLD, None)], {}),
    ([("Ждать, что человек изменится, – это тоже выбор.", INK, BOLD, None),
      ("Ваш.", ACCENT, XBOLD, 96)], {}),
    ([("Иногда усталость от людей –", INK, BOLD, None),
      ("это усталость от роли, которую вы при них играете.", ACCENT, BOLD, None)], {}),
    ([("Ощущению «я плохой человек»", INK, BOLD, None),
      ("обычно столько же лет, сколько вашим первым воспоминаниям.", ACCENT, BOLD, None)], {}),
    ([("Узнали", INK, XBOLD, 96), ("в чём-то себя?", ACCENT, XBOLD, 96)], {"tab": False, "size": 30}),
]
for i, (paras, kw) in enumerate(slides, start=2):
    text_slide(paras, f"{i:02d}.jpg", **kw)
print("ok")
