"""
cogs/welcome.py – Boas-vindas com 2 canais + DM guia automático
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
_FALLBACK_ACCENT = (88, 101, 242)


def _load_font(paths, size):
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _circle_crop(img, size):
    img = img.resize((size, size), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, mask=mask)
    return out


def _text_width(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0]


def _draw_rounded_rect(draw, xy, radius, fill):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill)


def _gradient_overlay(size):
    W, H = size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for x in range(W):
        t = x / W
        alpha = int(210 * (1 - t) + 80 * t)
        draw.line([(x, 0), (x, H)], fill=(15, 16, 20, alpha))
    return overlay


def _avg_color_from_bytes(data):
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB").resize((32, 32), Image.LANCZOS)
        pixels = list(img.getdata())
        r = sum(p[0] for p in pixels) // len(pixels)
        g = sum(p[1] for p in pixels) // len(pixels)
        b = sum(p[2] for p in pixels) // len(pixels)
        gray = (r + g + b) // 3
        factor = 1.8
        r = max(0, min(255, int(gray + factor * (r - gray))))
        g = max(0, min(255, int(gray + factor * (g - gray))))
        b = max(0, min(255, int(gray + factor * (b - gray))))
        return (r, g, b)
    except Exception:
        return _FALLBACK_ACCENT


def _ordinal_pt(n):
    return f"{n}º"


async def _build_welcome_image(member, guild, bg_url=""):
    W, H = 800, 200
    AV_SIZE = 90
    PAD = 24

    avatar_bytes = None
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

    accent_rgb = _avg_color_from_bytes(avatar_bytes) if avatar_bytes else _FALLBACK_ACCENT

    bg_raw = None
    if bg_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(bg_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        bg_raw = await resp.read()
        except Exception:
            pass

    if bg_raw:
        bg_img = Image.open(io.BytesIO(bg_raw)).convert("RGBA").resize((W, H), Image.LANCZOS)
        bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=3))
        card = bg_img.copy()
    else:
        card = Image.new("RGBA", (W, H), (18, 19, 24, 255))
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        cx, cy = W // 5, H // 2
        for r in range(160, 0, -1):
            alpha = int(60 * (1 - r / 160))
            gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent_rgb + (alpha,))
        card = Image.alpha_composite(card, glow)

    card = Image.alpha_composite(card, _gradient_overlay((W, H)))

    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _draw_rounded_rect(ImageDraw.Draw(panel), (PAD // 2, PAD // 2, W - PAD // 2, H - PAD // 2), 16, (0, 0, 0, 80))
    card = Image.alpha_composite(card, panel)

    stripe = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(stripe).rounded_rectangle([PAD // 2, PAD // 2, PAD // 2 + 5, H - PAD // 2], radius=3, fill=accent_rgb + (230,))
    card = Image.alpha_composite(card, stripe)

    draw = ImageDraw.Draw(card)
    font_title = _load_font(_BOLD_PATHS, 15)
    font_name = _load_font(_BOLD_PATHS, 28)
    font_sub = _load_font(_REGULAR_PATHS, 15)
    font_count = _load_font(_REGULAR_PATHS, 14)

    av_x = PAD + 14
    av_y = (H - AV_SIZE) // 2

    ring_size = AV_SIZE + 6
    ring_img = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
    ImageDraw.Draw(ring_img).ellipse((0, 0, ring_size - 1, ring_size - 1), fill=accent_rgb + (255,))
    card.paste(ring_img, (av_x - 3, av_y - 3), ring_img)

    sep_size = AV_SIZE + 2
    sep_img = Image.new("RGBA", (sep_size, sep_size), (0, 0, 0, 0))
    ImageDraw.Draw(sep_img).ellipse((0, 0, sep_size - 1, sep_size - 1), fill=(18, 19, 24, 255))
    card.paste(sep_img, (av_x - 1, av_y - 1), sep_img)

    av_img = Image.open(io.BytesIO(avatar_bytes)) if avatar_bytes else Image.new("RGB", (AV_SIZE, AV_SIZE), accent_rgb)
    card.paste(_circle_crop(av_img, AV_SIZE), (av_x, av_y), _circle_crop(av_img, AV_SIZE))

    tx = av_x + AV_SIZE + 22
    row1_y = H // 2 - 46
    row2_y = H // 2 - 16
    row3_y = H // 2 + 22

    draw.text((tx, row1_y), "Bem-vindo(a) ao servidor!", font=font_title, fill=(200, 202, 220, 230))

    name = member.display_name
    max_name_w = W - tx - PAD - 10
    while _text_width(draw, name, font_name) > max_name_w and len(name) > 3:
        name = name[:-1]
    if name != member.display_name:
        name = name[:-1] + "…"

    draw.text((tx + 1, row2_y + 1), name, font=font_name, fill=(0, 0, 0, 120))
    draw.text((tx, row2_y), name, font=font_name, fill=(255, 255, 255, 255))

    member_count = guild.member_count or 0
    count_text = f"Você é o {_ordinal_pt(member_count)} membro"
    badge_padding = (12, 6)
    badge_w = _text_width(draw, count_text, font_count) + badge_padding[0] * 2
    badge_h = 26
    badge_x0, badge_y0 = tx, row3_y
    badge_x1, badge_y1 = badge_x0 + badge_w, badge_y0 + badge_h

    badge_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(badge_layer).rounded_rectangle([badge_x0, badge_y0, badge_x1, badge_y1], radius=13, fill=accent_rgb + (200,))
    card = Image.alpha_composite(card, badge_layer)
    draw = ImageDraw.Draw(card)
    draw.text((badge_x0 + badge_padding[0], badge_y0 + badge_padding[1] - 1), count_text, font=font_count, fill=(255, 255, 255, 255))

    srv_font = _load_font(_REGULAR_PATHS, 12)
    srv_w = _text_width(draw, guild.name, srv_font)
    draw.text((W - PAD - srv_w, H - PAD + 2), guild.name, font=srv_font, fill=(160, 163, 185, 180))

    buf = io.BytesIO()
    card.convert("RGB").save(buf, format="PNG", optimize=False)
    buf.seek(0)
    return buf


def _format_welcome_message(template, member):
    guild = member.guild
    return (
        template
        .replace("{user}", member.mention)
        .replace("{server}", guild.name)
        .replace("{count}", str(guild.member_count or "?"))
        .replace("{name}", member.display_name)
    )


def _build_dm_guide_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title=f"👋 Bem-vindo(a) ao {guild.name}!",
        description=(
            f"Ficamos felizes em ter você aqui em **{guild.name}**! 🎉\n\n"
            "Aqui vai um guia rápido para você começar:"
        ),
        color=BOT_COLOR,
    )
    embed.add_field(
        name="📖 Leia as Regras",
        value="Confira os canais de regras e informações do servidor antes de qualquer coisa.",
        inline=False,
    )
    embed.add_field(
        name="🪪 Seu Perfil",
        value="Use `/perfil ver` para ver seu card, `/perfil editar` para personalizar.",
        inline=False,
    )
    embed.add_field(
        name="💰 Economia",
        value="Use `/coinsdiarias` todo dia para ganhar moedas. Veja `/banco saldo` para conferir.",
        inline=False,
    )
    embed.add_field(
        name="🎫 Precisa de Ajuda?",
        value="Abra um ticket no servidor — nossa equipe está pronta para ajudar!",
        inline=False,
    )
    embed.add_field(
        name="📘 Guia Completo",
        value="Use `/guia` no servidor para ver todos os comandos disponíveis.",
        inline=False,
    )
    embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)
    embed.set_footer(text=f"Esta mensagem foi enviada automaticamente por {guild.name}")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


# ── Cog ───────────────────────────────────────────────────────────────────────

class Welcome(commands.Cog):
    """Sistema de boas-vindas com imagem personalizada, 2 canais e DM de guia."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        cfg = await self.bot.db.get_guild_config(member.guild.id)

        # ── Canal 1 ───────────────────────────────────────────────────────
        channel_id = cfg.get("welcome_channel_id") or 0
        if channel_id:
            channel = member.guild.get_channel(int(channel_id))
            if isinstance(channel, discord.TextChannel):
                bg_url = cfg.get("welcome_image_url") or ""
                try:
                    img_buf = await _build_welcome_image(member, member.guild, bg_url=bg_url)
                    await channel.send(file=discord.File(img_buf, filename="welcome.png"))
                except Exception:
                    pass
                template = cfg.get("welcome_message") or "Seja bem-vindo(a), {user}! Você é o {count}º membro de **{server}**."
                await channel.send(_format_welcome_message(template, member))

        # ── Canal 2 ───────────────────────────────────────────────────────
        channel2_id = cfg.get("welcome_channel2_id") or 0
        if channel2_id:
            channel2 = member.guild.get_channel(int(channel2_id))
            if isinstance(channel2, discord.TextChannel):
                bg_url2 = cfg.get("welcome_image_url2") or cfg.get("welcome_image_url") or ""
                try:
                    img_buf2 = await _build_welcome_image(member, member.guild, bg_url=bg_url2)
                    await channel2.send(file=discord.File(img_buf2, filename="welcome.png"))
                except Exception:
                    pass
                template2 = cfg.get("welcome_message2") or cfg.get("welcome_message") or "Seja bem-vindo(a), {user}! Você é o {count}º membro de **{server}**."
                await channel2.send(_format_welcome_message(template2, member))

        # ── DM de guia ────────────────────────────────────────────────────
        dm_enabled = cfg.get("welcome_dm_enabled", 1)
        if dm_enabled:
            try:
                dm_embed = _build_dm_guide_embed(member.guild)
                await member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass  # DMs fechadas — ignorar silenciosamente

    # ══════════════════════════════════════════════════════════════════════
    # /boas-vindas group
    # ══════════════════════════════════════════════════════════════════════

    bv = app_commands.Group(
        name="boas-vindas",
        description="Configurações de boas-vindas",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @bv.command(name="configurar", description="Configura os canais e mensagens de boas-vindas (suporta até 2 canais)")
    @app_commands.describe(
        canal="Canal principal de boas-vindas",
        mensagem="Mensagem do canal principal (use {user}, {server}, {count}, {name})",
        canal2="Segundo canal de boas-vindas (opcional)",
        mensagem2="Mensagem do segundo canal (opcional, usa a do canal 1 se vazia)",
        dm_guia="Enviar guia automático por DM ao novo membro (padrão: ativado)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bv_configurar(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        mensagem: Optional[str] = None,
        canal2: Optional[discord.TextChannel] = None,
        mensagem2: Optional[str] = None,
        dm_guia: bool = True,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        fields = {
            "welcome_channel_id": canal.id,
            "welcome_dm_enabled": int(dm_guia),
        }
        if mensagem:
            fields["welcome_message"] = mensagem
        if canal2:
            fields["welcome_channel2_id"] = canal2.id
        if mensagem2:
            fields["welcome_message2"] = mensagem2

        await self.bot.db.set_guild_config(interaction.guild.id, **fields)

        preview_msg = mensagem or "Seja bem-vindo(a), {user}! Você é o {count}º membro de **{server}**."
        preview_rendered = _format_welcome_message(preview_msg, interaction.user)

        embed = discord.Embed(title="✅ Boas-vindas Configuradas", color=SUCCESS_COLOR, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="📢 Canal 1", value=canal.mention, inline=True)
        embed.add_field(name="📢 Canal 2", value=canal2.mention if canal2 else "—", inline=True)
        embed.add_field(name="✉️ DM Guia", value="✅ Ativado" if dm_guia else "❌ Desativado", inline=True)
        embed.add_field(name="Mensagem Canal 1", value=f"```{mensagem or '(padrão)'}```", inline=False)
        if canal2:
            embed.add_field(name="Mensagem Canal 2", value=f"```{mensagem2 or '(igual ao canal 1)'}```", inline=False)
        embed.add_field(name="Pré-visualização", value=preview_rendered, inline=False)
        embed.set_footer(text="Placeholders: {user} {server} {count} {name}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @bv.command(name="imagem", description="Define a imagem de fundo do cartão de boas-vindas")
    @app_commands.describe(
        url="URL da imagem para o canal 1",
        url2="URL da imagem para o canal 2 (opcional)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bv_imagem(self, interaction: discord.Interaction, url: Optional[str] = None, url2: Optional[str] = None) -> None:
        await interaction.response.defer(ephemeral=True)
        fields = {}
        if url is not None:
            if url and not url.startswith(("http://", "https://")):
                return await interaction.followup.send(embed=discord.Embed(description="❌ URL 1 inválida.", color=ERROR_COLOR), ephemeral=True)
            fields["welcome_image_url"] = url or ""
        if url2 is not None:
            if url2 and not url2.startswith(("http://", "https://")):
                return await interaction.followup.send(embed=discord.Embed(description="❌ URL 2 inválida.", color=ERROR_COLOR), ephemeral=True)
            fields["welcome_image_url2"] = url2 or ""
        if not fields:
            return await interaction.followup.send("Informe pelo menos uma URL.", ephemeral=True)
        await self.bot.db.set_guild_config(interaction.guild.id, **fields)
        embed = discord.Embed(title="🖼️ Imagens Atualizadas", color=SUCCESS_COLOR)
        if url:
            embed.set_image(url=url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @bv.command(name="testar", description="Simula uma entrada no servidor para visualizar o cartão")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bv_testar(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=False)
        cfg = await self.bot.db.get_guild_config(interaction.guild.id)
        bg_url = cfg.get("welcome_image_url") or ""
        try:
            img_buf = await _build_welcome_image(interaction.user, interaction.guild, bg_url=bg_url)
            file = discord.File(img_buf, filename="welcome_preview.png")
        except Exception as exc:
            return await interaction.followup.send(
                embed=discord.Embed(title="❌ Erro ao gerar imagem", description=f"```{exc}```", color=ERROR_COLOR), ephemeral=True
            )
        template = cfg.get("welcome_message") or "Seja bem-vindo(a), {user}! Você é o {count}º membro de **{server}**."
        text = _format_welcome_message(template, interaction.user)
        ch1 = interaction.guild.get_channel(cfg.get("welcome_channel_id") or 0)
        ch2 = interaction.guild.get_channel(cfg.get("welcome_channel2_id") or 0)
        embed = discord.Embed(
            title="🔍 Pré-visualização das Boas-vindas",
            description=f"**Canal 1:** {ch1.mention if ch1 else '—'}\n**Canal 2:** {ch2.mention if ch2 else '—'}\n\n**Mensagem:**\n{text}",
            color=BOT_COLOR,
        )
        embed.set_image(url="attachment://welcome_preview.png")
        embed.set_footer(text="Simulação — DM também seria enviada ao membro real.")
        await interaction.followup.send(embed=embed, file=file)

        # Simula DM
        try:
            dm_embed = _build_dm_guide_embed(interaction.guild)
            await interaction.user.send(content="*(Esta é uma prévia da DM de boas-vindas)*", embed=dm_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @bv.command(name="desativar", description="Desativa um ou ambos os canais de boas-vindas")
    @app_commands.describe(canal="Qual canal desativar: 1, 2 ou ambos")
    @app_commands.choices(canal=[
        app_commands.Choice(name="Canal 1", value="1"),
        app_commands.Choice(name="Canal 2", value="2"),
        app_commands.Choice(name="Ambos", value="ambos"),
    ])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bv_desativar(self, interaction: discord.Interaction, canal: str = "ambos") -> None:
        await interaction.response.defer(ephemeral=True)
        fields = {}
        if canal in ("1", "ambos"):
            fields["welcome_channel_id"] = 0
        if canal in ("2", "ambos"):
            fields["welcome_channel2_id"] = 0
        await self.bot.db.set_guild_config(interaction.guild.id, **fields)
        embed = discord.Embed(title="🔕 Boas-vindas Desativadas", description=f"Canal(is) desativado(s): **{canal}**", color=WARNING_COLOR)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @bv.command(name="info", description="Exibe as configurações atuais de boas-vindas")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bv_info(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        cfg = await self.bot.db.get_guild_config(interaction.guild.id)

        ch1_id = cfg.get("welcome_channel_id") or 0
        ch2_id = cfg.get("welcome_channel2_id") or 0
        ch1 = interaction.guild.get_channel(int(ch1_id)) if ch1_id else None
        ch2 = interaction.guild.get_channel(int(ch2_id)) if ch2_id else None

        embed = discord.Embed(title="ℹ️ Configurações de Boas-vindas", color=SUCCESS_COLOR if ch1_id else WARNING_COLOR, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Canal 1", value=ch1.mention if ch1 else "—", inline=True)
        embed.add_field(name="Canal 2", value=ch2.mention if ch2 else "—", inline=True)
        embed.add_field(name="DM Guia", value="✅ Ativo" if cfg.get("welcome_dm_enabled", 1) else "❌ Inativo", inline=True)
        msg1 = cfg.get("welcome_message") or "(padrão)"
        msg2 = cfg.get("welcome_message2") or "(igual ao canal 1)"
        embed.add_field(name="Mensagem Canal 1", value=f"```{msg1[:200]}```", inline=False)
        embed.add_field(name="Mensagem Canal 2", value=f"```{msg2[:200]}```", inline=False)
        img1 = cfg.get("welcome_image_url") or "—"
        img2 = cfg.get("welcome_image_url2") or "—"
        embed.add_field(name="Imagem Canal 1", value=img1[:80], inline=True)
        embed.add_field(name="Imagem Canal 2", value=img2[:80], inline=True)
        embed.set_footer(text="Use /boas-vindas configurar para alterar")
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def cog_app_command_error(self, interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(title="❌ Sem Permissão", description="Você precisa da permissão `Gerenciar Servidor`.", color=ERROR_COLOR)
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        raise error


async def setup(bot):
    await bot.add_cog(Welcome(bot))
