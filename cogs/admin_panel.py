import discord
from discord.ext import commands
from discord import app_commands
from config import BOT_COLOR, SUCCESS_COLOR, ERROR_COLOR, WARNING_COLOR, COIN_EMOJI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_channel(guild: discord.Guild, channel_id) -> str:
    """Return a channel mention or 'Não configurado'."""
    if not channel_id:
        return "Não configurado"
    ch = guild.get_channel(int(channel_id))
    return ch.mention if ch else f"<#{channel_id}>"


def _fmt_bool(value) -> str:
    return "✅ Ativado" if value else "❌ Desativado"


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------

class XPConfigModal(discord.ui.Modal, title="Configurar XP & Níveis"):
    xp_min = discord.ui.TextInput(
        label="XP Mínimo por mensagem",
        placeholder="Ex: 10",
        required=False,
        max_length=6,
    )
    xp_max = discord.ui.TextInput(
        label="XP Máximo por mensagem",
        placeholder="Ex: 25",
        required=False,
        max_length=6,
    )
    xp_cooldown = discord.ui.TextInput(
        label="Cooldown de XP (segundos)",
        placeholder="Ex: 60",
        required=False,
        max_length=6,
    )
    coins_per_msg = discord.ui.TextInput(
        label="Moedas por mensagem",
        placeholder="Ex: 1",
        required=False,
        max_length=6,
    )
    level_coins_base = discord.ui.TextInput(
        label="Moedas base ao subir de nível",
        placeholder="Ex: 50",
        required=False,
        max_length=6,
    )

    def __init__(self, db, guild_id: int):
        super().__init__()
        self.db = db
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        updates: dict = {}
        fields = {
            "xp_min": self.xp_min.value,
            "xp_max": self.xp_max.value,
            "xp_cooldown": self.xp_cooldown.value,
            "coins_per_msg": self.coins_per_msg.value,
            "level_coins_base": self.level_coins_base.value,
        }
        errors = []
        for key, raw in fields.items():
            if raw.strip():
                try:
                    val = int(raw.strip())
                    if val <= 0:
                        raise ValueError
                    updates[key] = val
                except ValueError:
                    errors.append(key)

        if errors:
            await interaction.response.send_message(
                f"❌ Os seguintes campos devem ser números inteiros positivos: `{'`, `'.join(errors)}`",
                ephemeral=True,
            )
            return

        if updates:
            await interaction.client.db.set_guild_config(self.guild_id, **updates)

        await interaction.response.send_message(
            "✅ Configurações de XP & Níveis atualizadas com sucesso!",
            ephemeral=True,
        )


class ChannelModal(discord.ui.Modal, title="Configurar Canal de Nível"):
    channel_input = discord.ui.TextInput(
        label="ID ou menção do canal",
        placeholder="Ex: 123456789012345678 ou #nivel",
        required=True,
        max_length=32,
    )

    def __init__(self, db, guild_id: int):
        super().__init__()
        self.db = db
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.channel_input.value.strip().strip("<#>")
        try:
            channel_id = int(raw)
        except ValueError:
            await interaction.response.send_message(
                "❌ Valor inválido. Envie o ID numérico do canal ou uma menção `#canal`.",
                ephemeral=True,
            )
            return

        ch = interaction.guild.get_channel(channel_id)
        if ch is None:
            await interaction.response.send_message(
                "❌ Canal não encontrado neste servidor.",
                ephemeral=True,
            )
            return

        await interaction.client.db.set_guild_config(
            self.guild_id, level_channel_id=channel_id
        )
        await interaction.response.send_message(
            f"✅ Canal de nível definido como {ch.mention}.",
            ephemeral=True,
        )


class CustomRolePriceModal(discord.ui.Modal, title="Preço do Cargo Personalizado"):
    price = discord.ui.TextInput(
        label=f"Novo preço (em moedas)",
        placeholder="Ex: 5000",
        required=True,
        max_length=10,
    )

    def __init__(self, db, guild_id: int):
        super().__init__()
        self.db = db
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.price.value.strip())
            if val <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ O preço deve ser um número inteiro positivo.",
                ephemeral=True,
            )
            return

        await interaction.client.db.set_shop_config(
            self.guild_id, custom_role_price=val
        )
        await interaction.response.send_message(
            f"✅ Preço do cargo personalizado definido para **{val} {COIN_EMOJI}**.",
            ephemeral=True,
        )


class WelcomeModal(discord.ui.Modal, title="Configurar Boas-vindas"):
    mensagem = discord.ui.TextInput(
        label="Mensagem de boas-vindas",
        placeholder="Use {user} para mencionar. Ex: Bem-vindo(a), {user}!",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=500,
    )
    url_imagem = discord.ui.TextInput(
        label="URL da imagem (opcional)",
        placeholder="https://...",
        required=False,
        max_length=300,
    )

    def __init__(self, db, guild_id: int):
        super().__init__()
        self.db = db
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        updates: dict = {}
        if self.mensagem.value.strip():
            updates["welcome_message"] = self.mensagem.value.strip()
        if self.url_imagem.value.strip():
            updates["welcome_image_url"] = self.url_imagem.value.strip()

        if updates:
            await interaction.client.db.set_guild_config(self.guild_id, **updates)

        await interaction.response.send_message(
            "✅ Configurações de boas-vindas atualizadas!",
            ephemeral=True,
        )


class PixModal(discord.ui.Modal, title="Configurar Pix & Sweet Coins"):
    chave_pix = discord.ui.TextInput(
        label="Chave Pix",
        placeholder="CPF, e-mail, telefone ou chave aleatória",
        required=False,
        max_length=100,
    )
    preco_100 = discord.ui.TextInput(
        label="Preço de 100 moedas (em centavos)",
        placeholder="Ex: 199 = R$1,99",
        required=False,
        max_length=8,
    )
    preco_500 = discord.ui.TextInput(
        label="Preço de 500 moedas (em centavos)",
        placeholder="Ex: 799 = R$7,99",
        required=False,
        max_length=8,
    )
    preco_1000 = discord.ui.TextInput(
        label="Preço de 1000 moedas (em centavos)",
        placeholder="Ex: 1499 = R$14,99",
        required=False,
        max_length=8,
    )

    def __init__(self, db, guild_id: int):
        super().__init__()
        self.db = db
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        updates: dict = {}
        price_fields = {
            "pix_price_100": self.preco_100.value,
            "pix_price_500": self.preco_500.value,
            "pix_price_1000": self.preco_1000.value,
        }
        errors = []
        for key, raw in price_fields.items():
            if raw.strip():
                try:
                    val = int(raw.strip())
                    if val <= 0:
                        raise ValueError
                    updates[key] = val
                except ValueError:
                    errors.append(key)

        if errors:
            await interaction.response.send_message(
                f"❌ Os preços devem ser inteiros positivos em centavos: `{'`, `'.join(errors)}`",
                ephemeral=True,
            )
            return

        if self.chave_pix.value.strip():
            updates["pix_key"] = self.chave_pix.value.strip()

        if updates:
            await interaction.client.db.set_guild_config(self.guild_id, **updates)

        await interaction.response.send_message(
            "✅ Configurações de Pix atualizadas com sucesso!",
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Section views (with Back button + action buttons)
# ---------------------------------------------------------------------------

class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="← Voltar", style=discord.ButtonStyle.secondary, row=4)

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Apenas administradores podem usar este painel.", ephemeral=True
            )
            return
        view = AdminPanelView(interaction.client.db)
        await interaction.response.edit_message(
            embed=_main_embed(), view=view
        )


# --- XP Section ---

class XPSectionView(discord.ui.View):
    def __init__(self, db, guild_id: int):
        super().__init__(timeout=120)
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="✏️ Editar XP Config", style=discord.ButtonStyle.primary, row=0)
    async def edit_xp(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Apenas administradores podem usar este painel.", ephemeral=True
            )
            return
        await interaction.response.send_modal(XPConfigModal(self.db, self.guild_id))

    @discord.ui.button(label="📢 Canal de Nível", style=discord.ButtonStyle.secondary, row=0)
    async def set_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Apenas administradores podem usar este painel.", ephemeral=True
            )
            return
        await interaction.response.send_modal(ChannelModal(self.db, self.guild_id))


# --- Shop Section ---

class ShopSectionView(discord.ui.View):
    def __init__(self, db, guild_id: int):
        super().__init__(timeout=120)
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="✏️ Preço Cargo Custom", style=discord.ButtonStyle.primary, row=0)
    async def edit_price(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Apenas administradores podem usar este painel.", ephemeral=True
            )
            return
        await interaction.response.send_modal(CustomRolePriceModal(self.db, self.guild_id))


# --- Welcome Section ---

class WelcomeSectionView(discord.ui.View):
    def __init__(self, db, guild_id: int):
        super().__init__(timeout=120)
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="✏️ Editar", style=discord.ButtonStyle.primary, row=0)
    async def edit_welcome(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Apenas administradores podem usar este painel.", ephemeral=True
            )
            return
        await interaction.response.send_modal(WelcomeModal(self.db, self.guild_id))


# --- Tickets Section ---

class TicketsSectionView(discord.ui.View):
    def __init__(self, db, guild_id: int, enabled: bool):
        super().__init__(timeout=120)
        self.db = db
        self.guild_id = guild_id
        self.enabled = enabled

        if enabled:
            self.add_item(_TicketToggleButton(label="❌ Desativar", new_state=False))
        else:
            self.add_item(_TicketToggleButton(label="✅ Ativar", new_state=True))

        self.add_item(BackButton())


class _TicketToggleButton(discord.ui.Button):
    def __init__(self, label: str, new_state: bool):
        style = discord.ButtonStyle.danger if not new_state else discord.ButtonStyle.success
        super().__init__(label=label, style=style, row=0)
        self.new_state = new_state

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Apenas administradores podem usar este painel.", ephemeral=True
            )
            return
        db = interaction.client.db
        await db.set_tickets_config(interaction.guild_id, enabled=1 if self.new_state else 0)
        cfg = await db.get_tickets_config(interaction.guild_id)
        embed = await _tickets_embed(interaction.guild, cfg)
        view = TicketsSectionView(db, interaction.guild_id, bool(self.new_state))
        await interaction.response.edit_message(embed=embed, view=view)


# --- Anon Section ---

class AnonSectionView(discord.ui.View):
    def __init__(self, db, guild_id: int, enabled: bool):
        super().__init__(timeout=120)
        self.db = db
        self.guild_id = guild_id
        self.enabled = enabled

        if enabled:
            self.add_item(_AnonToggleButton(label="❌ Desativar", new_state=False))
        else:
            self.add_item(_AnonToggleButton(label="✅ Ativar", new_state=True))

        self.add_item(BackButton())


class _AnonToggleButton(discord.ui.Button):
    def __init__(self, label: str, new_state: bool):
        style = discord.ButtonStyle.danger if not new_state else discord.ButtonStyle.success
        super().__init__(label=label, style=style, row=0)
        self.new_state = new_state

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Apenas administradores podem usar este painel.", ephemeral=True
            )
            return
        db = interaction.client.db
        # get current anon config and toggle
        cfg = await db.get_anon_config(interaction.guild_id)
        if cfg is None:
            await interaction.response.send_message(
                "❌ Sistema de mensagens anônimas não configurado ainda.", ephemeral=True
            )
            return
        # Use a generic approach — update via set if available, else warn
        # The spec says "calls toggle_anon"; we store via db attribute if available
        await db.toggle_anon(interaction.guild_id, self.new_state)
        cfg = await db.get_anon_config(interaction.guild_id)
        embed = _anon_embed(interaction.guild, cfg)
        view = AnonSectionView(db, interaction.guild_id, bool(self.new_state))
        await interaction.response.edit_message(embed=embed, view=view)


# --- Clans Section ---

class ClansSectionView(discord.ui.View):
    def __init__(self, db, guild_id: int):
        super().__init__(timeout=120)
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())


# --- Pix Section ---

class PixSectionView(discord.ui.View):
    def __init__(self, db, guild_id: int):
        super().__init__(timeout=120)
        self.db = db
        self.guild_id = guild_id
        self.add_item(BackButton())

    @discord.ui.button(label="✏️ Editar Pix", style=discord.ButtonStyle.primary, row=0)
    async def edit_pix(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Apenas administradores podem usar este painel.", ephemeral=True
            )
            return
        await interaction.response.send_modal(PixModal(self.db, self.guild_id))


# ---------------------------------------------------------------------------
# Section embed builders
# ---------------------------------------------------------------------------

def _main_embed() -> discord.Embed:
    embed = discord.Embed(
        title="⚙️ Painel de Administração",
        description="Selecione uma seção abaixo para ver e editar as configurações.",
        color=BOT_COLOR,
    )
    embed.set_footer(text="Apenas administradores podem usar este painel")
    return embed


async def _xp_embed(guild: discord.Guild, cfg: dict, boost_roles: list) -> discord.Embed:
    embed = discord.Embed(title="📊 XP & Níveis", color=BOT_COLOR)

    embed.add_field(
        name="Configurações de XP",
        value=(
            f"**XP por mensagem:** {cfg.get('xp_min', '?')} – {cfg.get('xp_max', '?')}\n"
            f"**Cooldown:** {cfg.get('xp_cooldown', '?')}s\n"
            f"**Moedas por mensagem:** {cfg.get('coins_per_msg', '?')} {COIN_EMOJI}\n"
            f"**Moedas base ao nivelar:** {cfg.get('level_coins_base', '?')} {COIN_EMOJI}"
        ),
        inline=False,
    )
    embed.add_field(
        name="Canal de Nível",
        value=_fmt_channel(guild, cfg.get("level_channel_id")),
        inline=False,
    )

    if boost_roles:
        lines = []
        for br in boost_roles:
            role = guild.get_role(int(br["role_id"]))
            name = role.mention if role else f"<@&{br['role_id']}>"
            lines.append(f"{name} — **{br['multiplier']}x**")
        embed.add_field(name="Cargos com Boost de XP", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Cargos com Boost de XP", value="Nenhum configurado", inline=False)

    embed.set_footer(text="Use os botões abaixo para editar")
    return embed


async def _shop_embed(guild: discord.Guild, cfg: dict, shop_cfg: dict) -> discord.Embed:
    embed = discord.Embed(title="🏪 Loja & Economia", color=BOT_COLOR)
    embed.add_field(
        name="Canal da Loja",
        value=_fmt_channel(guild, cfg.get("shop_channel_id")),
        inline=False,
    )
    price = shop_cfg.get("custom_role_price", "Não definido") if shop_cfg else "Não definido"
    embed.add_field(
        name="Preço — Cargo Personalizado",
        value=f"**{price}** {COIN_EMOJI}" if isinstance(price, int) else price,
        inline=False,
    )
    embed.set_footer(text="Use os botões abaixo para editar")
    return embed


async def _welcome_embed(guild: discord.Guild, cfg: dict) -> discord.Embed:
    embed = discord.Embed(title="👋 Boas-vindas", color=BOT_COLOR)
    embed.add_field(
        name="Canal de Boas-vindas",
        value=_fmt_channel(guild, cfg.get("welcome_channel_id")),
        inline=False,
    )
    msg = cfg.get("welcome_message") or "Não definida"
    embed.add_field(name="Mensagem", value=f"```{msg}```", inline=False)
    img = cfg.get("welcome_image_url") or "Não definida"
    embed.add_field(name="URL da Imagem", value=img, inline=False)
    embed.set_footer(text="Use os botões abaixo para editar")
    return embed


async def _tickets_embed(guild: discord.Guild, cfg) -> discord.Embed:
    embed = discord.Embed(title="🎫 Tickets", color=BOT_COLOR)
    if cfg is None:
        embed.description = "Sistema de tickets ainda não configurado."
        return embed
    embed.add_field(
        name="Status",
        value=_fmt_bool(cfg.get("enabled")),
        inline=False,
    )
    embed.add_field(
        name="Canal de Tickets",
        value=_fmt_channel(guild, cfg.get("channel_id")),
        inline=True,
    )
    embed.add_field(
        name="Log de Tickets",
        value=_fmt_channel(guild, cfg.get("log_channel_id")),
        inline=True,
    )
    cat_id = cfg.get("category_id")
    if cat_id:
        cat = guild.get_channel(int(cat_id))
        cat_name = cat.name if cat else f"ID {cat_id}"
    else:
        cat_name = "Não configurada"
    embed.add_field(name="Categoria", value=cat_name, inline=True)
    embed.set_footer(text="Use os botões abaixo para editar")
    return embed


def _anon_embed(guild: discord.Guild, cfg) -> discord.Embed:
    embed = discord.Embed(title="📨 Mensagens Anônimas", color=BOT_COLOR)
    if cfg is None:
        embed.description = "Sistema de mensagens anônimas ainda não configurado."
        return embed
    embed.add_field(
        name="Status",
        value=_fmt_bool(cfg.get("enabled")),
        inline=False,
    )
    embed.add_field(
        name="Canal de menu (painel)",
        value=_fmt_channel(guild, cfg.get("menu_channel_id")),
        inline=True,
    )
    embed.add_field(
        name="Canal de envio (GIF)",
        value=_fmt_channel(guild, cfg.get("channel_id")),
        inline=True,
    )
    embed.add_field(
        name="Canal de log",
        value=_fmt_channel(guild, cfg.get("log_channel_id")),
        inline=True,
    )
    embed.set_footer(text="Use os botões abaixo para editar")
    return embed


async def _clans_embed(guild: discord.Guild, clans: list) -> discord.Embed:
    embed = discord.Embed(title="🛡️ Clãs", color=BOT_COLOR)
    embed.add_field(name="Total de Clãs", value=str(len(clans)), inline=False)

    if clans:
        preview = clans[:5]
        lines = []
        for clan in preview:
            name = clan.get("name", "Sem nome")
            members = clan.get("member_count", clan.get("members", "?"))
            lines.append(f"• **{name}** — {members} membros")
        embed.add_field(
            name="Clãs Recentes (primeiros 5)",
            value="\n".join(lines),
            inline=False,
        )
    else:
        embed.add_field(name="Clãs", value="Nenhum clã criado ainda.", inline=False)

    embed.set_footer(text="Gerencie os clãs pelos comandos /clan")
    return embed


async def _pix_embed(guild: discord.Guild, cfg: dict) -> discord.Embed:
    embed = discord.Embed(title="💰 Pix & Sweet Coins", color=BOT_COLOR)

    pix_key = cfg.get("pix_key") or "Não configurada"
    embed.add_field(name="Chave Pix", value=pix_key, inline=False)

    def fmt_price(centavos) -> str:
        if centavos is None:
            return "Não definido"
        return f"R$ {int(centavos) / 100:.2f}".replace(".", ",")

    price_table = (
        f"100 {COIN_EMOJI} → **{fmt_price(cfg.get('pix_price_100'))}**\n"
        f"500 {COIN_EMOJI} → **{fmt_price(cfg.get('pix_price_500'))}**\n"
        f"1000 {COIN_EMOJI} → **{fmt_price(cfg.get('pix_price_1000'))}**"
    )
    embed.add_field(name="Tabela de Preços", value=price_table, inline=False)
    embed.set_footer(text="Use os botões abaixo para editar")
    return embed


# ---------------------------------------------------------------------------
# Main Select
# ---------------------------------------------------------------------------

class AdminSectionSelect(discord.ui.Select):
    def __init__(self, db):
        self.db = db
        options = [
            discord.SelectOption(label="📊 XP & Níveis", value="xp"),
            discord.SelectOption(label="🏪 Loja & Economia", value="shop"),
            discord.SelectOption(label="👋 Boas-vindas", value="welcome"),
            discord.SelectOption(label="🎫 Tickets", value="tickets"),
            discord.SelectOption(label="📨 Mensagens Anônimas", value="anon"),
            discord.SelectOption(label="🛡️ Clãs", value="clans"),
            discord.SelectOption(label="💰 Pix & Sweet Coins", value="pix"),
        ]
        super().__init__(
            placeholder="Selecione uma seção...",
            options=options,
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Apenas administradores podem usar este painel.", ephemeral=True
            )
            return

        section = self.values[0]
        guild = interaction.guild
        guild_id = interaction.guild_id
        db = interaction.client.db

        cfg = await db.get_guild_config(guild_id)
        if cfg is None:
            cfg = {}

        if section == "xp":
            boost_roles = await db.get_xp_boost_roles(guild_id) or []
            embed = await _xp_embed(guild, cfg, boost_roles)
            view = XPSectionView(db, guild_id)
            await interaction.response.edit_message(embed=embed, view=view)

        elif section == "shop":
            shop_cfg = await db.get_shop_config(guild_id)
            embed = await _shop_embed(guild, cfg, shop_cfg)
            view = ShopSectionView(db, guild_id)
            await interaction.response.edit_message(embed=embed, view=view)

        elif section == "welcome":
            embed = await _welcome_embed(guild, cfg)
            view = WelcomeSectionView(db, guild_id)
            await interaction.response.edit_message(embed=embed, view=view)

        elif section == "tickets":
            tickets_cfg = await db.get_tickets_config(guild_id)
            embed = await _tickets_embed(guild, tickets_cfg)
            enabled = bool(tickets_cfg.get("enabled")) if tickets_cfg else False
            view = TicketsSectionView(db, guild_id, enabled)
            await interaction.response.edit_message(embed=embed, view=view)

        elif section == "anon":
            anon_cfg = await db.get_anon_config(guild_id)
            embed = _anon_embed(guild, anon_cfg)
            enabled = bool(anon_cfg.get("enabled")) if anon_cfg else False
            view = AnonSectionView(db, guild_id, enabled)
            await interaction.response.edit_message(embed=embed, view=view)

        elif section == "clans":
            clans = await db.get_all_clans(guild_id) or []
            embed = await _clans_embed(guild, clans)
            view = ClansSectionView(db, guild_id)
            await interaction.response.edit_message(embed=embed, view=view)

        elif section == "pix":
            embed = await _pix_embed(guild, cfg)
            view = PixSectionView(db, guild_id)
            await interaction.response.edit_message(embed=embed, view=view)


# ---------------------------------------------------------------------------
# Main panel view
# ---------------------------------------------------------------------------

class AdminPanelView(discord.ui.View):
    def __init__(self, db):
        super().__init__(timeout=120)
        self.add_item(AdminSectionSelect(db))


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class AdminPanel(commands.Cog):
    """Painel de administração do servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="painel", description="Abre o painel de administração do servidor.")
    @app_commands.default_permissions(administrator=True)
    async def painel(self, interaction: discord.Interaction):
        """Abre o painel de configurações administrativas."""
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Você precisa ser administrador para usar este comando.",
                ephemeral=True,
            )
            return

        view = AdminPanelView(self.bot.db)
        await interaction.response.send_message(
            embed=_main_embed(),
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminPanel(bot))
