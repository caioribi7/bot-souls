"""
cogs/welcome.py  –  Sistema de boas-vindas com imagem gerada dinamicamente
discord.py 2.x  •  app_commands (slash)  •  Mensagens em português
Requer: Pillow, aiohttp
"""

from __future__ import annotations

import io
import math
from datetime import datetime, timezone
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import BOT_COLOR, SUCCESS_COLOR, ERROR_COLOR, WARNING_COLOR

# ── Font paths (same as card_generator.py) ───────────────────────────────────

_BOLD_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
]
_REGULAR_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
]

_FALLBACK_ACCENT = (88, 101, 242)  # #5865F2


def _load_font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


# ── Pillow helpers ────────────────────────────────────────────────────────────

def _circle_crop(img: Image.Image, size: int) -> Image.Image:
    """Resize + circular mask."""
    img = img.resize((size, size), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, mask=mask)
    return out


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple,
) -> None:
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)


def _gradient_overlay(size: tuple[int, int]) -> Image.Image:
    """Create a left-to-right gradient overlay: opaque dark on left, lighter on right."""
    W, H = size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for x in range(W):
        # Alpha goes from 210 (left) to 100 (right) in first 2/3, then 100->80
        t = x / W
        alpha = int(210 * (1 - t) + 80 * t)
        draw.line([(x, 0), (x, H)], fill=(15, 16, 20, alpha))
    return overlay


def _avg_color_from_bytes(data: bytes) -> tuple[int, int, int]:
    """Compute a vibrant dominant color from image bytes. Falls back to #5865F2."""
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB").resize((32, 32), Image.LANCZOS)
        pixels = list(img.getdata())
        r = sum(p[0] for p in pixels) // len(pixels)
        g = sum(p[1] for p in pixels) // len(pixels)
        b = sum(p[2] for p in pixels) // len(pixels)
        # Boost saturation: amplify distance from gray
        gray = (r + g + b) // 3
        factor = 1.8
        r = max(0, min(255, int(gray + factor * (r - gray))))
        g = max(0, min(255, int(gray + factor * (g - gray))))
        b = max(0, min(255, int(gray + factor * (b - gray))))
        return (r, g, b)
    except Exception:
        return _FALLBACK_ACCENT


def _ordinal_pt(n: int) -> str:
    """Portuguese ordinal suffix: 1º, 2º, …"""
    return f"{n}º"


# ── Core image builder ────────────────────────────────────────────────────────

async def _build_welcome_image(
    member: discord.Member,
    guild: discord.Guild,
    bg_url: str = "",
) -> io.BytesIO:
    """
    Build an 800×200 welcome card.

    Layout:
        [left pad] [avatar 90px] [right: title / name / member count]
    Background: bg_url image (blurred+overlaid) or solid dark gradient.
    Returns a BytesIO PNG buffer.
    """
    W, H = 800, 200
    AV_SIZE = 90
    PAD = 24

    # ── Fetch avatar bytes ────────────────────────────────────────────────
    avatar_bytes: bytes | None = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                str(member.display_avatar.replace(size=256, format="png")),
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status == 200:
                    avatar_bytes = await resp.read()
    except Exception:
        pass

    # ── Derive accent color from avatar ──────────────────────────────────
    if avatar_bytes:
        accent_rgb = _avg_color_from_bytes(avatar_bytes)
    else:
        accent_rgb = _FALLBACK_ACCENT

    # ── Fetch background image ────────────────────────────────────────────
    bg_raw: bytes | None = None
    if bg_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    bg_url, timeout=aiohttp.ClientTimeout(total=8)
                ) as resp:
                    if resp.status == 200:
                        bg_raw = await resp.read()
        except Exception:
            pass

    # ── Build base card ───────────────────────────────────────────────────
    if bg_raw:
        bg_img = Image.open(io.BytesIO(bg_raw)).convert("RGBA")
        bg_img = bg_img.resize((W, H), Image.LANCZOS)
        # Slight blur to keep text readable
        bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=3))
        card = bg_img.copy()
    else:
        # Rich dark background with a subtle radial glow
        card = Image.new("RGBA", (W, H), (18, 19, 24, 255))
        # Subtle accent glow on the left third
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        cx, cy = W // 5, H // 2
        for r in range(160, 0, -1):
            alpha = int(60 * (1 - r / 160))
            glow_draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                fill=accent_rgb + (alpha,),
            )
        card = Image.alpha_composite(card, glow)

    # ── Gradient overlay ──────────────────────────────────────────────────
    overlay = _gradient_overlay((W, H))
    card = Image.alpha_composite(card, overlay)

    # ── Semi-transparent content panel ───────────────────────────────────
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    panel_draw = ImageDraw.Draw(panel)
    # Frosted-glass style dark panel covering most of the card
    _draw_rounded_rect(
        panel_draw,
        (PAD // 2, PAD // 2, W - PAD // 2, H - PAD // 2),
        radius=16,
        fill=(0, 0, 0, 80),
    )
    card = Image.alpha_composite(card, panel)

    # ── Accent stripe on the left edge ───────────────────────────────────
    stripe = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    stripe_draw = ImageDraw.Draw(stripe)
    stripe_draw.rounded_rectangle(
        [PAD // 2, PAD // 2, PAD // 2 + 5, H - PAD // 2],
        radius=3,
        fill=accent_rgb + (230,),
    )
    card = Image.alpha_composite(card, stripe)

    draw = ImageDraw.Draw(card)

    # ── Fonts ─────────────────────────────────────────────────────────────
    font_title = _load_font(_BOLD_PATHS, 15)
    font_name = _load_font(_BOLD_PATHS, 28)
    font_sub = _load_font(_REGULAR_PATHS, 15)
    font_count = _load_font(_REGULAR_PATHS, 14)

    # ── Avatar ────────────────────────────────────────────────────────────
    av_x = PAD + 14
    av_y = (H - AV_SIZE) // 2

    # Avatar ring (accent color)
    ring_size = AV_SIZE + 6
    ring_img = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
    ImageDraw.Draw(ring_img).ellipse(
        (0, 0, ring_size - 1, ring_size - 1),
        fill=accent_rgb + (255,),
    )
    card.paste(ring_img, (av_x - 3, av_y - 3), ring_img)

    # Inner white/dark separator ring
    sep_size = AV_SIZE + 2
    sep_img = Image.new("RGBA", (sep_size, sep_size), (0, 0, 0, 0))
    ImageDraw.Draw(sep_img).ellipse(
        (0, 0, sep_size - 1, sep_size - 1),
        fill=(18, 19, 24, 255),
    )
    card.paste(sep_img, (av_x - 1, av_y - 1), sep_img)

    if avatar_bytes:
        av_img = Image.open(io.BytesIO(avatar_bytes))
    else:
        av_img = Image.new("RGB", (AV_SIZE, AV_SIZE), accent_rgb)

    av_circle = _circle_crop(av_img, AV_SIZE)
    card.paste(av_circle, (av_x, av_y), av_circle)

    # ── Text layout ───────────────────────────────────────────────────────
    tx = av_x + AV_SIZE + 22
    # Vertical center: distribute 3 rows
    row1_y = H // 2 - 46   # "Bem-vindo(a) ao servidor!"
    row2_y = H // 2 - 16   # Display name
    row3_y = H // 2 + 22   # Member count

    # Row 1: title (slightly muted)
    title_text = "Bem-vindo(a) ao servidor!"
    draw.text((tx, row1_y), title_text, font=font_title, fill=(200, 202, 220, 230))

    # Row 2: display name (bold, white, truncated if needed)
    name = member.display_name
    max_name_w = W - tx - PAD - 10
    while _text_width(draw, name, font_name) > max_name_w and len(name) > 3:
        name = name[:-1]
    if name != member.display_name:
        name = name[:-1] + "…"

    # Subtle text shadow for depth
    draw.text((tx + 1, row2_y + 1), name, font=font_name, fill=(0, 0, 0, 120))
    draw.text((tx, row2_y), name, font=font_name, fill=(255, 255, 255, 255))

    # Row 3: member count badge
    member_count = guild.member_count or 0
    count_text = f"Você é o {_ordinal_pt(member_count)} membro"

    badge_padding = (12, 6)
    badge_w = _text_width(draw, count_text, font_count) + badge_padding[0] * 2
    badge_h = 26
    badge_x0 = tx
    badge_y0 = row3_y
    badge_x1 = badge_x0 + badge_w
    badge_y1 = badge_y0 + badge_h

    badge_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    badge_draw = ImageDraw.Draw(badge_layer)
    badge_draw.rounded_rectangle(
        [badge_x0, badge_y0, badge_x1, badge_y1],
        radius=13,
        fill=accent_rgb + (200,),
    )
    card = Image.alpha_composite(card, badge_layer)
    draw = ImageDraw.Draw(card)

    draw.text(
        (badge_x0 + badge_padding[0], badge_y0 + badge_padding[1] - 1),
        count_text,
        font=font_count,
        fill=(255, 255, 255, 255),
    )

    # ── Server name (subtle, bottom-right) ───────────────────────────────
    server_text = guild.name
    srv_font = _load_font(_REGULAR_PATHS, 12)
    srv_w = _text_width(draw, server_text, srv_font)
    draw.text(
        (W - PAD - srv_w, H - PAD + 2),
        server_text,
        font=srv_font,
        fill=(160, 163, 185, 180),
    )

    # ── Output ────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    card.convert("RGB").save(buf, format="PNG", optimize=False)
    buf.seek(0)
    return buf


# ── Welcome text formatter ────────────────────────────────────────────────────

def _format_welcome_message(template: str, member: discord.Member) -> str:
    guild = member.guild
    return (
        template
        .replace("{user}", member.mention)
        .replace("{server}", guild.name)
        .replace("{count}", str(guild.member_count or "?"))
    )


# ── Cog ───────────────────────────────────────────────────────────────────────

class Welcome(commands.Cog):
    """Sistema de boas-vindas com imagem personalizada."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── on_member_join ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        cfg = await self.bot.db.get_guild_config(member.guild.id)
        channel_id = cfg.get("welcome_channel_id") or 0
        if not channel_id:
            return

        channel = member.guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return

        bg_url = cfg.get("welcome_image_url") or ""

        try:
            img_buf = await _build_welcome_image(member, member.guild, bg_url=bg_url)
            file = discord.File(img_buf, filename="welcome.png")
            await channel.send(file=file)
        except Exception:
            pass  # Don't fail silently on image errors — image is optional

        # Text message
        template = cfg.get("welcome_message") or "Seja bem-vindo(a), {user}! Você é o {count}º membro de **{server}**."
        text = _format_welcome_message(template, member)
        await channel.send(text)

    # ══════════════════════════════════════════════════════════════════════
    # /boas-vindas  command group
    # ══════════════════════════════════════════════════════════════════════

    bv = app_commands.Group(
        name="boas-vindas",
        description="Configurações de boas-vindas",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    # ── /boas-vindas configurar ───────────────────────────────────────────

    @bv.command(name="configurar", description="Configura o canal e mensagem de boas-vindas")
    @app_commands.describe(
        canal="Canal onde as mensagens serão enviadas",
        mensagem="Mensagem de boas-vindas (use {user}, {server}, {count})",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bv_configurar(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        mensagem: Optional[str] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        fields: dict = {"welcome_channel_id": canal.id}
        if mensagem:
            fields["welcome_message"] = mensagem

        await self.bot.db.set_guild_config(interaction.guild.id, **fields)

        preview_msg = mensagem or "Seja bem-vindo(a), {user}! Você é o {count}º membro de **{server}**."
        preview_rendered = _format_welcome_message(preview_msg, interaction.user)  # type: ignore[arg-type]

        embed = discord.Embed(
            title="✅ Boas-vindas Configuradas",
            color=SUCCESS_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Canal", value=canal.mention, inline=True)
        embed.add_field(
            name="Mensagem",
            value=f"```{mensagem or '(padrão)'}```",
            inline=False,
        )
        embed.add_field(
            name="Pré-visualização",
            value=preview_rendered,
            inline=False,
        )
        embed.set_footer(text="Use {user}, {server} e {count} como placeholders.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /boas-vindas imagem ───────────────────────────────────────────────

    @bv.command(name="imagem", description="Define a imagem de fundo do cartão de boas-vindas")
    @app_commands.describe(url="URL da imagem de fundo (deixe em branco para remover)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bv_imagem(
        self,
        interaction: discord.Interaction,
        url: Optional[str] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if url:
            # Basic URL validation
            if not (url.startswith("http://") or url.startswith("https://")):
                return await interaction.followup.send(
                    embed=discord.Embed(
                        description="❌ URL inválida. Use um link HTTP(S) válido.",
                        color=ERROR_COLOR,
                    ),
                    ephemeral=True,
                )

        await self.bot.db.set_guild_config(
            interaction.guild.id,
            welcome_image_url=url or "",
        )

        embed = discord.Embed(
            title="🖼️ Imagem de Fundo Atualizada",
            color=SUCCESS_COLOR if url else WARNING_COLOR,
        )
        if url:
            embed.description = f"A imagem de fundo foi definida para:\n{url}"
            embed.set_image(url=url)
        else:
            embed.description = "A imagem de fundo personalizada foi removida. O cartão usará o fundo padrão."
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /boas-vindas testar ───────────────────────────────────────────────

    @bv.command(name="testar", description="Simula uma entrada no servidor para visualizar o cartão")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bv_testar(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)

        cfg = await self.bot.db.get_guild_config(interaction.guild.id)
        bg_url = cfg.get("welcome_image_url") or ""

        try:
            img_buf = await _build_welcome_image(
                interaction.user,  # type: ignore[arg-type]
                interaction.guild,
                bg_url=bg_url,
            )
            file = discord.File(img_buf, filename="welcome_preview.png")
        except Exception as exc:
            return await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ Erro ao gerar imagem",
                    description=f"```{exc}```",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        template = (
            cfg.get("welcome_message")
            or "Seja bem-vindo(a), {user}! Você é o {count}º membro de **{server}**."
        )
        text = _format_welcome_message(template, interaction.user)  # type: ignore[arg-type]

        embed = discord.Embed(
            title="🔍 Pré-visualização das Boas-vindas",
            description=f"**Mensagem de texto:**\n{text}",
            color=BOT_COLOR,
        )
        embed.set_image(url="attachment://welcome_preview.png")
        embed.set_footer(text="Esta é uma simulação — apenas você pode ver.")

        await interaction.followup.send(embed=embed, file=file, ephemeral=False)

    # ── /boas-vindas desativar ────────────────────────────────────────────

    @bv.command(name="desativar", description="Desativa as mensagens de boas-vindas")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bv_desativar(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        await self.bot.db.set_guild_config(interaction.guild.id, welcome_channel_id=0)

        embed = discord.Embed(
            title="🔕 Boas-vindas Desativadas",
            description="As mensagens de boas-vindas foram desativadas neste servidor.",
            color=WARNING_COLOR,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /boas-vindas info ─────────────────────────────────────────────────

    @bv.command(name="info", description="Exibe as configurações atuais de boas-vindas")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bv_info(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        cfg = await self.bot.db.get_guild_config(interaction.guild.id)
        channel_id = cfg.get("welcome_channel_id") or 0
        message = cfg.get("welcome_message") or "(padrão)"
        image_url = cfg.get("welcome_image_url") or "(nenhuma)"

        if channel_id:
            channel = interaction.guild.get_channel(int(channel_id))
            channel_val = channel.mention if channel else f"Canal removido (ID: {channel_id})"
            status = "✅ Ativo"
            color = SUCCESS_COLOR
        else:
            channel_val = "—"
            status = "🔕 Inativo"
            color = WARNING_COLOR

        embed = discord.Embed(
            title="ℹ️ Configurações de Boas-vindas",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Canal", value=channel_val, inline=True)
        embed.add_field(name="​", value="​", inline=True)  # spacer
        embed.add_field(
            name="Mensagem",
            value=f"```{message if len(message) <= 200 else message[:197] + '…'}```",
            inline=False,
        )
        embed.add_field(
            name="Imagem de fundo",
            value=image_url if len(image_url) <= 80 else image_url[:77] + "…",
            inline=False,
        )
        embed.set_footer(
            text="Use /boas-vindas configurar para alterar  •  /boas-vindas testar para pré-visualizar"
        )

        if cfg.get("welcome_image_url"):
            embed.set_thumbnail(url=cfg["welcome_image_url"])

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Shared error handler ──────────────────────────────────────────────

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            missing = ", ".join(f"`{p}`" for p in error.missing_permissions)
            embed = discord.Embed(
                title="❌ Sem Permissão",
                description=f"Você precisa da(s) permissão(ões): {missing}",
                color=ERROR_COLOR,
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        raise error


# ── Setup ─────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
