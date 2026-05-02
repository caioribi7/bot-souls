import io
import asyncio
import random
import time
import discord
from discord import app_commands
from discord.ext import commands
from config import BOT_COLOR, SUCCESS_COLOR, ERROR_COLOR, WARNING_COLOR, COIN_EMOJI, XP_EMOJI, LEVEL_EMOJI
from utils.card_generator import generate_leaderboard_card


def xp_for_level(level: int) -> int:
    """XP required to advance from `level` to `level+1`."""
    return 5 * (level ** 2) + 50 * level + 100


def compute_level(total_xp: int) -> tuple[int, int, int]:
    """Return (level, xp_in_current_level, xp_needed_for_next)."""
    level = 0
    accumulated = 0
    while True:
        needed = xp_for_level(level)
        if accumulated + needed > total_xp:
            return level, total_xp - accumulated, needed
        accumulated += needed
        level += 1


class Levels(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── XP on message ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        db = self.bot.db
        cfg = await db.get_guild_config(message.guild.id)
        now = time.time()

        user_data = await db.get_user(message.author.id, message.guild.id)
        if now - user_data["last_xp_ts"] < cfg["xp_cooldown"]:
            return

        # ── Multipliers ──────────────────────────────────────────────────
        role_ids = [r.id for r in message.author.roles]
        xp_multiplier = await db.get_xp_multiplier(message.guild.id, role_ids)

        godparent_bonus = 0.0
        try:
            from cogs.marriage import get_godparent_xp_bonus
            godparent_bonus = await get_godparent_xp_bonus(self.bot, message.author.id, message.guild.id)
        except Exception:
            pass

        clan_bonus = 0.0
        try:
            from cogs.clans import get_clan_xp_bonus
            clan_bonus = await get_clan_xp_bonus(self.bot, message.author.id, message.guild.id)
        except Exception:
            pass

        final_mult = xp_multiplier + godparent_bonus + clan_bonus
        xp_gain = int(random.randint(cfg["xp_min"], cfg["xp_max"]) * final_mult)
        coins_gain = cfg["coins_per_msg"]
        await db.add_xp(message.author.id, message.guild.id, xp_gain, coins_gain, now)

        # Re-fetch to get updated xp
        updated = await db.get_user(message.author.id, message.guild.id)
        new_level, _, _ = compute_level(updated["xp"])
        old_level = updated["level"]

        if new_level > old_level:
            await db.set_user_level(message.author.id, message.guild.id, new_level)
            await self._handle_level_up(message, new_level, cfg)

    async def _handle_level_up(
        self,
        message: discord.Message,
        new_level: int,
        cfg: dict,
    ):
        guild = message.guild
        member = message.author

        # Coin reward for leveling up
        coins_reward = new_level * cfg.get("level_coins_base", 100)
        await self.bot.db.add_coins(member.id, guild.id, coins_reward)

        # Determine channel
        channel_id = cfg["level_channel_id"]
        channel = guild.get_channel(channel_id) if channel_id else message.channel

        if channel:
            text = cfg["level_up_msg"].format(user=member.mention, level=new_level)

            # Fetch profile for card generation
            profile = await self.bot.db.get_profile(member.id)

            try:
                card_buf = await _build_levelup_card(
                    member=member,
                    level=new_level,
                    color=profile.get("color", "#5865F2"),
                    banner_url=profile.get("banner_url", ""),
                    background_color=profile.get("background_color", "#2C2F33"),
                    theme=profile.get("theme", "escuro"),
                )
                file = discord.File(card_buf, filename="levelup.png")
                try:
                    await channel.send(
                        content=f"{text}\n{COIN_EMOJI} +{coins_reward:,} Sweet Coins pelo nível {new_level}!",
                        file=file,
                    )
                except discord.Forbidden:
                    pass
            except Exception:
                # Fallback to plain embed if card generation fails
                embed = discord.Embed(description=text, color=BOT_COLOR)
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"{COIN_EMOJI} +{coins_reward:,} Sweet Coins pelo nível {new_level}!")
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

        # Assign level roles
        level_roles = await self.bot.db.get_level_roles(guild.id)
        for lr in level_roles:
            if lr["level"] <= new_level:
                role = guild.get_role(lr["role_id"])
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason=f"Level {lr['level']} atingido")
                    except discord.Forbidden:
                        pass

    # ── /rank ─────────────────────────────────────────────────────────────

    @app_commands.command(name="rank", description="Veja seu perfil de XP e nível")
    @app_commands.describe(membro="Membro para ver o rank (opcional)")
    async def rank(
        self,
        interaction: discord.Interaction,
        membro: discord.Member | None = None,
    ):
        await interaction.response.defer()
        target = membro or interaction.user

        db = self.bot.db
        user_data = await db.get_user(target.id, interaction.guild_id)
        profile = await db.get_profile(target.id)
        rank = await db.get_rank(target.id, interaction.guild_id)
        level, current_xp, xp_needed = compute_level(user_data["xp"])

        try:
            from utils.card_generator import generate_profile_card

            buf = await generate_profile_card(
                username=str(target.display_name),
                avatar_url=str(target.display_avatar.url),
                level=level,
                current_xp=current_xp,
                xp_needed=xp_needed,
                total_xp=user_data["xp"],
                rank=rank,
                messages=user_data["messages"],
                bio=profile["bio"],
                color=profile["color"],
                banner_url=profile["banner_url"],
                background_color=profile["background_color"],
                icon_url=profile["icon_url"],
            )
            # generate_profile_card returns (buf, ext)
            if isinstance(buf, tuple):
                buf, ext = buf
            else:
                ext = "png"
            file = discord.File(buf, filename=f"rank.{ext}")
            await interaction.followup.send(file=file)
        except Exception:
            accent = profile.get("color", "#5865F2")
            try:
                r, g, b = int(accent[1:3], 16), int(accent[3:5], 16), int(accent[5:7], 16)
                color_int = (r << 16) + (g << 8) + b
            except Exception:
                color_int = BOT_COLOR
            embed = discord.Embed(
                title=f"{LEVEL_EMOJI} Rank de {target.display_name}",
                color=color_int,
            )
            embed.add_field(name="Nível", value=str(level), inline=True)
            embed.add_field(name="Rank", value=f"#{rank}", inline=True)
            embed.add_field(
                name="XP",
                value=f"{current_xp:,} / {xp_needed:,} ({user_data['xp']:,} total)",
                inline=True,
            )
            embed.add_field(name="Mensagens", value=f"{user_data['messages']:,}", inline=True)
            embed.set_thumbnail(url=target.display_avatar.url)
            await interaction.followup.send(embed=embed)

    # ── /leaderboard ──────────────────────────────────────────────────────

    @app_commands.command(name="leaderboard", description="Top 10 membros com mais XP")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        top = await self.bot.db.get_leaderboard(interaction.guild_id)

        try:
            players = []
            for i, row in enumerate(top):
                member = interaction.guild.get_member(row["user_id"])
                username = member.display_name if member else f"Usuário {row['user_id']}"
                avatar_url = str(member.display_avatar.url) if member else ""
                level, _, _ = compute_level(row["xp"])

                # Try to get profile color
                color = "#5865F2"
                try:
                    profile = await self.bot.db.get_profile(row["user_id"])
                    color = profile.get("color", "#5865F2") or "#5865F2"
                except Exception:
                    pass

                players.append({
                    "rank": i + 1,
                    "username": username,
                    "level": level,
                    "total_xp": row["xp"],
                    "avatar_url": avatar_url,
                    "color": color,
                })

            card_buf = await generate_leaderboard_card(players, theme="escuro")
            file = discord.File(card_buf, filename="leaderboard.png")
            await interaction.followup.send(file=file)

        except Exception:
            # Fallback to plain embed
            embed = discord.Embed(
                title=f"{XP_EMOJI} Ranking do servidor",
                color=BOT_COLOR,
            )
            medals = ["🥇", "🥈", "🥉"]
            lines = []
            for i, row in enumerate(top):
                member = interaction.guild.get_member(row["user_id"])
                name = member.display_name if member else f"<@{row['user_id']}>"
                level, _, _ = compute_level(row["xp"])
                prefix = medals[i] if i < 3 else f"`{i+1}.`"
                lines.append(f"{prefix} **{name}** — Nível {level} • {row['xp']:,} XP")
            embed.description = "\n".join(lines) if lines else "Nenhum dado ainda."
            await interaction.followup.send(embed=embed)

    # ── Admin commands ────────────────────────────────────────────────────

    admin_group = app_commands.Group(
        name="xp-admin",
        description="Gerenciar XP dos membros",
        default_permissions=discord.Permissions(administrator=True),
    )

    @admin_group.command(name="dar", description="Dar XP a um membro")
    @app_commands.describe(membro="Membro", quantidade="Quantidade de XP")
    async def give_xp(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        quantidade: int,
    ):
        if quantidade <= 0:
            await interaction.response.send_message("A quantidade deve ser positiva.", ephemeral=True)
            return
        await self.bot.db.add_xp(membro.id, interaction.guild_id, quantidade, 0, time.time())
        await interaction.response.send_message(
            f"✅ +{quantidade:,} XP para {membro.mention}.", ephemeral=True
        )

    @admin_group.command(name="definir-nivel", description="Definir o nível de um membro")
    @app_commands.describe(membro="Membro", nivel="Novo nível")
    async def set_level(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        nivel: int,
    ):
        if nivel < 0:
            await interaction.response.send_message("Nível inválido.", ephemeral=True)
            return
        total = sum(xp_for_level(i) for i in range(nivel))
        await self.bot.db.set_user_xp(membro.id, interaction.guild_id, total)
        await self.bot.db.set_user_level(membro.id, interaction.guild_id, nivel)
        await interaction.response.send_message(
            f"✅ Nível de {membro.mention} definido como **{nivel}**.", ephemeral=True
        )

    @admin_group.command(name="cargo-nivel", description="Vincular cargo a um nível")
    @app_commands.describe(nivel="Nível necessário", cargo="Cargo a conceder")
    async def set_level_role(
        self,
        interaction: discord.Interaction,
        nivel: int,
        cargo: discord.Role,
    ):
        await self.bot.db.set_level_role(interaction.guild_id, nivel, cargo.id)
        await interaction.response.send_message(
            f"✅ {cargo.mention} será concedido ao atingir o nível **{nivel}**.",
            ephemeral=True,
        )

    @admin_group.command(name="canal-nivel", description="Canal para avisos de level-up")
    @app_commands.describe(canal="Canal de texto")
    async def set_level_channel(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ):
        await self.bot.db.set_guild_config(interaction.guild_id, level_channel_id=canal.id)
        await interaction.response.send_message(
            f"✅ Avisos de level-up serão enviados em {canal.mention}.", ephemeral=True
        )

    @admin_group.command(name="config-xp", description="Configurar XP por mensagem e cooldown")
    @app_commands.describe(
        minimo="XP mínimo por mensagem",
        maximo="XP máximo por mensagem",
        cooldown="Cooldown em segundos entre mensagens com XP",
        moedas="Moedas por mensagem",
    )
    async def config_xp(
        self,
        interaction: discord.Interaction,
        minimo: int = 15,
        maximo: int = 25,
        cooldown: int = 60,
        moedas: int = 5,
    ):
        await self.bot.db.set_guild_config(
            interaction.guild_id,
            xp_min=minimo,
            xp_max=maximo,
            xp_cooldown=cooldown,
            coins_per_msg=moedas,
        )
        await interaction.response.send_message(
            f"✅ XP: {minimo}–{maximo} | Cooldown: {cooldown}s | Moedas: {moedas}/msg",
            ephemeral=True,
        )

    @admin_group.command(name="boost-info", description="Ver todos os cargos com bônus de XP configurados")
    async def boost_info(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            # Fetch all multiplier roles for this guild
            # We pass all role IDs from the guild to surface what's configured
            all_role_ids = [r.id for r in interaction.guild.roles]
            # get_xp_multiplier returns the highest multiplier; to list all
            # we inspect each role individually
            rows = []
            for role in interaction.guild.roles:
                if role.is_default():
                    continue
                mult = await self.bot.db.get_xp_multiplier(interaction.guild_id, [role.id])
                if mult != 1.0:
                    rows.append((role, mult))

            embed = discord.Embed(
                title=f"{XP_EMOJI} Cargos com Bônus de XP",
                color=BOT_COLOR,
            )

            if rows:
                lines = []
                for role, mult in sorted(rows, key=lambda x: x[1], reverse=True):
                    lines.append(f"{role.mention} — **{mult:.2f}x**")
                embed.description = "\n".join(lines)
            else:
                embed.description = "Nenhum cargo com bônus de XP configurado."

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(
                f"❌ Erro ao buscar informações de boost: {e}", ephemeral=True
            )


# ── Level-up card builder ─────────────────────────────────────────────────────

async def _build_levelup_card(
    member: discord.Member,
    level: int,
    color: str = "#5865F2",
    banner_url: str = "",
    background_color: str = "#2C2F33",
    theme: str = "escuro",
) -> io.BytesIO:
    """
    Generate a 600x180px level-up card image.
    Returns a BytesIO PNG buffer.
    """
    import aiohttp
    from PIL import Image, ImageDraw, ImageFont

    W, H = 600, 180
    AV = 80

    # ── Helpers ──────────────────────────────────────────────────────────
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

    async def _fetch(url: str) -> bytes | None:
        if not url:
            return None
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status == 200:
                        return await r.read()
        except Exception:
            return None

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

    def _font(paths, size):
        for p in paths:
            try:
                return ImageFont.truetype(p, size)
            except (IOError, OSError):
                continue
        return ImageFont.load_default()

    # ── Theme ─────────────────────────────────────────────────────────────
    THEMES_LOCAL = {
        "escuro": {
            "overlay": (0, 0, 0, 160),
            "text": (255, 255, 255, 255),
            "subtext": (175, 178, 195, 255),
            "bg": (30, 32, 36),
        },
        "claro": {
            "overlay": (255, 255, 255, 140),
            "text": (15, 15, 25, 255),
            "subtext": (60, 62, 80, 255),
            "bg": (235, 238, 245),
        },
    }
    t = THEMES_LOCAL.get(theme, THEMES_LOCAL["escuro"])

    accent_rgb = _hex_to_rgb(color)
    bg_rgb = _hex_to_rgb(background_color)

    # ── Fetch assets concurrently ─────────────────────────────────────────
    avatar_bytes, banner_bytes = await asyncio.gather(
        _fetch(str(member.display_avatar.url)),
        _fetch(banner_url),
    )

    # ── Build canvas ──────────────────────────────────────────────────────
    if banner_bytes:
        try:
            bg_img = Image.open(io.BytesIO(banner_bytes)).convert("RGBA")
            bg_img = bg_img.resize((W, H), Image.LANCZOS)
            overlay = Image.new("RGBA", (W, H), t["overlay"])
            card = Image.alpha_composite(bg_img, overlay)
        except Exception:
            card = Image.new("RGBA", (W, H), bg_rgb + (255,))
    else:
        card = Image.new("RGBA", (W, H), bg_rgb + (255,))

    draw = ImageDraw.Draw(card)

    # ── Accent left stripe ─────────────────────────────────────────────────
    draw.rectangle([(0, 0), (5, H)], fill=accent_rgb + (255,))

    # ── Avatar ────────────────────────────────────────────────────────────
    ax, ay = 24, (H - AV) // 2

    if avatar_bytes:
        try:
            av_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        except Exception:
            av_img = Image.new("RGBA", (AV, AV), accent_rgb + (255,))
    else:
        av_img = Image.new("RGBA", (AV, AV), accent_rgb + (255,))

    # Ring around avatar
    ring_sz = AV + 8
    ring_img = Image.new("RGBA", (ring_sz, ring_sz), (0, 0, 0, 0))
    ImageDraw.Draw(ring_img).ellipse((0, 0, ring_sz - 1, ring_sz - 1), fill=accent_rgb + (255,))
    card.paste(ring_img, (ax - 4, ay - 4), ring_img)

    av_circle = _circle_crop(av_img, AV)
    card.paste(av_circle, (ax, ay), av_circle)

    # ── Text area ─────────────────────────────────────────────────────────
    tx = ax + AV + 22
    font_title = _font(_BOLD, 16)
    font_level = _font(_BOLD, 38)
    font_body = _font(_REGULAR, 13)

    # "SUBIU DE NÍVEL!" label
    draw.text((tx, 28), "SUBIU DE NÍVEL!", font=font_title, fill=accent_rgb + (255,))

    # Large level number
    level_text = f"Nível {level}"
    draw.text((tx, 52), level_text, font=font_level, fill=t["text"])

    # Username under level
    name_display = member.display_name[:22] + ("…" if len(member.display_name) > 22 else "")
    draw.text((tx, 110), name_display, font=font_body, fill=t["subtext"])

    # ── Confetti decoration ───────────────────────────────────────────────
    import random as _random
    confetti_colors = [
        accent_rgb,
        (255, 214, 0),
        (87, 242, 135),
        (254, 231, 92),
        (237, 66, 69),
        (88, 101, 242),
    ]
    _random.seed(level * 42)
    for _ in range(22):
        cx = _random.randint(tx, W - 20)
        cy = _random.randint(H - 40, H - 8)
        size = _random.randint(4, 10)
        col = _random.choice(confetti_colors) + (200,)
        if _random.random() > 0.5:
            draw.rectangle([(cx, cy), (cx + size, cy + size)], fill=col)
        else:
            draw.ellipse([(cx, cy), (cx + size, cy + size)], fill=col)

    # ── Output ────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    card.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


async def setup(bot: commands.Bot):
    await bot.add_cog(Levels(bot))
