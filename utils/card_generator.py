import io
import aiohttp
from PIL import Image, ImageDraw, ImageFont

# ── Theme definitions ─────────────────────────────────────────────────────────

THEMES: dict[str, dict] = {
    "escuro": {
        "bg":        (30, 32, 36),
        "text":      (255, 255, 255, 255),
        "subtext":   (175, 178, 195, 255),
        "bar_bg":    (52, 54, 68, 210),
        "badge2":    (68, 70, 88, 225),
        "badge3":    (50, 52, 66, 225),
        "overlay":   (0, 0, 0, 170),
        "footer":    (95, 98, 120, 210),
        "xp_text":   (225, 228, 235, 225),
        "bio":       (182, 185, 200, 255),
        "divider_a": 75,
        "ring":      (255, 255, 255, 255),
    },
    "claro": {
        "bg":        (235, 238, 245),
        "text":      (15, 15, 25, 255),
        "subtext":   (60, 62, 80, 255),
        "bar_bg":    (185, 188, 210, 210),
        "badge2":    (172, 176, 198, 225),
        "badge3":    (158, 162, 185, 225),
        "overlay":   (255, 255, 255, 155),
        "footer":    (125, 128, 150, 210),
        "xp_text":   (30, 32, 50, 225),
        "bio":       (70, 72, 90, 255),
        "divider_a": 130,
        "ring":      (60, 60, 80, 255),
    },
}

# ── Preset color palette ──────────────────────────────────────────────────────

COLOR_PRESETS: dict[str, tuple[str, str]] = {
    "Discord":    ("💜", "#5865F2"),
    "Verde":      ("💚", "#57F287"),
    "Vermelho":   ("❤️",  "#ED4245"),
    "Amarelo":    ("💛", "#FEE75C"),
    "Azul":       ("🩵", "#3BA3EB"),
    "Laranja":    ("🧡", "#FF7043"),
    "Rosa":       ("🩷", "#FF69B4"),
    "Ciano":      ("🔵", "#00BCD4"),
    "Ouro":       ("🌟", "#FFD700"),
    "Branco":     ("🤍", "#FFFFFF"),
    "Preto":      ("🖤", "#23272A"),
    "Roxo":       ("🟣", "#9B59B6"),
}

# ── Font paths ────────────────────────────────────────────────────────────────

_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
]
_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
]


def _font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _circle_crop(img: Image.Image, size: int) -> Image.Image:
    img = img.resize((size, size), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, mask=mask)
    return out


async def _fetch_raw(url: str) -> bytes | None:
    if not url:
        return None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    return await r.read()
    except Exception:
        return None


def _tw(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


# ── Core frame renderer ───────────────────────────────────────────────────────

def _render_frame(
    bg: Image.Image | None,
    avatar: Image.Image,
    icon: Image.Image | None,
    username: str,
    level: int,
    current_xp: int,
    xp_needed: int,
    total_xp: int,
    rank: int,
    messages: int,
    bio: str,
    accent_rgb: tuple[int, int, int],
    t: dict,            # theme dict
    bg_color: tuple,    # fallback solid bg
    fonts: dict,
) -> Image.Image:
    W, H = 900, 290
    AV = 128
    PAD = 30

    # Background
    if bg is not None:
        base = bg.resize((W, H), Image.LANCZOS).convert("RGBA")
        overlay = Image.new("RGBA", (W, H), t["overlay"])
        card = Image.alpha_composite(base, overlay)
    else:
        card = Image.new("RGBA", (W, H), bg_color + (255,))

    draw = ImageDraw.Draw(card)

    # Side accent stripe
    draw.rectangle([(0, 0), (6, H)], fill=accent_rgb + (255,))

    # Avatar position
    ax = PAD + 6
    ay = (H - AV) // 2

    # Avatar border ring
    bsz = AV + 8
    ring_img = Image.new("RGBA", (bsz, bsz), (0, 0, 0, 0))
    ImageDraw.Draw(ring_img).ellipse((0, 0, bsz - 1, bsz - 1), fill=accent_rgb + (255,))
    card.paste(ring_img, (ax - 4, ay - 4), ring_img)

    # Avatar
    av_circle = _circle_crop(avatar, AV)
    card.paste(av_circle, (ax, ay), av_circle)

    # Badge icon (bottom-right of avatar)
    if icon is not None:
        ic = _circle_crop(icon, 38)
        bx, by = ax + AV - 38, ay + AV - 38
        ring2 = Image.new("RGBA", (44, 44), (0, 0, 0, 0))
        ImageDraw.Draw(ring2).ellipse((0, 0, 43, 43), fill=t["ring"])
        card.paste(ring2, (bx - 3, by - 3), ring2)
        card.paste(ic, (bx, by), ic)

    # Text X start
    tx = ax + AV + 22

    # Username
    draw.text((tx, 38), username[:24], font=fonts["name"], fill=t["text"])

    # Stat badges
    badge_y = 83
    xc = tx
    badges = [
        (f"Nível {level}", accent_rgb + (225,)),
        (f"Rank #{rank}",  t["badge2"]),
        (f"💬 {messages:,}", t["badge3"]),
    ]
    for label, fill in badges:
        tw = _tw(draw, label, fonts["label"]) + 20
        draw.rounded_rectangle([xc, badge_y, xc + tw, badge_y + 26], radius=13, fill=fill)
        draw.text((xc + 10, badge_y + 4), label, font=fonts["label"], fill=t["text"])
        xc += tw + 8

    # XP bar
    bar_y, bar_h = 124, 24
    bar_w = W - tx - PAD
    draw.rounded_rectangle([tx, bar_y, tx + bar_w, bar_y + bar_h], radius=12, fill=t["bar_bg"])

    progress = min(current_xp / xp_needed, 1.0) if xp_needed > 0 else 0
    fp = int(bar_w * progress)
    if fp > 12:
        draw.rounded_rectangle([tx, bar_y, tx + fp, bar_y + bar_h], radius=12,
                                fill=accent_rgb + (255,))
        shine = tuple(min(255, c + 55) for c in accent_rgb) + (75,)
        draw.rounded_rectangle([tx + 2, bar_y + 2, tx + fp - 2, bar_y + bar_h // 2 + 1],
                                radius=8, fill=shine)

    xp_str = f"{current_xp:,} / {xp_needed:,} XP  •  Total: {total_xp:,}"
    xtw = _tw(draw, xp_str, fonts["xp"])
    draw.text((tx + (bar_w - xtw) // 2, bar_y + 5), xp_str,
              font=fonts["xp"], fill=t["xp_text"])

    # Bio
    if bio:
        draw.text((tx, 163), bio[:90] + ("…" if len(bio) > 90 else ""),
                  font=fonts["body"], fill=t["bio"])

    # Divider + footer
    dv = H - 40
    draw.line([(tx, dv), (W - PAD, dv)], fill=accent_rgb + (t["divider_a"],), width=1)
    draw.text((tx, dv + 8), "Community Bot", font=fonts["xp"], fill=t["footer"])

    return card


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_profile_card(
    username: str,
    avatar_url: str,
    level: int,
    current_xp: int,
    xp_needed: int,
    total_xp: int,
    rank: int,
    messages: int,
    bio: str,
    color: str = "#5865F2",
    banner_url: str = "",
    background_color: str = "#2C2F33",
    icon_url: str = "",
    theme: str = "escuro",
) -> tuple[io.BytesIO, str]:
    """
    Returns (buffer, extension) where extension is 'png' or 'gif'.
    Animated GIF banners produce an animated GIF output.
    """
    t = THEMES.get(theme, THEMES["escuro"])
    accent_rgb = _hex_to_rgb(color)
    bg_color = _hex_to_rgb(background_color)

    # Pre-load fonts once
    fonts = {
        "name":  _font(_BOLD,    30),
        "label": _font(_BOLD,    18),
        "body":  _font(_REGULAR, 16),
        "xp":    _font(_REGULAR, 14),
    }

    # Fetch raw bytes concurrently
    import asyncio
    avatar_bytes, banner_bytes, icon_bytes = await asyncio.gather(
        _fetch_raw(avatar_url),
        _fetch_raw(banner_url),
        _fetch_raw(icon_url) if icon_url else asyncio.sleep(0, result=None),
    )

    # Avatar image
    if avatar_bytes:
        avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    else:
        avatar_img = Image.new("RGBA", (128, 128), accent_rgb + (255,))

    # Icon image
    icon_img = None
    if icon_bytes:
        try:
            icon_img = Image.open(io.BytesIO(icon_bytes)).convert("RGBA")
        except Exception:
            pass

    # Banner frames (supports animated GIF)
    bg_frames: list[Image.Image | None] = [None]
    frame_durations: list[int] = [100]
    is_animated = False

    if banner_bytes:
        try:
            raw_banner = Image.open(io.BytesIO(banner_bytes))
            if getattr(raw_banner, "is_animated", False) and raw_banner.n_frames > 1:
                is_animated = True
                n = min(raw_banner.n_frames, 28)  # cap frames for file size
                bg_frames = []
                frame_durations = []
                for i in range(n):
                    raw_banner.seek(i)
                    bg_frames.append(raw_banner.copy().convert("RGBA"))
                    frame_durations.append(raw_banner.info.get("duration", 60))
            else:
                bg_frames = [raw_banner.convert("RGBA")]
        except Exception:
            bg_frames = [None]

    # Render each frame
    rendered: list[Image.Image] = []
    for frame in bg_frames:
        img = _render_frame(
            bg=frame,
            avatar=avatar_img,
            icon=icon_img,
            username=username,
            level=level,
            current_xp=current_xp,
            xp_needed=xp_needed,
            total_xp=total_xp,
            rank=rank,
            messages=messages,
            bio=bio,
            accent_rgb=accent_rgb,
            t=t,
            bg_color=bg_color,
            fonts=fonts,
        )
        rendered.append(img)

    buf = io.BytesIO()

    if is_animated:
        # Convert to P mode (palette) for GIF — FASTOCTREE gives best quality
        palette_frames = [f.convert("RGB").quantize(method=Image.Quantize.FASTOCTREE)
                          for f in rendered]
        palette_frames[0].save(
            buf,
            format="GIF",
            save_all=True,
            append_images=palette_frames[1:],
            loop=0,
            duration=frame_durations,
            optimize=False,
        )
        buf.seek(0)
        return buf, "gif"
    else:
        rendered[0].convert("RGB").save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf, "png"


async def generate_leaderboard_card(
    players: list[dict],
    theme: str = "escuro",
) -> io.BytesIO:
    players = players[:10]
    row_h = 70
    width = 800
    header_h = 60
    footer_h = 30
    height = header_h + (len(players) * row_h) + footer_h

    t = THEMES.get(theme, THEMES["escuro"])
    accent = _hex_to_rgb(players[0].get("color", "#5865F2")) if players else (88, 101, 242)

    fonts = {
        "title": _font(_BOLD, 24),
        "name": _font(_BOLD, 18),
        "small": _font(_REGULAR, 14),
        "badge": _font(_BOLD, 14),
        "rank": _font(_BOLD, 18),
        "footer": _font(_REGULAR, 12),
    }

    card = Image.new("RGBA", (width, height), t["bg"] + (255,))
    draw = ImageDraw.Draw(card)

    # Header
    for i in range(width):
        k = i / max(1, width - 1)
        r = int(accent[0] * (1 - k) + 45 * k)
        g = int(accent[1] * (1 - k) + 55 * k)
        b = int(accent[2] * (1 - k) + 90 * k)
        draw.line([(i, 0), (i, header_h)], fill=(r, g, b, 255))
    title = "🏆 LEADERBOARD"
    tw = _tw(draw, title, fonts["title"])
    draw.text(((width - tw) // 2, 16), title, font=fonts["title"], fill=(255, 255, 255, 255))

    # Avatar fetch
    import asyncio
    raws = await asyncio.gather(*[_fetch_raw(p.get("avatar_url", "")) for p in players])
    avatars: list[Image.Image | None] = []
    for raw in raws:
        if not raw:
            avatars.append(None)
            continue
        try:
            avatars.append(Image.open(io.BytesIO(raw)).convert("RGBA"))
        except Exception:
            avatars.append(None)

    # Rows
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    y = header_h
    for idx, p in enumerate(players, start=1):
        row_bg = (t["bg"][0] + 8, t["bg"][1] + 8, t["bg"][2] + 8, 255) if idx % 2 == 0 else (t["bg"][0], t["bg"][1], t["bg"][2], 255)
        draw.rectangle([(0, y), (width, y + row_h)], fill=row_bg)
        draw.line([(0, y + row_h - 1), (width, y + row_h - 1)], fill=t["subtext"])

        rank_label = medals.get(idx, f"#{idx}")
        draw.text((20, y + 24), rank_label, font=fonts["rank"], fill=t["text"])

        av = avatars[idx - 1]
        if av is None:
            fallback = Image.new("RGBA", (48, 48), _hex_to_rgb(p.get("color", "#5865F2")) + (255,))
            av_img = _circle_crop(fallback, 48)
        else:
            av_img = _circle_crop(av, 48)
        card.paste(av_img, (82, y + 11), av_img)

        username = str(p.get("username", "Usuário"))
        if len(username) > 18:
            username = username[:17] + "…"
        draw.text((145, y + 14), username, font=fonts["name"], fill=t["text"])

        color = _hex_to_rgb(p.get("color", "#5865F2"))
        badge = f"Nível {p.get('level', 0)}"
        bw = _tw(draw, badge, fonts["badge"]) + 16
        bx, by = 145, y + 38
        draw.rounded_rectangle([bx, by, bx + bw, by + 22], radius=11, fill=color + (230,))
        draw.text((bx + 8, by + 3), badge, font=fonts["badge"], fill=(255, 255, 255, 255))

        # XP bar visual (proporcional simples ao nível)
        bar_x, bar_y, bar_w, bar_h = 320, y + 30, 200, 12
        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=6, fill=t["bar_bg"])
        progress = min(1.0, (p.get("level", 0) % 10) / 10.0 + 0.1)
        fill = int(bar_w * progress)
        draw.rounded_rectangle([bar_x, bar_y, bar_x + fill, bar_y + bar_h], radius=6, fill=color + (255,))

        xp_text = f"{int(p.get('total_xp', 0)):,} XP"
        tw_xp = _tw(draw, xp_text, fonts["small"])
        draw.text((width - tw_xp - 20, y + 25), xp_text, font=fonts["small"], fill=t["subtext"])

        y += row_h

    # Footer
    draw.rectangle([(0, height - footer_h), (width, height)], fill=(0, 0, 0, 35))
    footer = "Community Bot"
    fw = _tw(draw, footer, fonts["footer"])
    draw.text(((width - fw) // 2, height - 21), footer, font=fonts["footer"], fill=t["subtext"])

    out = io.BytesIO()
    card.convert("RGB").save(out, format="PNG", optimize=True)
    out.seek(0)
    return out


async def generate_shop_card(
    guild_name: str,
    guild_icon_url: str,
    items: list[dict],
    custom_role_price: int,
    theme: str = "escuro",
) -> io.BytesIO:
    """Generate a visual shop panel image. Returns PNG BytesIO."""
    regular = [i for i in items if not i.get("is_custom")]

    ROW_H   = 72
    WIDTH   = 800
    HDR_H   = 86
    FTR_H   = 36

    custom_row = {
        "name": "Cargo Personalizado",
        "price": custom_role_price,
        "emoji": "✨",
        "description": "Crie seu proprio cargo com nome e cor personalizada!",
        "xp_multiplier": 1.0,
        "_custom": True,
    }
    
    display_rows = regular[:10]
    all_rows: list[dict] = display_rows + [custom_row]
    height = HDR_H + len(all_rows) * ROW_H + FTR_H

    t = THEMES.get(theme, THEMES["escuro"])

    fonts = {
        "title":  _font(_BOLD,    23),
        "sub":    _font(_REGULAR, 13),
        "name":   _font(_BOLD,    17),
        "price":  _font(_BOLD,    14),
        "desc":   _font(_REGULAR, 13),
        "badge":  _font(_BOLD,    12),
        "footer": _font(_REGULAR, 12),
    }

    icon_bytes = await _fetch_raw(guild_icon_url)
    icon_img: Image.Image | None = None
    if icon_bytes:
        try:
            icon_img = _circle_crop(Image.open(io.BytesIO(icon_bytes)).convert("RGBA"), 56)
        except Exception:
            pass

    card = Image.new("RGBA", (WIDTH, height), t["bg"] + (255,))
    draw = ImageDraw.Draw(card)

    # ── Header gradient (gold → orange) ──────────────────────────────────────
    c1 = (255, 186,  0)
    c2 = (255,  90,  0)
    for x in range(WIDTH):
        k = x / max(1, WIDTH - 1)
        rc = int(c1[0] * (1 - k) + c2[0] * k)
        gc = int(c1[1] * (1 - k) + c2[1] * k)
        bc = int(c1[2] * (1 - k) + c2[2] * k)
        draw.line([(x, 0), (x, HDR_H)], fill=(rc, gc, bc, 255))

    if icon_img:
        iy = (HDR_H - 56) // 2
        card.paste(icon_img, (16, iy), icon_img)

    title = "LOJA DE CARGOS"
    tw = _tw(draw, title, fonts["title"])
    draw.text(((WIDTH - tw) // 2, 12), title, font=fonts["title"], fill=(255, 255, 255, 255))

    n = len(regular)
    sub = (
        f"{n} {'item' if n == 1 else 'itens'} na loja (clique em 🛒 Ver Loja para comprar)"
    )
    stw = _tw(draw, sub, fonts["sub"])
    draw.text(((WIDTH - stw) // 2, 48), sub, font=fonts["sub"], fill=(255, 244, 200, 215))

    # ── Item rows ─────────────────────────────────────────────────────────────
    y = HDR_H
    for idx, item in enumerate(all_rows):
        alt = idx % 2 == 1
        bg_c = (t["bg"][0] + 9, t["bg"][1] + 9, t["bg"][2] + 12, 255) if alt else (t["bg"][0], t["bg"][1], t["bg"][2], 255)
        draw.rectangle([(0, y), (WIDTH, y + ROW_H)], fill=bg_c)

        if item.get("_custom"):
            accent = (155, 89, 182)
        elif (item.get("xp_multiplier") or 1.0) > 1.0:
            accent = (255, 183,   0)
        else:
            accent = (88, 101, 242)

        draw.rectangle([(0, y), (4, y + ROW_H)], fill=accent + (255,))

        dr = 13
        dcx, dcy = 24, y + ROW_H // 2
        draw.ellipse([(dcx - dr, dcy - dr), (dcx + dr, dcy + dr)], fill=accent + (195,))

        name_text = str(item.get("name", ""))[:32]
        draw.text((52, y + 12), name_text, font=fonts["name"], fill=t["text"])

        desc_text = str(item.get("description") or "")[:72]
        if desc_text:
            draw.text((52, y + 38), desc_text, font=fonts["desc"], fill=t["bio"])

        price = item.get("price", 0)
        price_str = f"{price:,} moedas"
        pw = _tw(draw, price_str, fonts["price"])
        bw = pw + 24
        bx = WIDTH - bw - 16
        by = y + (ROW_H - 28) // 2
        draw.rounded_rectangle([bx, by, bx + bw, by + 28], radius=14, fill=(255, 186, 0, 220))
        draw.text((bx + 12, by + 6), price_str, font=fonts["price"], fill=(30, 18, 0, 255))

        xp = item.get("xp_multiplier") or 1.0
        if xp > 1.0 and not item.get("_custom"):
            xp_str = f"XP x{xp:.1f}"
            xw = _tw(draw, xp_str, fonts["badge"])
            xbx = bx - xw - 28
            xby = by
            draw.rounded_rectangle([xbx, xby, xbx + xw + 16, xby + 28], radius=14, fill=(57, 242, 135, 205))
            draw.text((xbx + 8, xby + 6), xp_str, font=fonts["badge"], fill=(8, 50, 18, 255))

        draw.line([(6, y + ROW_H - 1), (WIDTH - 6, y + ROW_H - 1)], fill=accent + (22,))
        y += ROW_H

    # ── Footer ────────────────────────────────────────────────────────────────
    draw.rectangle([(0, height - FTR_H), (WIDTH, height)], fill=(0, 0, 0, 38))
    footer = f"Community Bot  •  {guild_name}"[:65]
    ftw = _tw(draw, footer, fonts["footer"])
    draw.text(((WIDTH - ftw) // 2, height - FTR_H + 11), footer, font=fonts["footer"], fill=t["subtext"])

    buf = io.BytesIO()
    card.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf
