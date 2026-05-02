"""Gera um GIF animado (ou GIF de um frame) com texto destacado sobre fundo GIF (ex.: flores / anime)."""

from __future__ import annotations

import asyncio
import io
import math
import textwrap

import aiohttp
from PIL import Image, ImageDraw, ImageFont

CARD_W = 720
CARD_H = 400
BOTTOM_BAR = 190
TEXT_MAX_CHARS = 800
WRAP_WIDTH = 34
BODY_FONT_SIZE = 30
TITLE_FONT_SIZE = 20
OUTLINE_RADIUS = 3
MAX_LINES = 15
MAX_FRAMES = 24
FRAME_DURATION_MS_DEFAULT = 80
FRAME_DURATION_MIN = 50
FRAME_DURATION_MAX = 120

_FONT_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_BOLD:
        try:
            return ImageFont.truetype(p, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _line_height(draw: ImageDraw.ImageDraw, line: str, font: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), line, font=font)
    return max(26, bbox[3] - bbox[1] + 8)


def _text_width(draw: ImageDraw.ImageDraw, line: str, font: ImageFont.ImageFont) -> int:
    b = draw.textbbox((0, 0), line, font=font)
    return b[2] - b[0]


def _draw_outlined_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    outline_rgb: tuple[int, int, int] = (0, 0, 0),
    outline_steps: int = OUTLINE_RADIUS,
) -> None:
    x, y = xy
    for dx in range(-outline_steps, outline_steps + 1):
        for dy in range(-outline_steps, outline_steps + 1):
            if math.hypot(dx, dy) > outline_steps + 0.25:
                continue
            draw.text(
                (x + dx, y + dy),
                text,
                font=font,
                fill=outline_rgb + (255,),
            )
    draw.text((x, y), text, font=font, fill=fill)


def _draw_footer(img_rgba: Image.Image, msg: str) -> Image.Image:
    out = img_rgba.copy().convert("RGBA")
    h = out.height

    # Gradiente inferior mais forte para o texto destacar sobre flores/anime claros.
    overlay = Image.new("RGBA", out.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for ypx in range(h - BOTTOM_BAR, h):
        t = (ypx - (h - BOTTOM_BAR)) / max(1, BOTTOM_BAR - 1)
        alpha = int(120 + 135 * t)
        od.line([(0, ypx), (out.width, ypx)], fill=(14, 6, 22, alpha))
    out = Image.alpha_composite(out, overlay)

    font = _font(BODY_FONT_SIZE)
    hdr = _font(TITLE_FONT_SIZE)

    dummy = ImageDraw.Draw(Image.new("RGBA", (CARD_W, CARD_H)))
    body = msg.strip()[:TEXT_MAX_CHARS] if msg.strip() else "…"
    lines: list[str] = []
    for block in body.split("\n"):
        lines.extend(textwrap.wrap(block, width=WRAP_WIDTH) or [""])
    lines = lines[:MAX_LINES]

    max_w = CARD_W - 72
    for i, ln in enumerate(lines):
        while _text_width(dummy, ln, font) > max_w and len(ln) > 14:
            ln = ln[:-2] + "…"
        lines[i] = ln

    total_h = sum(_line_height(dummy, ln, font) for ln in lines)
    title_gap = TITLE_FONT_SIZE + 18
    block_h = title_gap + total_h + 36
    panel_top = max(40, h - block_h)

    panel = Image.new("RGBA", out.size, (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    pd.rounded_rectangle(
        [20, panel_top - 8, CARD_W - 20, h - 10],
        radius=22,
        fill=(18, 10, 32, 235),
        outline=(255, 255, 255, 90),
        width=3,
    )
    out = Image.alpha_composite(out, panel)

    draw = ImageDraw.Draw(out)
    start_y = panel_top + title_gap + 4
    cx = CARD_W // 2

    sub = "Mensagem anônima"
    hb = draw.textbbox((0, 0), sub, font=hdr)
    sx = CARD_W // 2 - (hb[2] - hb[0]) // 2
    sy = panel_top + 6
    title_fill = (255, 253, 200, 255)
    _draw_outlined_text(
        draw, (sx, sy), sub, hdr, fill=title_fill, outline_rgb=(160, 40, 80), outline_steps=2
    )

    yy = start_y
    body_fill = (255, 255, 255, 255)
    for line in lines:
        lh = _line_height(dummy, line, font)
        tw = _text_width(dummy, line, font)
        xy = (cx - tw // 2, yy)
        _draw_outlined_text(
            draw, xy, line, font, fill=body_fill, outline_rgb=(15, 5, 25), outline_steps=OUTLINE_RADIUS
        )
        yy += lh

    return out


async def _fetch_bytes(session: aiohttp.ClientSession | None, url: str, timeout_s: float = 20.0):
    owns_session = False
    if session is None:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_s))
        owns_session = True
    try:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()
    finally:
        if owns_session:
            await session.close()


def _static_fallback_gif(msg: str) -> io.BytesIO:
    base = Image.new("RGBA", (CARD_W, CARD_H), (45, 25, 55, 255))
    layer = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    dl = ImageDraw.Draw(layer)
    for yy in range(CARD_H):
        t = yy / CARD_H
        dl.line(
            [(0, yy), (CARD_W, yy)],
            fill=(
                int(235 - t * 40),
                int(160 + t * 50),
                int(200 + t * 35),
                255,
            ),
        )
    stamped = _draw_footer(Image.alpha_composite(base, layer.convert("RGBA")), msg)
    q = stamped.convert("RGB").quantize(colors=248, method=Image.Quantize.MEDIANCUT)
    buf = io.BytesIO()
    q.save(buf, format="GIF", optimize=True, duration=FRAME_DURATION_MS_DEFAULT, loop=0)
    buf.seek(0)
    return buf


async def build_anonymous_card(
    text: str,
    gif_url: str,
    *,
    session: aiohttp.ClientSession | None = None,
) -> io.BytesIO:
    """GIF em BytesIO pronto para `discord.File(fp, filename=\"anon.gif\")`."""
    txt = text.strip() or "Sem texto."

    try:
        raw = await asyncio.wait_for(_fetch_bytes(session, gif_url), timeout=25.0)
    except (asyncio.TimeoutError, aiohttp.ClientError, OSError):
        return _static_fallback_gif(txt)

    try:
        base = Image.open(io.BytesIO(raw))
    except OSError:
        return _static_fallback_gif(txt)

    n_frames = getattr(base, "n_frames", 1) or 1
    fc = min(n_frames, MAX_FRAMES)

    durations: list[int] = []
    frames_rgb: list[Image.Image] = []

    try:
        for i in range(fc):
            base.seek(i)
            dur = base.info.get("duration", FRAME_DURATION_MS_DEFAULT)
            dur = FRAME_DURATION_MS_DEFAULT if not dur else int(dur)
            dur = max(FRAME_DURATION_MIN, min(FRAME_DURATION_MAX, dur))
            durations.append(dur)

            frame_rgba = base.convert("RGBA")
            composite = Image.alpha_composite(
                Image.new("RGBA", frame_rgba.size, (255, 255, 255, 255)),
                frame_rgba,
            )
            composite = composite.resize((CARD_W, CARD_H), Image.Resampling.LANCZOS)
            stamped_rgba = _draw_footer(composite, txt)
            frames_rgb.append(stamped_rgba.convert("RGB"))

    finally:
        base.close()

    if not frames_rgb:
        return _static_fallback_gif(txt)

    buf = io.BytesIO()
    master = frames_rgb[0].quantize(colors=248, method=Image.Quantize.MEDIANCUT)

    quantized = [frames_rgb[0].quantize(palette=master, dither=Image.Dither.NONE)]
    for f in frames_rgb[1:]:
        quantized.append(f.quantize(palette=master, dither=Image.Dither.NONE))

    first, *tail = quantized
    duration_list = durations[: len(quantized)] or ([FRAME_DURATION_MS_DEFAULT] * len(quantized))
    kw: dict = {
        "format": "GIF",
        "optimize": True,
        "duration": duration_list if len(duration_list) > 1 else duration_list[0],
        "loop": 0,
        "disposal": 2,
    }
    if tail:
        kw["save_all"] = True
        kw["append_images"] = tail
    first.save(buf, **kw)
    buf.seek(0)
    return buf
