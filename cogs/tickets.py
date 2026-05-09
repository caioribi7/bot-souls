"""
cogs/tickets.py – Tickets com Select Menu de categorias e configurador interativo
"""
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from config import BOT_COLOR, SUCCESS_COLOR, ERROR_COLOR, WARNING_COLOR


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _staff_overwrites(guild, user):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False, send_messages=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }
    for role in guild.roles:
        if role.permissions.manage_guild:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    return overwrites


def _ticket_panel_embed(config=None):
    cfg = config or {}
    title = cfg.get("panel_title") or "📬 Suporte"
    description = cfg.get("panel_description") or (
        "Precisa de ajuda? Selecione uma categoria abaixo para abrir um ticket privado com a equipe.\n"
        "Nossa equipe irá atendê-lo assim que possível."
    )
    embed = discord.Embed(title=title, description=description, color=BOT_COLOR)
    embed.set_footer(text="Um ticket por usuário • Respeitamos sua privacidade")
    return embed


def _ticket_channel_embed(user, category_name, config=None):
    cfg = config or {}
    title = (cfg.get("ticket_title") or "🎫 Ticket de {user}").replace("{user}", user.display_name)
    description = (cfg.get("ticket_description") or "Olá, {user}! Descreva sua situação e a equipe irá ajudar.").replace("{user}", user.mention)
    embed = discord.Embed(
        title=title,
        description=(
            f"**Categoria:** {category_name}\n\n"
            f"{description}\n\n"
            "**Botões disponíveis:**\n"
            "🔒 **Fechar** — encerra e apaga este ticket\n"
            "👋 **Assumir** — staff assume o atendimento"
        ),
        color=BOT_COLOR,
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="Ticket aberto • Use os botões abaixo para gerenciar")
    return embed


async def _send_transcript(log_channel, ticket_channel, user, closer):
    messages = []
    async for msg in ticket_channel.history(limit=100, oldest_first=True):
        if msg.author.bot and not msg.embeds:
            continue
        ts = msg.created_at.strftime("%d/%m/%Y %H:%M")
        content = msg.content or "[embed/anexo]"
        messages.append(f"[{ts}] {msg.author.display_name}: {content}")

    transcript_text = "\n".join(messages) if messages else "Nenhuma mensagem registrada."
    chunks = []
    current = ""
    for line in transcript_text.splitlines(keepends=True):
        if len(current) + len(line) > 1000:
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)

    embed = discord.Embed(title=f"📋 Transcript — {ticket_channel.name}", color=WARNING_COLOR)
    embed.add_field(name="Usuário", value=user.mention, inline=True)
    embed.add_field(name="Fechado por", value=closer.mention, inline=True)
    embed.add_field(name="Canal", value=ticket_channel.name, inline=True)
    for i, chunk in enumerate(chunks[:3]):
        embed.add_field(name=f"Mensagens {'(cont.)' if i > 0 else ''}", value=f"```{chunk[:1000]}```", inline=False)
    embed.set_footer(text=f"{len(messages)} mensagens registradas")
    try:
        await log_channel.send(embed=embed)
    except discord.Forbidden:
        pass


# ─── Category Select ──────────────────────────────────────────────────────────

CATEGORY_PREFIXES = {
    "duvidas": "duvida",
    "parcerias": "parceria",
    "outros": "ticket",
}


class TicketCategorySelect(discord.ui.Select):
    def __init__(self, config: dict):
        options = []
        if config.get("cat_duvidas_enabled", 1):
            options.append(discord.SelectOption(
                label=config.get("cat_duvidas_label") or "❓ Dúvidas",
                value="duvidas",
                description=config.get("cat_duvidas_desc") or "Tire suas dúvidas com a equipe",
                emoji="❓",
            ))
        if config.get("cat_parcerias_enabled", 1):
            options.append(discord.SelectOption(
                label=config.get("cat_parcerias_label") or "🤝 Parcerias",
                value="parcerias",
                description=config.get("cat_parcerias_desc") or "Proposta de parceria com o servidor",
                emoji="🤝",
            ))
        if config.get("cat_outros_enabled", 1):
            options.append(discord.SelectOption(
                label=config.get("cat_outros_label") or "💬 Outros",
                value="outros",
                description=config.get("cat_outros_desc") or "Outros assuntos e solicitações",
                emoji="💬",
            ))
        if not options:
            options.append(discord.SelectOption(label="📬 Abrir Ticket", value="outros"))
        super().__init__(
            placeholder="Selecione a categoria do seu ticket…",
            options=options,
            custom_id="ticket_category_select",
        )

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        db = interaction.client.db
        guild = interaction.guild
        user = interaction.user

        existing = await db.get_open_ticket(user.id, guild.id)
        if existing:
            channel = guild.get_channel(existing["channel_id"])
            mention = channel.mention if channel else "ticket anterior"
            return await interaction.response.send_message(f"❌ Você já tem um ticket aberto: {mention}", ephemeral=True)

        config = await db.get_tickets_config(guild.id)
        if not config or not config.get("enabled"):
            return await interaction.response.send_message("❌ O sistema de tickets não está configurado.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        category_obj = guild.get_channel(config["category_id"]) if config.get("category_id") else None
        overwrites = _staff_overwrites(guild, user)
        prefix = CATEGORY_PREFIXES.get(category, "ticket")
        channel_name = f"{prefix}-{user.name[:20]}"

        # Get category label for embed
        label_key = f"cat_{category}_label"
        cat_label = config.get(label_key) or category.capitalize()

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category_obj,
                overwrites=overwrites,
                reason=f"Ticket [{category}] aberto por {user}",
            )
        except discord.Forbidden:
            return await interaction.followup.send("❌ Sem permissão para criar canais.", ephemeral=True)

        ticket_id = await db.create_ticket(guild.id, user.id, channel.id)
        control_view = TicketControlView(ticket_id=ticket_id, user_id=user.id)
        embed = _ticket_channel_embed(user, cat_label, config)
        await channel.send(embed=embed, view=control_view)
        await interaction.followup.send(f"✅ Ticket aberto em {channel.mention}!", ephemeral=True)


class TicketOpenView(discord.ui.View):
    """Painel de tickets — persistente. Recarregado dinamicamente."""

    def __init__(self, config: dict | None = None):
        super().__init__(timeout=None)
        cfg = config or {}
        self.add_item(TicketCategorySelect(cfg))


class TicketOpenViewEmpty(discord.ui.View):
    """View persistente vazia para registro no bot (restaura via DB no startup)."""
    def __init__(self):
        super().__init__(timeout=None)


class TicketControlView(discord.ui.View):
    def __init__(self, *, ticket_id: int = 0, user_id: int = 0):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.user_id = user_id

    @discord.ui.button(label="🔒 Fechar", style=discord.ButtonStyle.danger, custom_id="ticket_control_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        db = interaction.client.db
        guild = interaction.guild
        channel = interaction.channel

        ticket = await db.get_ticket_by_channel(channel.id)
        if not ticket:
            return await interaction.response.send_message("❌ Este canal não é um ticket válido.", ephemeral=True)

        await interaction.response.defer()
        closer = interaction.user
        ticket_user = guild.get_member(ticket["user_id"])

        config = await db.get_tickets_config(guild.id)
        if config and config.get("log_channel_id"):
            log_ch = guild.get_channel(config["log_channel_id"])
            if log_ch and ticket_user:
                await _send_transcript(log_ch, channel, ticket_user, closer)

        await db.close_ticket(ticket["id"])

        close_template = (config or {}).get("close_message") or "🔒 Ticket fechado por {closer}. Este canal será deletado em 5 segundos."
        close_msg = close_template.replace("{closer}", closer.mention)
        await interaction.followup.send(embed=discord.Embed(description=close_msg, color=WARNING_COLOR))
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket fechado por {closer}")
        except discord.NotFound:
            pass

    @discord.ui.button(label="👋 Assumir", style=discord.ButtonStyle.primary, custom_id="ticket_control_claim")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not member.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Apenas membros da equipe podem assumir tickets.", ephemeral=True)

        original_message = interaction.message
        if original_message and original_message.embeds:
            embed = original_message.embeds[0]
            embed.color = SUCCESS_COLOR
            updated = False
            new_fields = []
            for field in embed.fields:
                if field.name == "Atendido por":
                    new_fields.append(discord.embeds.EmbedField(name="Atendido por", value=member.mention, inline=True))
                    updated = True
                else:
                    new_fields.append(field)
            if not updated:
                embed.add_field(name="Atendido por", value=member.mention, inline=True)
            else:
                embed.clear_fields()
                for f in new_fields:
                    embed.add_field(name=f.name, value=f.value, inline=f.inline)
            await original_message.edit(embed=embed)

        await interaction.response.send_message(f"👋 {member.mention} assumiu este ticket!")


# ─── Ticket Configurator (interactive) ───────────────────────────────────────

class ModalTicketTexto(discord.ui.Modal):
    def __init__(self, title: str, field_key: str, current: str, state: dict, view: "TicketConfigView"):
        super().__init__(title=title)
        self._field_key = field_key
        self._state = state
        self._view = view
        self.campo = discord.ui.TextInput(label="Texto", style=discord.TextStyle.paragraph, default=current, required=False, max_length=1024)
        self.add_item(self.campo)

    async def on_submit(self, interaction: discord.Interaction):
        self._state[self._field_key] = self.campo.value.strip()
        await self._view.refresh(interaction)


class TicketConfigView(discord.ui.View):
    """Painel interativo para configurar tickets."""

    def __init__(self, state: dict, author_id: int, guild: discord.Guild):
        super().__init__(timeout=300)
        self.state = state
        self.author_id = author_id
        self.guild = guild

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Este painel pertence a outro usuário.", ephemeral=True)
            return False
        return True

    def build_overview_embed(self) -> discord.Embed:
        s = self.state
        ch = self.guild.get_channel(s.get("channel_id") or 0)
        log_ch = self.guild.get_channel(s.get("log_channel_id") or 0)
        cat = self.guild.get_channel(s.get("category_id") or 0)

        cats = []
        if s.get("cat_duvidas_enabled", 1): cats.append(s.get("cat_duvidas_label") or "❓ Dúvidas")
        if s.get("cat_parcerias_enabled", 1): cats.append(s.get("cat_parcerias_label") or "🤝 Parcerias")
        if s.get("cat_outros_enabled", 1): cats.append(s.get("cat_outros_label") or "💬 Outros")

        embed = discord.Embed(title="🎫 Configurar Tickets", color=BOT_COLOR)
        embed.add_field(name="📢 Canal do Painel", value=ch.mention if ch else "*(não definido)*", inline=True)
        embed.add_field(name="📋 Log", value=log_ch.mention if log_ch else "—", inline=True)
        embed.add_field(name="📁 Categoria Discord", value=cat.name if cat else "—", inline=True)
        embed.add_field(name="📌 Título do Painel", value=s.get("panel_title") or "—", inline=False)
        embed.add_field(name="📝 Descrição do Painel", value=(s.get("panel_description") or "—")[:200], inline=False)
        embed.add_field(name="🏷️ Categorias Ativas", value=" | ".join(cats) if cats else "*(nenhuma)*", inline=False)
        embed.set_footer(text="Configure e clique em 💾 Salvar para aplicar")
        return embed

    async def refresh(self, interaction):
        await interaction.response.edit_message(embed=self.build_overview_embed(), view=self)

    @discord.ui.button(label="📌 Título Painel", style=discord.ButtonStyle.secondary, row=0)
    async def btn_titulo(self, interaction, _):
        await interaction.response.send_modal(ModalTicketTexto(
            "📌 Título do Painel", "panel_title", self.state.get("panel_title") or "", self.state, self))

    @discord.ui.button(label="📝 Descrição Painel", style=discord.ButtonStyle.secondary, row=0)
    async def btn_desc(self, interaction, _):
        await interaction.response.send_modal(ModalTicketTexto(
            "📝 Descrição do Painel", "panel_description", self.state.get("panel_description") or "", self.state, self))

    @discord.ui.button(label="🎫 Título Ticket", style=discord.ButtonStyle.secondary, row=0)
    async def btn_tkt_titulo(self, interaction, _):
        await interaction.response.send_modal(ModalTicketTexto(
            "🎫 Título do Ticket", "ticket_title", self.state.get("ticket_title") or "", self.state, self))

    @discord.ui.button(label="💬 Desc. Ticket", style=discord.ButtonStyle.secondary, row=0)
    async def btn_tkt_desc(self, interaction, _):
        await interaction.response.send_modal(ModalTicketTexto(
            "💬 Descrição do Ticket (use {user})", "ticket_description", self.state.get("ticket_description") or "", self.state, self))

    @discord.ui.button(label="🔒 Msg Fechamento", style=discord.ButtonStyle.secondary, row=1)
    async def btn_close_msg(self, interaction, _):
        await interaction.response.send_modal(ModalTicketTexto(
            "🔒 Mensagem de Fechamento (use {closer})", "close_message", self.state.get("close_message") or "", self.state, self))

    @discord.ui.button(label="❓ Dúvidas: ON", style=discord.ButtonStyle.success, row=1)
    async def btn_duvidas(self, interaction, button):
        self.state["cat_duvidas_enabled"] = 0 if self.state.get("cat_duvidas_enabled", 1) else 1
        button.label = f"❓ Dúvidas: {'ON' if self.state['cat_duvidas_enabled'] else 'OFF'}"
        button.style = discord.ButtonStyle.success if self.state["cat_duvidas_enabled"] else discord.ButtonStyle.danger
        await self.refresh(interaction)

    @discord.ui.button(label="🤝 Parcerias: ON", style=discord.ButtonStyle.success, row=1)
    async def btn_parcerias(self, interaction, button):
        self.state["cat_parcerias_enabled"] = 0 if self.state.get("cat_parcerias_enabled", 1) else 1
        button.label = f"🤝 Parcerias: {'ON' if self.state['cat_parcerias_enabled'] else 'OFF'}"
        button.style = discord.ButtonStyle.success if self.state["cat_parcerias_enabled"] else discord.ButtonStyle.danger
        await self.refresh(interaction)

    @discord.ui.button(label="💬 Outros: ON", style=discord.ButtonStyle.success, row=2)
    async def btn_outros(self, interaction, button):
        self.state["cat_outros_enabled"] = 0 if self.state.get("cat_outros_enabled", 1) else 1
        button.label = f"💬 Outros: {'ON' if self.state['cat_outros_enabled'] else 'OFF'}"
        button.style = discord.ButtonStyle.success if self.state["cat_outros_enabled"] else discord.ButtonStyle.danger
        await self.refresh(interaction)

    @discord.ui.button(label="🏷️ Label Dúvidas", style=discord.ButtonStyle.secondary, row=2)
    async def btn_label_duvidas(self, interaction, _):
        await interaction.response.send_modal(ModalTicketTexto(
            "🏷️ Rótulo da categoria Dúvidas", "cat_duvidas_label", self.state.get("cat_duvidas_label") or "❓ Dúvidas", self.state, self))

    @discord.ui.button(label="🏷️ Label Parcerias", style=discord.ButtonStyle.secondary, row=2)
    async def btn_label_parcerias(self, interaction, _):
        await interaction.response.send_modal(ModalTicketTexto(
            "🏷️ Rótulo da categoria Parcerias", "cat_parcerias_label", self.state.get("cat_parcerias_label") or "🤝 Parcerias", self.state, self))

    @discord.ui.button(label="💾 Salvar & Publicar", style=discord.ButtonStyle.success, row=3)
    async def btn_salvar(self, interaction, _):
        db = interaction.client.db
        guild = interaction.guild
        s = self.state

        if not s.get("channel_id"):
            return await interaction.response.send_message("❌ Defina o canal do painel primeiro com `/ticket configurar canal:#canal`.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        # Delete old panel
        existing = await db.get_tickets_config(guild.id)
        if existing and existing.get("panel_message_id") and existing.get("channel_id"):
            old_ch = guild.get_channel(existing["channel_id"])
            if old_ch:
                try:
                    old_msg = await old_ch.fetch_message(existing["panel_message_id"])
                    await old_msg.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

        channel = guild.get_channel(s["channel_id"])
        if not channel:
            return await interaction.followup.send("❌ Canal não encontrado. Reconfigure.", ephemeral=True)

        view = TicketOpenView(s)
        panel_embed = _ticket_panel_embed(s)
        try:
            panel_msg = await channel.send(embed=panel_embed, view=view)
        except discord.Forbidden:
            return await interaction.followup.send(f"❌ Sem permissão para enviar em {channel.mention}.", ephemeral=True)

        s["panel_message_id"] = panel_msg.id
        s["enabled"] = 1
        await db.set_tickets_config(guild.id, **s)

        for child in self.children:
            child.disabled = True
        embed = discord.Embed(
            title="✅ Tickets Configurados!",
            description=f"Painel publicado em {channel.mention}.",
            color=SUCCESS_COLOR,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        await interaction.message.edit(view=self)

    @discord.ui.button(label="🗑️ Cancelar", style=discord.ButtonStyle.danger, row=3)
    async def btn_cancelar(self, interaction, _):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=discord.Embed(description="❌ Configuração cancelada.", color=ERROR_COLOR), view=self)


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    ticket_group = app_commands.Group(
        name="ticket",
        description="Sistema de tickets de suporte",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @ticket_group.command(name="configurar", description="Abre o painel interativo de configuração de tickets")
    @app_commands.describe(
        canal="Canal onde o painel de tickets será publicado",
        categoria="Categoria Discord onde os canais de ticket serão criados",
        log="Canal para receber transcritos dos tickets fechados",
    )
    async def configurar(self, interaction, canal: discord.TextChannel | None = None,
                         categoria: discord.CategoryChannel | None = None,
                         log: discord.TextChannel | None = None):
        db = self.bot.db
        guild = interaction.guild
        await interaction.response.defer(ephemeral=True)

        existing = await db.get_tickets_config(guild.id) or {}
        state = dict(existing)

        if canal:
            state["channel_id"] = canal.id
        if categoria:
            state["category_id"] = categoria.id
        if log:
            state["log_channel_id"] = log.id

        # Ensure defaults
        state.setdefault("panel_title", "📬 Suporte")
        state.setdefault("panel_description", "Selecione uma categoria abaixo para abrir um ticket privado com a equipe.")
        state.setdefault("ticket_title", "🎫 Ticket de {user}")
        state.setdefault("ticket_description", "Olá, {user}! Descreva sua situação e a equipe irá ajudar.")
        state.setdefault("close_message", "🔒 Ticket fechado por {closer}. Este canal será deletado em 5 segundos.")
        state.setdefault("cat_duvidas_enabled", 1)
        state.setdefault("cat_duvidas_label", "❓ Dúvidas")
        state.setdefault("cat_duvidas_desc", "Tire suas dúvidas com a equipe")
        state.setdefault("cat_parcerias_enabled", 1)
        state.setdefault("cat_parcerias_label", "🤝 Parcerias")
        state.setdefault("cat_parcerias_desc", "Proposta de parceria com o servidor")
        state.setdefault("cat_outros_enabled", 1)
        state.setdefault("cat_outros_label", "💬 Outros")
        state.setdefault("cat_outros_desc", "Outros assuntos e solicitações")

        view = TicketConfigView(state, interaction.user.id, guild)
        embed = view.build_overview_embed()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @ticket_group.command(name="painel", description="Reenvia o painel de tickets no canal configurado")
    async def painel(self, interaction):
        db = self.bot.db
        guild = interaction.guild
        config = await db.get_tickets_config(guild.id)
        if not config or not config.get("channel_id"):
            return await interaction.response.send_message("❌ Configure tickets primeiro com `/ticket configurar`.", ephemeral=True)
        channel = guild.get_channel(config["channel_id"])
        if not channel:
            return await interaction.response.send_message("❌ Canal não encontrado.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        if config.get("panel_message_id"):
            try:
                old = await channel.fetch_message(config["panel_message_id"])
                await old.delete()
            except (discord.NotFound, discord.Forbidden):
                pass
        view = TicketOpenView(config)
        panel_embed = _ticket_panel_embed(config)
        try:
            panel_msg = await channel.send(embed=panel_embed, view=view)
        except discord.Forbidden:
            return await interaction.followup.send(f"❌ Sem permissão em {channel.mention}.", ephemeral=True)
        await db.set_tickets_config(guild.id, panel_message_id=panel_msg.id)
        await interaction.followup.send(f"✅ Painel reenviado em {channel.mention}!", ephemeral=True)

    @ticket_group.command(name="fechar", description="Fecha o ticket do canal atual")
    @app_commands.describe(razao="Motivo do fechamento")
    async def fechar(self, interaction, razao: str | None = None):
        db = self.bot.db
        guild = interaction.guild
        channel = interaction.channel
        ticket = await db.get_ticket_by_channel(channel.id)
        if not ticket:
            return await interaction.response.send_message("❌ Use dentro de um canal de ticket.", ephemeral=True)
        await interaction.response.defer()
        closer = interaction.user
        ticket_user = guild.get_member(ticket["user_id"])
        config = await db.get_tickets_config(guild.id)
        if config and config.get("log_channel_id"):
            log_ch = guild.get_channel(config["log_channel_id"])
            if log_ch and ticket_user:
                await _send_transcript(log_ch, channel, ticket_user, closer)
        await db.close_ticket(ticket["id"])
        close_template = (config or {}).get("close_message") or "🔒 Ticket fechado por {closer}. Este canal será deletado em 5 segundos."
        close_msg = close_template.replace("{closer}", closer.mention)
        if razao:
            close_msg += f"\n**Motivo:** {razao}"
        await interaction.followup.send(embed=discord.Embed(description=close_msg, color=WARNING_COLOR))
        await asyncio.sleep(5)
        try:
            await channel.delete()
        except discord.NotFound:
            pass


# ─── Setup ────────────────────────────────────────────────────────────────────

async def setup(bot):
    bot.add_view(TicketControlView())
    await bot.add_cog(Tickets(bot))
