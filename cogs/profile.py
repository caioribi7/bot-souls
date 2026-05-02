import re
import discord
from discord import app_commands
from discord.ext import commands
from config import BOT_COLOR
from utils.card_generator import COLOR_PRESETS

HEX_RE = re.compile(r"^#?([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})$")
URL_RE = re.compile(r"^https?://\S+$")


def _norm_hex(value: str) -> str | None:
    m = HEX_RE.match(value)
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return f"#{h.upper()}"


def _profile_embed(profile: dict, title: str = "🪪 Editar Perfil") -> discord.Embed:
    tema_icon = "🌙" if profile.get("theme", "escuro") == "escuro" else "☀️"
    color_int = int(profile.get("color", "#5865F2").lstrip("#"), 16)
    embed = discord.Embed(title=title, color=color_int)
    embed.add_field(
        name="Tema",
        value=f"{tema_icon} {profile.get('theme', 'escuro').capitalize()}",
        inline=True,
    )
    embed.add_field(name="Cor Destaque", value=f"`{profile.get('color', '#5865F2')}`", inline=True)
    embed.add_field(
        name="Cor Fundo", value=f"`{profile.get('background_color', '#2C2F33')}`", inline=True
    )
    embed.add_field(name="Bio", value=profile.get("bio") or "—", inline=False)

    banner = profile.get("banner_url") or "—"
    icon = profile.get("icon_url") or "—"
    if len(banner) > 60:
        banner = banner[:57] + "…"
    if len(icon) > 60:
        icon = icon[:57] + "…"
    embed.add_field(name="Banner", value=banner, inline=False)
    embed.add_field(name="Ícone", value=icon, inline=False)
    embed.set_footer(
        text="📎 Para enviar arquivos diretamente: /perfil banner arquivo:  •  /perfil icone arquivo:"
    )
    return embed


# ── Modals ────────────────────────────────────────────────────────────────────


class BioModal(discord.ui.Modal, title="Editar Bio"):
    bio = discord.ui.TextInput(
        label="Bio",
        placeholder="Fale um pouco sobre você...",
        required=False,
        max_length=150,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, bot: commands.Bot, current: str = ""):
        super().__init__()
        self.bot = bot
        self.bio.default = current

    async def on_submit(self, interaction: discord.Interaction):
        await self.bot.db.update_profile(interaction.user.id, bio=self.bio.value.strip())
        await interaction.response.send_message("✅ Bio atualizada!", ephemeral=True)


class ColorModal(discord.ui.Modal, title="Cor de Destaque"):
    cor = discord.ui.TextInput(
        label="Código hex (ex: #FF5733)",
        placeholder="#5865F2",
        required=True,
        max_length=7,
    )

    def __init__(self, bot: commands.Bot, current: str = "#5865F2"):
        super().__init__()
        self.bot = bot
        self.cor.default = current

    async def on_submit(self, interaction: discord.Interaction):
        v = _norm_hex(self.cor.value)
        if not v:
            await interaction.response.send_message("❌ Cor inválida. Use `#RRGGBB`.", ephemeral=True)
            return
        await self.bot.db.update_profile(interaction.user.id, color=v)
        embed = discord.Embed(
            description=f"✅ Cor de destaque: `{v}`", color=int(v.lstrip("#"), 16)
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class BgColorModal(discord.ui.Modal, title="Cor de Fundo"):
    cor = discord.ui.TextInput(
        label="Código hex (ex: #1A1A2E)",
        placeholder="#2C2F33",
        required=True,
        max_length=7,
    )

    def __init__(self, bot: commands.Bot, current: str = "#2C2F33"):
        super().__init__()
        self.bot = bot
        self.cor.default = current

    async def on_submit(self, interaction: discord.Interaction):
        v = _norm_hex(self.cor.value)
        if not v:
            await interaction.response.send_message("❌ Cor inválida. Use `#RRGGBB`.", ephemeral=True)
            return
        await self.bot.db.update_profile(interaction.user.id, background_color=v)
        embed = discord.Embed(description=f"✅ Cor de fundo: `{v}`", color=int(v.lstrip("#"), 16))
        await interaction.response.send_message(embed=embed, ephemeral=True)


class BannerModal(discord.ui.Modal, title="Banner do Perfil"):
    url = discord.ui.TextInput(
        label="URL da imagem ou GIF (vazio = remover)",
        placeholder="https://... (.gif para animado)",
        required=False,
        max_length=500,
    )

    def __init__(self, bot: commands.Bot, current: str = ""):
        super().__init__()
        self.bot = bot
        self.url.default = current

    async def on_submit(self, interaction: discord.Interaction):
        val = self.url.value.strip()
        if val and not URL_RE.match(val):
            await interaction.response.send_message("❌ URL inválida.", ephemeral=True)
            return
        await self.bot.db.update_profile(interaction.user.id, banner_url=val)
        if val:
            is_gif = val.lower().split("?")[0].endswith(".gif")
            embed = discord.Embed(
                description=f"✅ Banner {'animado (GIF) ' if is_gif else ''}atualizado!",
                color=BOT_COLOR,
            )
            if not is_gif:
                embed.set_image(url=val)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("✅ Banner removido.", ephemeral=True)


class IconModal(discord.ui.Modal, title="Ícone do Perfil"):
    url = discord.ui.TextInput(
        label="URL da imagem (vazio = remover)",
        placeholder="https://...",
        required=False,
        max_length=500,
    )

    def __init__(self, bot: commands.Bot, current: str = ""):
        super().__init__()
        self.bot = bot
        self.url.default = current

    async def on_submit(self, interaction: discord.Interaction):
        val = self.url.value.strip()
        if val and not URL_RE.match(val):
            await interaction.response.send_message("❌ URL inválida.", ephemeral=True)
            return
        await self.bot.db.update_profile(interaction.user.id, icon_url=val)
        if val:
            embed = discord.Embed(description="✅ Ícone atualizado!", color=BOT_COLOR)
            embed.set_thumbnail(url=val)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("✅ Ícone removido.", ephemeral=True)


# ── Theme selector view ───────────────────────────────────────────────────────


class ThemeView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: int):
        super().__init__(timeout=60)
        self.bot = bot
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Não é seu perfil.", ephemeral=True)
            return False
        return True

    async def _set(self, interaction: discord.Interaction, theme: str, label: str):
        await self.bot.db.update_profile(interaction.user.id, theme=theme)
        self.stop()
        await interaction.response.edit_message(
            content=f"✅ Tema alterado para **{label}**!",
            embed=None,
            view=None,
        )

    @discord.ui.button(label="🌙 Escuro", style=discord.ButtonStyle.secondary)
    async def dark(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._set(interaction, "escuro", "Escuro")

    @discord.ui.button(label="☀️ Claro", style=discord.ButtonStyle.primary)
    async def light(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._set(interaction, "claro", "Claro")

    @discord.ui.button(label="← Voltar", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, _: discord.ui.Button):
        profile = await self.bot.db.get_profile(interaction.user.id)
        view = EditMenuView(self.bot, self.user_id, profile)
        self.stop()
        await interaction.response.edit_message(
            content="", embed=_profile_embed(profile), view=view
        )


# ── Color palette view ────────────────────────────────────────────────────────


class ColorPaletteView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: int):
        super().__init__(timeout=60)
        self.bot = bot
        self.user_id = user_id
        for name, (emoji, hex_val) in COLOR_PRESETS.items():
            btn = discord.ui.Button(label=f"{emoji} {name}", style=discord.ButtonStyle.secondary)
            btn.callback = self._make_cb(hex_val, name)
            self.add_item(btn)
        back_btn = discord.ui.Button(
            label="← Voltar", style=discord.ButtonStyle.secondary, row=3
        )
        back_btn.callback = self._back
        self.add_item(back_btn)
        hex_btn = discord.ui.Button(
            label="✏️ Inserir hex", style=discord.ButtonStyle.primary, row=3
        )
        hex_btn.callback = self._hex_input
        self.add_item(hex_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Não é seu perfil.", ephemeral=True)
            return False
        return True

    def _make_cb(self, hex_val: str, name: str):
        async def callback(interaction: discord.Interaction):
            await self.bot.db.update_profile(interaction.user.id, color=hex_val)
            self.stop()
            await interaction.response.edit_message(
                content="",
                embed=discord.Embed(
                    description=f"✅ Cor definida: **{name}** `{hex_val}`",
                    color=int(hex_val.lstrip("#"), 16),
                ),
                view=None,
            )
        return callback

    async def _back(self, interaction: discord.Interaction):
        profile = await self.bot.db.get_profile(interaction.user.id)
        view = EditMenuView(self.bot, self.user_id, profile)
        self.stop()
        await interaction.response.edit_message(
            content="", embed=_profile_embed(profile), view=view
        )

    async def _hex_input(self, interaction: discord.Interaction):
        profile = await self.bot.db.get_profile(interaction.user.id)
        await interaction.response.send_modal(
            ColorModal(self.bot, profile.get("color", "#5865F2"))
        )


# ── Confirm reset view ────────────────────────────────────────────────────────


class ConfirmResetView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: int):
        super().__init__(timeout=30)
        self.bot = bot
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Não é seu perfil.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.bot.db.update_profile(
            interaction.user.id,
            bio="",
            banner_url="",
            icon_url="",
            color="#5865F2",
            background_color="#2C2F33",
            theme="escuro",
        )
        self.stop()
        await interaction.response.edit_message(
            content="✅ Perfil resetado.", embed=None, view=None
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.stop()
        profile = await self.bot.db.get_profile(self.user_id)
        view = EditMenuView(self.bot, self.user_id, profile)
        await interaction.response.edit_message(
            content="", embed=_profile_embed(profile), view=view
        )


# ── Edit menu (select dropdown) ───────────────────────────────────────────────


class EditSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, user_id: int, profile: dict):
        self.bot = bot
        self.user_id = user_id
        self.profile = profile
        options = [
            discord.SelectOption(
                label="📝 Bio", value="bio", description="Alterar sua bio"
            ),
            discord.SelectOption(
                label="🎨 Cor de Destaque",
                value="color",
                description="Cor dos detalhes do card",
            ),
            discord.SelectOption(
                label="🖌️ Cor de Fundo",
                value="bg",
                description="Fundo quando não há banner",
            ),
            discord.SelectOption(
                label="🌙 Tema", value="theme", description="Fundo escuro ou claro"
            ),
            discord.SelectOption(
                label="🖼️ Banner",
                value="banner",
                description="Imagem ou GIF de fundo do card",
            ),
            discord.SelectOption(
                label="🏷️ Ícone",
                value="icon",
                description="Badge circular no canto do avatar",
            ),
            discord.SelectOption(
                label="🗑️ Resetar Tudo",
                value="reset",
                description="Voltar tudo ao padrão",
            ),
        ]
        super().__init__(placeholder="✏️  O que deseja editar?", options=options)

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]

        if value == "bio":
            await interaction.response.send_modal(
                BioModal(self.bot, self.profile.get("bio", ""))
            )

        elif value == "color":
            view = ColorPaletteView(self.bot, self.user_id)
            await interaction.response.edit_message(
                content="",
                embed=discord.Embed(
                    title="🎨 Cor de Destaque",
                    description="Escolha uma cor da paleta ou clique em **✏️ Inserir hex**.",
                    color=BOT_COLOR,
                ),
                view=view,
            )

        elif value == "bg":
            await interaction.response.send_modal(
                BgColorModal(self.bot, self.profile.get("background_color", "#2C2F33"))
            )

        elif value == "theme":
            view = ThemeView(self.bot, self.user_id)
            tema_atual = self.profile.get("theme", "escuro")
            icon = "🌙" if tema_atual == "escuro" else "☀️"
            await interaction.response.edit_message(
                content="",
                embed=discord.Embed(
                    title="🌙 Tema do Card",
                    description=f"Tema atual: **{icon} {tema_atual.capitalize()}**\nEscolha abaixo:",
                    color=BOT_COLOR,
                ),
                view=view,
            )

        elif value == "banner":
            await interaction.response.send_modal(
                BannerModal(self.bot, self.profile.get("banner_url", ""))
            )

        elif value == "icon":
            await interaction.response.send_modal(
                IconModal(self.bot, self.profile.get("icon_url", ""))
            )

        elif value == "reset":
            view = ConfirmResetView(self.bot, self.user_id)
            await interaction.response.edit_message(
                content="",
                embed=discord.Embed(
                    title="⚠️ Resetar Perfil",
                    description="Isso apagará **bio, banner, ícone e cores**. Confirmar?",
                    color=discord.Color.red(),
                ),
                view=view,
            )


class EditMenuView(discord.ui.View):
    def __init__(self, bot: commands.Bot, user_id: int, profile: dict):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.add_item(EditSelect(bot, user_id, profile))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Não é seu perfil.", ephemeral=True)
            return False
        return True


# ── Cog ───────────────────────────────────────────────────────────────────────


class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    perfil = app_commands.Group(name="perfil", description="Gerenciar seu perfil")

    # /perfil ver ─────────────────────────────────────────────────────────────

    @perfil.command(name="ver", description="Ver o card de perfil")
    @app_commands.describe(membro="Membro (padrão: você)")
    async def view(
        self,
        interaction: discord.Interaction,
        membro: discord.Member | None = None,
    ):
        await interaction.response.defer()
        target = membro or interaction.user

        try:
            from cogs.levels import compute_level
        except Exception:
            # Fallback local se o cog de levels falhar ao carregar
            def compute_level(total_xp: int) -> tuple[int, int, int]:
                def xp_for_level(level: int) -> int:
                    return 5 * (level ** 2) + 50 * level + 100
                level = 0
                acc = 0
                while True:
                    needed = xp_for_level(level)
                    if acc + needed > total_xp:
                        return level, total_xp - acc, needed
                    acc += needed
                    level += 1

        db = self.bot.db
        user_data = await db.get_user(target.id, interaction.guild_id)
        profile = await db.get_profile(target.id)
        rank = await db.get_rank(target.id, interaction.guild_id)
        level, cur_xp, xp_need = compute_level(user_data["xp"])

        try:
            from utils.card_generator import generate_profile_card

            buf, ext = await generate_profile_card(
                username=target.display_name,
                avatar_url=str(target.display_avatar.url),
                level=level,
                current_xp=cur_xp,
                xp_needed=xp_need,
                total_xp=user_data["xp"],
                rank=rank,
                messages=user_data["messages"],
                bio=profile["bio"],
                color=profile["color"],
                banner_url=profile["banner_url"],
                background_color=profile["background_color"],
                icon_url=profile["icon_url"],
                theme=profile.get("theme", "escuro"),
            )
            await interaction.followup.send(file=discord.File(buf, filename=f"perfil.{ext}"))

        except Exception:
            import traceback

            traceback.print_exc()
            embed = discord.Embed(
                title=f"🪪 {target.display_name}",
                color=int(profile["color"].lstrip("#"), 16),
            )
            embed.set_thumbnail(url=target.display_avatar.url)
            if profile["banner_url"]:
                embed.set_image(url=profile["banner_url"])
            if profile["bio"]:
                embed.add_field(name="📝 Bio", value=profile["bio"], inline=False)
            embed.add_field(name="🏆 Nível", value=str(level), inline=True)
            embed.add_field(name="📊 Rank", value=f"#{rank}", inline=True)
            embed.add_field(
                name="⭐ XP",
                value=f"{cur_xp:,}/{xp_need:,} ({user_data['xp']:,} total)",
                inline=True,
            )
            embed.add_field(name="💬 Msgs", value=f"{user_data['messages']:,}", inline=True)
            await interaction.followup.send(embed=embed)

    # /perfil editar ──────────────────────────────────────────────────────────

    @perfil.command(name="editar", description="Editar perfil com menu interativo")
    async def edit(self, interaction: discord.Interaction):
        profile = await self.bot.db.get_profile(interaction.user.id)
        view = EditMenuView(self.bot, interaction.user.id, profile)
        await interaction.response.send_message(
            embed=_profile_embed(profile), view=view, ephemeral=True
        )

    # /perfil tema ────────────────────────────────────────────────────────────

    @perfil.command(name="tema", description="Escolher fundo escuro ou claro do card")
    async def theme(self, interaction: discord.Interaction):
        profile = await self.bot.db.get_profile(interaction.user.id)
        atual = profile.get("theme", "escuro")
        icon = "🌙" if atual == "escuro" else "☀️"
        view = ThemeView(self.bot, interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🌙 Tema do Card",
                description=f"Tema atual: **{icon} {atual.capitalize()}**\nEscolha abaixo:",
                color=BOT_COLOR,
            ),
            view=view,
            ephemeral=True,
        )

    # /perfil cor-preset ──────────────────────────────────────────────────────

    @perfil.command(name="cor-preset", description="Escolher cor de destaque de uma paleta")
    async def color_preset(self, interaction: discord.Interaction):
        view = ColorPaletteView(self.bot, interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🎨 Paleta de Cores",
                description="Escolha uma cor de destaque ou clique em **✏️ Inserir hex**.",
                color=BOT_COLOR,
            ),
            view=view,
            ephemeral=True,
        )

    # /perfil bio ─────────────────────────────────────────────────────────────

    @perfil.command(name="bio", description="Alterar sua bio")
    @app_commands.describe(texto="Bio (máx. 150 caracteres)")
    async def bio(self, interaction: discord.Interaction, texto: str):
        if len(texto) > 150:
            await interaction.response.send_message(
                "❌ Máximo: 150 caracteres.", ephemeral=True
            )
            return
        await self.bot.db.update_profile(interaction.user.id, bio=texto)
        await interaction.response.send_message("✅ Bio atualizada!", ephemeral=True)

    # /perfil cor ─────────────────────────────────────────────────────────────

    @perfil.command(name="cor", description="Alterar cor de destaque (hex)")
    @app_commands.describe(hex_cor="Ex: #FF5733")
    async def color(self, interaction: discord.Interaction, hex_cor: str):
        v = _norm_hex(hex_cor)
        if not v:
            await interaction.response.send_message("❌ Use `#RRGGBB`.", ephemeral=True)
            return
        await self.bot.db.update_profile(interaction.user.id, color=v)
        embed = discord.Embed(description=f"Cor: `{v}`", color=int(v.lstrip("#"), 16))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /perfil fundo ───────────────────────────────────────────────────────────

    @perfil.command(name="fundo", description="Cor de fundo quando não há banner (hex)")
    @app_commands.describe(hex_cor="Ex: #1A1A2E")
    async def background(self, interaction: discord.Interaction, hex_cor: str):
        v = _norm_hex(hex_cor)
        if not v:
            await interaction.response.send_message("❌ Use `#RRGGBB`.", ephemeral=True)
            return
        await self.bot.db.update_profile(interaction.user.id, background_color=v)
        embed = discord.Embed(description=f"Cor de fundo: `{v}`", color=int(v.lstrip("#"), 16))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /perfil banner ──────────────────────────────────────────────────────────

    @perfil.command(name="banner", description="Banner de fundo do card (imagem, GIF ou arquivo)")
    @app_commands.describe(url="URL da imagem ou GIF", arquivo="Enviar imagem diretamente do dispositivo")
    async def banner(
        self,
        interaction: discord.Interaction,
        url: str | None = None,
        arquivo: discord.Attachment | None = None,
    ):
        if arquivo:
            banner_url = arquivo.url
            is_gif = (arquivo.content_type or "").startswith("image/gif")
        elif url:
            if not URL_RE.match(url):
                await interaction.response.send_message("❌ URL inválida.", ephemeral=True)
                return
            banner_url = url
            is_gif = url.lower().split("?")[0].endswith(".gif")
        else:
            await interaction.response.send_message(
                "❌ Envie um **arquivo** ou uma **URL**.", ephemeral=True
            )
            return

        await self.bot.db.update_profile(interaction.user.id, banner_url=banner_url)
        embed = discord.Embed(
            description=f"✅ Banner {'animado (GIF) ' if is_gif else ''}atualizado!",
            color=BOT_COLOR,
        )
        if not is_gif:
            embed.set_image(url=banner_url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /perfil icone ───────────────────────────────────────────────────────────

    @perfil.command(name="icone", description="Ícone/badge circular no canto do avatar")
    @app_commands.describe(url="URL da imagem", arquivo="Enviar imagem diretamente do dispositivo")
    async def icon(
        self,
        interaction: discord.Interaction,
        url: str | None = None,
        arquivo: discord.Attachment | None = None,
    ):
        if arquivo:
            icon_url = arquivo.url
        elif url:
            if not URL_RE.match(url):
                await interaction.response.send_message("❌ URL inválida.", ephemeral=True)
                return
            icon_url = url
        else:
            await interaction.response.send_message(
                "❌ Envie um **arquivo** ou uma **URL**.", ephemeral=True
            )
            return

        await self.bot.db.update_profile(interaction.user.id, icon_url=icon_url)
        embed = discord.Embed(description="✅ Ícone atualizado!", color=BOT_COLOR)
        embed.set_thumbnail(url=icon_url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /perfil remover-banner ──────────────────────────────────────────────────

    @perfil.command(name="remover-banner", description="Remover o banner do perfil")
    async def remove_banner(self, interaction: discord.Interaction):
        await self.bot.db.update_profile(interaction.user.id, banner_url="")
        await interaction.response.send_message("✅ Banner removido.", ephemeral=True)

    # /perfil resetar ─────────────────────────────────────────────────────────

    @perfil.command(name="resetar", description="Resetar perfil para o padrão")
    async def reset(self, interaction: discord.Interaction):
        view = ConfirmResetView(self.bot, interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Resetar Perfil",
                description="Isso apagará bio, banner, ícone e cores. Confirmar?",
                color=discord.Color.red(),
            ),
            view=view,
            ephemeral=True,
        )

    # /perfil info ────────────────────────────────────────────────────────────

    @perfil.command(name="info", description="Ver as configurações atuais do seu perfil")
    async def info(self, interaction: discord.Interaction):
        profile = await self.bot.db.get_profile(interaction.user.id)
        await interaction.response.send_message(
            embed=_profile_embed(profile, title="🪪 Seu Perfil"), ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))
