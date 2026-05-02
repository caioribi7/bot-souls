import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from config import BOT_COLOR, SUCCESS_COLOR, ERROR_COLOR, WARNING_COLOR, COIN_EMOJI


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _staff_overwrites(guild: discord.Guild, user: discord.Member) -> dict:
    """Build permission overwrites: default role blocked, user + staff allowed."""
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False, send_messages=False
        ),
        user: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        ),
    }
    for role in guild.roles:
        if role.permissions.manage_guild:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )
    return overwrites


def _ticket_panel_embed(config: dict | None = None) -> discord.Embed:
    cfg = config or {}
    title = cfg.get("panel_title") or "📬 Suporte"
    description = cfg.get("panel_description") or (
        "Precisa de ajuda ou tem alguma dúvida?\n\n"
        "Clique no botão abaixo para abrir um ticket privado com a equipe.\n"
        "Nossa equipe irá atendê-lo assim que possível."
    )
    embed = discord.Embed(
        title=title,
        description=description,
        color=BOT_COLOR,
    )
    embed.set_footer(text="Um ticket por usuário • Respeitamos sua privacidade")
    return embed


def _ticket_channel_embed(user: discord.Member, config: dict | None = None) -> discord.Embed:
    cfg = config or {}
    title = (cfg.get("ticket_title") or "🎫 Ticket de {user}").replace("{user}", user.display_name)
    description = (cfg.get("ticket_description") or "Olá, {user}! Descreva sua dúvida e a equipe irá ajudar.").replace(
        "{user}", user.mention
    )
    embed = discord.Embed(
        title=title,
        description=description
        + "\n\n**Botões disponíveis:**\n"
        + "🔒 **Fechar** — encerra e apaga este ticket\n"
        + "👋 **Assumir** — staff assume o atendimento deste ticket",
        color=BOT_COLOR,
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.set_footer(text="Ticket aberto • Use os botões abaixo para gerenciar")
    return embed


async def _send_transcript(
    log_channel: discord.TextChannel,
    ticket_channel: discord.TextChannel,
    user: discord.Member,
    closer: discord.Member,
):
    """Collect last 100 messages and post a transcript embed to the log channel."""
    messages = []
    async for msg in ticket_channel.history(limit=100, oldest_first=True):
        if msg.author.bot and not msg.embeds:
            continue
        ts = msg.created_at.strftime("%d/%m/%Y %H:%M")
        content = msg.content or "[embed/anexo]"
        messages.append(f"[{ts}] {msg.author.display_name}: {content}")

    transcript_text = "\n".join(messages) if messages else "Nenhuma mensagem registrada."

    # Split transcript into chunks of ≤1024 chars for embed fields
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

    embed = discord.Embed(
        title=f"📋 Transcript — {ticket_channel.name}",
        color=WARNING_COLOR,
    )
    embed.add_field(name="Usuário", value=user.mention, inline=True)
    embed.add_field(name="Fechado por", value=closer.mention, inline=True)
    embed.add_field(name="Canal", value=ticket_channel.name, inline=True)

    # Attach transcript inline (up to 3 chunks to stay within embed limits)
    for i, chunk in enumerate(chunks[:3]):
        embed.add_field(
            name=f"Mensagens {'(continuação)' if i > 0 else ''}",
            value=f"```{chunk[:1000]}```",
            inline=False,
        )
    if len(chunks) > 3:
        embed.set_footer(text=f"Transcript truncado — {len(messages)} mensagens no total")
    else:
        embed.set_footer(text=f"{len(messages)} mensagens registradas")

    try:
        await log_channel.send(embed=embed)
    except discord.Forbidden:
        pass


# ─── Persistent Views ─────────────────────────────────────────────────────────

class TicketOpenView(discord.ui.View):
    """The panel posted in the configured ticket channel. Persistent across restarts."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="📬 Abrir Ticket",
        style=discord.ButtonStyle.success,
        custom_id="ticket_open_panel",
    )
    async def open_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        db = interaction.client.db
        guild = interaction.guild
        user = interaction.user

        # Check for existing open ticket
        existing = await db.get_open_ticket(user.id, guild.id)
        if existing:
            channel = guild.get_channel(existing["channel_id"])
            mention = channel.mention if channel else "ticket anterior"
            await interaction.response.send_message(
                f"❌ Você já tem um ticket aberto: {mention}",
                ephemeral=True,
            )
            return

        config = await db.get_tickets_config(guild.id)
        if not config or not config.get("enabled"):
            await interaction.response.send_message(
                "❌ O sistema de tickets não está configurado neste servidor.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        category = guild.get_channel(config["category_id"]) if config.get("category_id") else None
        overwrites = _staff_overwrites(guild, user)

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{user.name}",
                category=category,
                overwrites=overwrites,
                reason=f"Ticket aberto por {user}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Não tenho permissão para criar canais. Contate um administrador.",
                ephemeral=True,
            )
            return

        ticket_id = await db.create_ticket(guild.id, user.id, channel.id)

        control_view = TicketControlView(ticket_id=ticket_id, user_id=user.id)
        embed = _ticket_channel_embed(user, config)
        await channel.send(embed=embed, view=control_view)

        await interaction.followup.send(
            f"✅ Ticket aberto em {channel.mention}!",
            ephemeral=True,
        )


class TicketControlView(discord.ui.View):
    """Controls posted inside the ticket channel. Persistent across restarts."""

    def __init__(self, *, ticket_id: int = 0, user_id: int = 0):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.user_id = user_id

    @discord.ui.button(
        label="🔒 Fechar",
        style=discord.ButtonStyle.danger,
        custom_id="ticket_control_close",
    )
    async def close_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        db = interaction.client.db
        guild = interaction.guild
        channel = interaction.channel

        ticket = await db.get_ticket_by_channel(channel.id)
        if not ticket:
            await interaction.response.send_message(
                "❌ Este canal não é um ticket válido.", ephemeral=True
            )
            return

        await interaction.response.defer()

        closer = interaction.user
        ticket_user = guild.get_member(ticket["user_id"])

        # Send transcript to log channel
        config = await db.get_tickets_config(guild.id)
        if config and config.get("log_channel_id"):
            log_ch = guild.get_channel(config["log_channel_id"])
            if log_ch and ticket_user:
                await _send_transcript(log_ch, channel, ticket_user, closer)

        # Mark as closed in DB
        await db.close_ticket(ticket["id"])

        close_template = (
            (config or {}).get("close_message")
            or "🔒 Ticket fechado por {closer}. Este canal será deletado em 5 segundos."
        )
        close_msg = close_template.replace("{closer}", closer.mention)
        embed = discord.Embed(description=close_msg, color=WARNING_COLOR)
        await interaction.followup.send(embed=embed)

        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket fechado por {closer}")
        except discord.NotFound:
            pass

    @discord.ui.button(
        label="👋 Assumir",
        style=discord.ButtonStyle.primary,
        custom_id="ticket_control_claim",
    )
    async def claim_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        member = interaction.user
        if not member.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ Apenas membros da equipe podem assumir tickets.", ephemeral=True
            )
            return

        # Edit the original embed to show who claimed it
        original_message = interaction.message
        if original_message and original_message.embeds:
            embed = original_message.embeds[0]
            embed.color = SUCCESS_COLOR

            # Update or add "Atendido por" field
            new_fields = []
            updated = False
            for field in embed.fields:
                if field.name == "Atendido por":
                    new_fields.append(
                        discord.embeds.EmbedField(
                            name="Atendido por",
                            value=member.mention,
                            inline=True,
                        )
                    )
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

        await interaction.response.send_message(
            f"👋 {member.mention} assumiu este ticket!",
        )


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    ticket_group = app_commands.Group(
        name="ticket",
        description="Sistema de tickets de suporte",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    # ── /ticket configurar ────────────────────────────────────────────────

    @ticket_group.command(
        name="configurar",
        description="Configura o sistema de tickets (canal, categoria e log)",
    )
    @app_commands.describe(
        canal="Canal onde o painel de abertura de tickets será publicado",
        categoria="Categoria onde os canais de ticket serão criados",
        log="Canal para receber os transcritos dos tickets fechados",
    )
    async def configurar(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        categoria: discord.CategoryChannel | None = None,
        log: discord.TextChannel | None = None,
    ):
        db = self.bot.db
        guild = interaction.guild

        await interaction.response.defer(ephemeral=True)

        # Build fields to store
        fields = {
            "channel_id": canal.id,
            "enabled": 1,
        }
        if categoria:
            fields["category_id"] = categoria.id
        if log:
            fields["log_channel_id"] = log.id

        # Check if there's an existing config to delete the old panel message
        existing_config = await db.get_tickets_config(guild.id)
        if existing_config and existing_config.get("panel_message_id") and existing_config.get("channel_id"):
            old_channel = guild.get_channel(existing_config["channel_id"])
            if old_channel:
                try:
                    old_msg = await old_channel.fetch_message(existing_config["panel_message_id"])
                    await old_msg.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

        # Send panel to the configured channel
        view = TicketOpenView()
        panel_embed = _ticket_panel_embed(fields)
        try:
            panel_msg = await canal.send(embed=panel_embed, view=view)
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ Não tenho permissão para enviar mensagens em {canal.mention}.",
                ephemeral=True,
            )
            return

        fields["panel_message_id"] = panel_msg.id
        await db.set_tickets_config(guild.id, **fields)

        parts = [f"✅ Sistema de tickets configurado!\n\n📬 **Painel:** {canal.mention}"]
        if categoria:
            parts.append(f"📁 **Categoria:** {categoria.name}")
        if log:
            parts.append(f"📋 **Log:** {log.mention}")

        embed = discord.Embed(
            title="🎫 Tickets Configurados",
            description="\n".join(parts),
            color=SUCCESS_COLOR,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /ticket painel ────────────────────────────────────────────────────

    @ticket_group.command(
        name="painel",
        description="Reenvia o painel de abertura de tickets no canal configurado",
    )
    async def painel(self, interaction: discord.Interaction):
        db = self.bot.db
        guild = interaction.guild

        config = await db.get_tickets_config(guild.id)
        if not config or not config.get("channel_id"):
            await interaction.response.send_message(
                "❌ Configure o sistema de tickets primeiro com `/ticket configurar`.",
                ephemeral=True,
            )
            return

        channel = guild.get_channel(config["channel_id"])
        if not channel:
            await interaction.response.send_message(
                "❌ O canal configurado não foi encontrado. Reconfigure com `/ticket configurar`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Delete old panel if it exists
        if config.get("panel_message_id"):
            try:
                old_msg = await channel.fetch_message(config["panel_message_id"])
                await old_msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        view = TicketOpenView()
        panel_embed = _ticket_panel_embed(config)
        try:
            panel_msg = await channel.send(embed=panel_embed, view=view)
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ Não tenho permissão para enviar mensagens em {channel.mention}.",
                ephemeral=True,
            )
            return

        await db.set_tickets_config(guild.id, panel_message_id=panel_msg.id)

        await interaction.followup.send(
            f"✅ Painel de tickets reenviado em {channel.mention}!",
            ephemeral=True,
        )

    # ── /ticket fechar ────────────────────────────────────────────────────

    @ticket_group.command(
        name="fechar",
        description="Fecha o ticket do canal atual (use dentro de um canal de ticket)",
    )
    @app_commands.describe(razao="Motivo do fechamento (opcional)")
    async def fechar(
        self,
        interaction: discord.Interaction,
        razao: str | None = None,
    ):
        db = self.bot.db
        guild = interaction.guild
        channel = interaction.channel

        ticket = await db.get_ticket_by_channel(channel.id)
        if not ticket:
            await interaction.response.send_message(
                "❌ Este comando deve ser usado dentro de um canal de ticket.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        closer = interaction.user
        ticket_user = guild.get_member(ticket["user_id"])
        reason_text = f" — **Motivo:** {razao}" if razao else ""

        config = await db.get_tickets_config(guild.id)
        if config and config.get("log_channel_id"):
            log_ch = guild.get_channel(config["log_channel_id"])
            if log_ch and ticket_user:
                await _send_transcript(log_ch, channel, ticket_user, closer)

        await db.close_ticket(ticket["id"])

        close_template = (
            (config or {}).get("close_message")
            or "🔒 Ticket fechado por {closer}. Este canal será deletado em 5 segundos."
        )
        close_msg = close_template.replace("{closer}", closer.mention)
        if reason_text:
            close_msg = f"{close_msg}\n{reason_text}"
        embed = discord.Embed(description=close_msg, color=WARNING_COLOR)
        await interaction.followup.send(embed=embed)

        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket fechado por {closer}" + (f": {razao}" if razao else ""))
        except discord.NotFound:
            pass

    @ticket_group.command(
        name="textos",
        description="Personalizar textos do painel e dos tickets",
    )
    @app_commands.describe(
        titulo_painel="Título do painel de tickets",
        descricao_painel="Descrição do painel de tickets",
        titulo_ticket="Título do ticket (use {user})",
        descricao_ticket="Descrição do ticket (use {user})",
        mensagem_fechamento="Mensagem ao fechar (use {closer})",
    )
    async def textos(
        self,
        interaction: discord.Interaction,
        titulo_painel: str | None = None,
        descricao_painel: str | None = None,
        titulo_ticket: str | None = None,
        descricao_ticket: str | None = None,
        mensagem_fechamento: str | None = None,
    ):
        updates = {}
        if titulo_painel is not None:
            updates["panel_title"] = titulo_painel
        if descricao_painel is not None:
            updates["panel_description"] = descricao_painel
        if titulo_ticket is not None:
            updates["ticket_title"] = titulo_ticket
        if descricao_ticket is not None:
            updates["ticket_description"] = descricao_ticket
        if mensagem_fechamento is not None:
            updates["close_message"] = mensagem_fechamento

        if not updates:
            await interaction.response.send_message(
                "Informe pelo menos um texto para atualizar.",
                ephemeral=True,
            )
            return

        await self.bot.db.set_tickets_config(interaction.guild_id, **updates)
        await interaction.response.send_message(
            "✅ Textos do sistema de tickets atualizados.",
            ephemeral=True,
        )


# ─── Setup ────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot):
    # Register persistent views BEFORE adding the cog so they survive restarts
    bot.add_view(TicketOpenView())
    bot.add_view(TicketControlView())
    await bot.add_cog(Tickets(bot))
