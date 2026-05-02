"""
cogs/moderation.py  –  Comandos de moderação para o Community Bot
discord.py 2.x  •  app_commands (slash)  •  Mensagens em português
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_COLOR, SUCCESS_COLOR, ERROR_COLOR, WARNING_COLOR

# ── Duration parser ───────────────────────────────────────────────────────────

_DURATION_RE = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?$", re.IGNORECASE)
_MAX_TIMEOUT_DELTA = timedelta(days=28)


def _parse_duration(text: str) -> timedelta | None:
    """Parse strings like '10m', '1h30m', '2d12h', etc.
    Returns None if the format is invalid or exceeds 28 days."""
    m = _DURATION_RE.match(text.strip())
    if not m or not any(m.groups()):
        return None
    days = int(m.group(1) or 0)
    hours = int(m.group(2) or 0)
    minutes = int(m.group(3) or 0)
    delta = timedelta(days=days, hours=hours, minutes=minutes)
    if delta <= timedelta(0) or delta > _MAX_TIMEOUT_DELTA:
        return None
    return delta


def _fmt_duration(delta: timedelta) -> str:
    """Format timedelta as human-readable Portuguese string."""
    total = int(delta.total_seconds())
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "0m"


# ── Permission check helpers ──────────────────────────────────────────────────

def _no_perm_embed(missing: list[str]) -> discord.Embed:
    perms = ", ".join(f"`{p}`" for p in missing)
    return discord.Embed(
        title="❌ Sem Permissão",
        description=f"Você precisa da(s) permissão(ões): {perms}",
        color=ERROR_COLOR,
    )


# ── Cog ───────────────────────────────────────────────────────────────────────

class Moderation(commands.Cog):
    """Comandos de moderação: ban, kick, timeout, warns, lock, nuke…"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Shared error handler ──────────────────────────────────────────────

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            embed = _no_perm_embed(error.missing_permissions)
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        # Re-raise so discord.py logs it
        raise error

    # ══════════════════════════════════════════════════════════════════════
    # /mod  command group
    # ══════════════════════════════════════════════════════════════════════

    mod = app_commands.Group(
        name="mod",
        description="Comandos de moderação",
        default_permissions=discord.Permissions(kick_members=True),
    )

    # ── /mod ban ──────────────────────────────────────────────────────────

    @mod.command(name="ban", description="Bane um membro do servidor")
    @app_commands.describe(
        membro="Membro a ser banido",
        razao="Motivo do banimento",
        delete_dias="Dias de mensagens a excluir (0-7, padrão 0)",
    )
    @app_commands.checks.has_permissions(ban_members=True)
    async def mod_ban(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        razao: str,
        delete_dias: Optional[int] = 0,
    ) -> None:
        await interaction.response.defer(ephemeral=False)

        delete_dias = max(0, min(7, delete_dias or 0))

        if membro == interaction.user:
            return await interaction.followup.send(
                embed=discord.Embed(description="❌ Você não pode banir a si mesmo.", color=ERROR_COLOR),
                ephemeral=True,
            )
        if membro.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Você não pode banir alguém com cargo igual ou superior ao seu.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # DM antes de banir
        dm_embed = discord.Embed(
            title="🔨 Você foi banido",
            description=f"Você foi banido de **{interaction.guild.name}**.",
            color=ERROR_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        dm_embed.add_field(name="Motivo", value=razao, inline=False)
        dm_embed.add_field(name="Moderador", value=str(interaction.user), inline=True)
        dm_embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        try:
            await membro.send(embed=dm_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass  # DMs fechadas

        await membro.ban(reason=f"[{interaction.user}] {razao}", delete_message_days=delete_dias)

        confirm = discord.Embed(
            title="🔨 Membro Banido",
            color=ERROR_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        confirm.add_field(name="Usuário", value=f"{membro} (`{membro.id}`)", inline=False)
        confirm.add_field(name="Motivo", value=razao, inline=False)
        confirm.add_field(name="Moderador", value=interaction.user.mention, inline=True)
        confirm.add_field(name="Mensagens excluídas", value=f"{delete_dias} dia(s)", inline=True)
        confirm.set_thumbnail(url=membro.display_avatar.url)
        confirm.set_footer(text=f"ID do usuário: {membro.id}")
        await interaction.followup.send(embed=confirm)

    # ── /mod kick ─────────────────────────────────────────────────────────

    @mod.command(name="kick", description="Expulsa um membro do servidor")
    @app_commands.describe(membro="Membro a ser expulso", razao="Motivo da expulsão")
    @app_commands.checks.has_permissions(kick_members=True)
    async def mod_kick(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        razao: str,
    ) -> None:
        await interaction.response.defer(ephemeral=False)

        if membro == interaction.user:
            return await interaction.followup.send(
                embed=discord.Embed(description="❌ Você não pode expulsar a si mesmo.", color=ERROR_COLOR),
                ephemeral=True,
            )
        if membro.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Você não pode expulsar alguém com cargo igual ou superior ao seu.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        dm_embed = discord.Embed(
            title="👢 Você foi expulso",
            description=f"Você foi expulso de **{interaction.guild.name}**.",
            color=WARNING_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        dm_embed.add_field(name="Motivo", value=razao, inline=False)
        dm_embed.add_field(name="Moderador", value=str(interaction.user), inline=True)
        dm_embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        try:
            await membro.send(embed=dm_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

        await membro.kick(reason=f"[{interaction.user}] {razao}")

        confirm = discord.Embed(
            title="👢 Membro Expulso",
            color=WARNING_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        confirm.add_field(name="Usuário", value=f"{membro} (`{membro.id}`)", inline=False)
        confirm.add_field(name="Motivo", value=razao, inline=False)
        confirm.add_field(name="Moderador", value=interaction.user.mention, inline=True)
        confirm.set_thumbnail(url=membro.display_avatar.url)
        confirm.set_footer(text=f"ID do usuário: {membro.id}")
        await interaction.followup.send(embed=confirm)

    # ── /mod timeout ──────────────────────────────────────────────────────

    @mod.command(name="timeout", description="Coloca um membro em silêncio temporário")
    @app_commands.describe(
        membro="Membro a ser silenciado",
        duracao='Duração (ex: "10m", "1h", "1d", máx 28d)',
        razao="Motivo do silêncio",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mod_timeout(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        duracao: str,
        razao: str,
    ) -> None:
        await interaction.response.defer(ephemeral=False)

        delta = _parse_duration(duracao)
        if delta is None:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        "❌ Duração inválida. Use o formato `10m`, `1h`, `2d`, `1d12h30m`.\n"
                        "O máximo é **28 dias**."
                    ),
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        if membro.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Você não pode silenciar alguém com cargo igual ou superior ao seu.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        until = datetime.now(timezone.utc) + delta

        dm_embed = discord.Embed(
            title="🔇 Você foi silenciado",
            description=f"Você foi colocado em silêncio em **{interaction.guild.name}**.",
            color=WARNING_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        dm_embed.add_field(name="Duração", value=_fmt_duration(delta), inline=True)
        dm_embed.add_field(name="Motivo", value=razao, inline=False)
        dm_embed.add_field(name="Moderador", value=str(interaction.user), inline=True)
        try:
            await membro.send(embed=dm_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

        await membro.timeout(until, reason=f"[{interaction.user}] {razao}")

        confirm = discord.Embed(
            title="🔇 Membro Silenciado",
            color=WARNING_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        confirm.add_field(name="Usuário", value=f"{membro} (`{membro.id}`)", inline=False)
        confirm.add_field(name="Duração", value=_fmt_duration(delta), inline=True)
        confirm.add_field(name="Até", value=f"<t:{int(until.timestamp())}:f>", inline=True)
        confirm.add_field(name="Motivo", value=razao, inline=False)
        confirm.add_field(name="Moderador", value=interaction.user.mention, inline=True)
        confirm.set_thumbnail(url=membro.display_avatar.url)
        confirm.set_footer(text=f"ID do usuário: {membro.id}")
        await interaction.followup.send(embed=confirm)

    # ── /mod warn ─────────────────────────────────────────────────────────

    @mod.command(name="warn", description="Adiciona uma advertência a um membro")
    @app_commands.describe(membro="Membro a ser advertido", razao="Motivo da advertência")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mod_warn(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        razao: str,
    ) -> None:
        await interaction.response.defer(ephemeral=False)

        warn_id = await self.bot.db.add_warn(
            interaction.guild.id, membro.id, interaction.user.id, razao
        )
        all_warns = await self.bot.db.get_warns(interaction.guild.id, membro.id)
        total = len(all_warns)

        dm_embed = discord.Embed(
            title="⚠️ Você recebeu uma advertência",
            description=f"Você foi advertido em **{interaction.guild.name}**.",
            color=WARNING_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        dm_embed.add_field(name="Motivo", value=razao, inline=False)
        dm_embed.add_field(name="Moderador", value=str(interaction.user), inline=True)
        dm_embed.add_field(name="Total de advertências", value=str(total), inline=True)
        try:
            await membro.send(embed=dm_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

        confirm = discord.Embed(
            title="⚠️ Advertência Registrada",
            color=WARNING_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        confirm.add_field(name="Usuário", value=f"{membro} (`{membro.id}`)", inline=False)
        confirm.add_field(name="Motivo", value=razao, inline=False)
        confirm.add_field(name="Moderador", value=interaction.user.mention, inline=True)
        confirm.add_field(name="Nº da advertência", value=f"#{total} (ID: {warn_id})", inline=True)
        confirm.set_thumbnail(url=membro.display_avatar.url)
        confirm.set_footer(text=f"ID do usuário: {membro.id}")
        await interaction.followup.send(embed=confirm)

    # ── /mod warns ────────────────────────────────────────────────────────

    @mod.command(name="warns", description="Lista as advertências de um membro")
    @app_commands.describe(membro="Membro para consultar advertências")
    async def mod_warns(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
    ) -> None:
        await interaction.response.defer(ephemeral=False)

        warns = await self.bot.db.get_warns(interaction.guild.id, membro.id)

        if not warns:
            embed = discord.Embed(
                title="📋 Advertências",
                description=f"{membro.mention} não possui advertências.",
                color=SUCCESS_COLOR,
            )
            embed.set_thumbnail(url=membro.display_avatar.url)
            return await interaction.followup.send(embed=embed)

        # Paginate: 10 per page
        pages: list[discord.Embed] = []
        per_page = 10
        total_pages = (len(warns) + per_page - 1) // per_page

        for page_num in range(total_pages):
            chunk = warns[page_num * per_page : (page_num + 1) * per_page]
            embed = discord.Embed(
                title=f"📋 Advertências — {membro.display_name}",
                description=f"Total: **{len(warns)}** advertência(s)",
                color=WARNING_COLOR,
            )
            embed.set_thumbnail(url=membro.display_avatar.url)
            embed.set_footer(
                text=f"Página {page_num + 1}/{total_pages}  •  ID do usuário: {membro.id}"
            )

            for w in chunk:
                moderator = interaction.guild.get_member(w["moderator_id"])
                mod_mention = moderator.mention if moderator else f"<@{w['moderator_id']}>"

                # Parse date
                created = w["created_at"]
                if isinstance(created, str):
                    try:
                        dt = datetime.fromisoformat(created)
                        ts = int(dt.timestamp())
                        date_str = f"<t:{ts}:d>"
                    except ValueError:
                        date_str = created
                elif isinstance(created, (int, float)):
                    date_str = f"<t:{int(created)}:d>"
                else:
                    date_str = str(created)

                embed.add_field(
                    name=f"Advertência #{w['id']}",
                    value=(
                        f"**Motivo:** {w['reason']}\n"
                        f"**Moderador:** {mod_mention}\n"
                        f"**Data:** {date_str}"
                    ),
                    inline=False,
                )
            pages.append(embed)

        # Send with pagination buttons if multiple pages
        if len(pages) == 1:
            return await interaction.followup.send(embed=pages[0])

        view = _PaginatorView(pages, interaction.user)
        await interaction.followup.send(embed=pages[0], view=view)

    # ── /mod remover-warn ─────────────────────────────────────────────────

    @mod.command(name="remover-warn", description="Remove uma advertência pelo ID")
    @app_commands.describe(id="ID da advertência a remover")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mod_remover_warn(
        self,
        interaction: discord.Interaction,
        id: int,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        success = await self.bot.db.remove_warn(id, interaction.guild.id)
        if success:
            embed = discord.Embed(
                title="✅ Advertência Removida",
                description=f"A advertência com ID **{id}** foi removida com sucesso.",
                color=SUCCESS_COLOR,
            )
        else:
            embed = discord.Embed(
                title="❌ Advertência não encontrada",
                description=f"Não foi encontrada nenhuma advertência com ID **{id}** neste servidor.",
                color=ERROR_COLOR,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /mod limpar-warns ─────────────────────────────────────────────────

    @mod.command(name="limpar-warns", description="Remove todas as advertências de um membro")
    @app_commands.describe(membro="Membro cujas advertências serão removidas")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def mod_limpar_warns(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        count = await self.bot.db.clear_warns(interaction.guild.id, membro.id)
        if count > 0:
            embed = discord.Embed(
                title="🧹 Advertências Limpas",
                description=(
                    f"Todas as advertências de {membro.mention} foram removidas.\n"
                    f"Total removido: **{count}**"
                ),
                color=SUCCESS_COLOR,
            )
        else:
            embed = discord.Embed(
                title="ℹ️ Nenhuma Advertência",
                description=f"{membro.mention} não possuía advertências.",
                color=BOT_COLOR,
            )
        embed.set_thumbnail(url=membro.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /mod lock ─────────────────────────────────────────────────────────

    @mod.command(name="lock", description="Bloqueia o envio de mensagens em um canal")
    @app_commands.describe(
        canal="Canal a bloquear (padrão: canal atual)",
        razao="Motivo do bloqueio",
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def mod_lock(
        self,
        interaction: discord.Interaction,
        canal: Optional[discord.TextChannel] = None,
        razao: Optional[str] = "Sem motivo especificado",
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        target: discord.TextChannel = canal or interaction.channel  # type: ignore[assignment]
        everyone = interaction.guild.default_role

        await target.set_permissions(
            everyone,
            send_messages=False,
            reason=f"[{interaction.user}] {razao}",
        )

        lock_embed = discord.Embed(
            title="🔒 Canal Bloqueado",
            description=(
                f"Este canal foi bloqueado por {interaction.user.mention}.\n"
                f"**Motivo:** {razao}"
            ),
            color=ERROR_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        lock_embed.set_footer(text="Apenas moderadores podem enviar mensagens aqui.")
        await target.send(embed=lock_embed)

        confirm = discord.Embed(
            description=f"✅ {target.mention} foi bloqueado.",
            color=SUCCESS_COLOR,
        )
        await interaction.followup.send(embed=confirm, ephemeral=True)

    # ── /mod unlock ───────────────────────────────────────────────────────

    @mod.command(name="unlock", description="Desbloqueia o envio de mensagens em um canal")
    @app_commands.describe(canal="Canal a desbloquear (padrão: canal atual)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def mod_unlock(
        self,
        interaction: discord.Interaction,
        canal: Optional[discord.TextChannel] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        target: discord.TextChannel = canal or interaction.channel  # type: ignore[assignment]
        everyone = interaction.guild.default_role

        await target.set_permissions(
            everyone,
            send_messages=None,  # Restore to default (inherited)
            reason=f"[{interaction.user}] Desbloqueio de canal",
        )

        unlock_embed = discord.Embed(
            title="🔓 Canal Desbloqueado",
            description=(
                f"Este canal foi desbloqueado por {interaction.user.mention}.\n"
                "O envio de mensagens está liberado novamente."
            ),
            color=SUCCESS_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        await target.send(embed=unlock_embed)

        confirm = discord.Embed(
            description=f"✅ {target.mention} foi desbloqueado.",
            color=SUCCESS_COLOR,
        )
        await interaction.followup.send(embed=confirm, ephemeral=True)

    # ── /mod nuke ─────────────────────────────────────────────────────────

    @mod.command(name="nuke", description="Recria o canal (apaga todas as mensagens)")
    @app_commands.describe(canal="Canal a ser nukado (padrão: canal atual)")
    @app_commands.checks.has_permissions(manage_channels=True, administrator=True)
    async def mod_nuke(
        self,
        interaction: discord.Interaction,
        canal: Optional[discord.TextChannel] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        target: discord.TextChannel = canal or interaction.channel  # type: ignore[assignment]

        # Clone channel preserving everything
        new_channel = await target.clone(
            reason=f"[{interaction.user}] Nuke do canal #{target.name}",
        )
        # Restore position
        await new_channel.edit(position=target.position)
        # Delete original
        await target.delete(reason=f"[{interaction.user}] Nuke")

        nuke_embed = discord.Embed(
            title="💥 Canal Nukado",
            description=(
                f"Este canal foi recriado por {interaction.user.mention}.\n"
                "Todas as mensagens anteriores foram apagadas."
            ),
            color=ERROR_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        nuke_embed.set_footer(text="Canal limpo com sucesso.")
        await new_channel.send(embed=nuke_embed)

        try:
            confirm = discord.Embed(
                description=f"✅ Canal nukado e recriado como {new_channel.mention}.",
                color=SUCCESS_COLOR,
            )
            await interaction.followup.send(embed=confirm, ephemeral=True)
        except discord.NotFound:
            pass  # Original interaction channel was the nuked one

    # ══════════════════════════════════════════════════════════════════════
    # /limpar  (top-level)
    # ══════════════════════════════════════════════════════════════════════

    @app_commands.command(name="limpar", description="Apaga mensagens de um canal")
    @app_commands.describe(
        quantidade="Número de mensagens a apagar (1-100)",
        canal="Canal alvo (padrão: canal atual)",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def limpar(
        self,
        interaction: discord.Interaction,
        quantidade: app_commands.Range[int, 1, 100],
        canal: Optional[discord.TextChannel] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        target: discord.TextChannel = canal or interaction.channel  # type: ignore[assignment]
        deleted = await target.purge(limit=quantidade)

        embed = discord.Embed(
            title="🧹 Mensagens Apagadas",
            description=(
                f"**{len(deleted)}** mensagem(ns) apagada(s) em {target.mention}."
            ),
            color=SUCCESS_COLOR,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Solicitado por {interaction.user}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ══════════════════════════════════════════════════════════════════════
    # /slowmode  (top-level)
    # ══════════════════════════════════════════════════════════════════════

    @app_commands.command(
        name="slowmode",
        description="Define o modo lento de um canal",
    )
    @app_commands.describe(
        segundos="Intervalo em segundos (0 = desativado, máx 21600)",
        canal="Canal alvo (padrão: canal atual)",
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(
        self,
        interaction: discord.Interaction,
        segundos: app_commands.Range[int, 0, 21600],
        canal: Optional[discord.TextChannel] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        target: discord.TextChannel = canal or interaction.channel  # type: ignore[assignment]
        await target.edit(slowmode_delay=segundos)

        if segundos == 0:
            desc = f"✅ Modo lento desativado em {target.mention}."
        else:
            desc = f"✅ Modo lento de **{segundos}s** ativado em {target.mention}."

        embed = discord.Embed(description=desc, color=SUCCESS_COLOR)
        await interaction.followup.send(embed=embed, ephemeral=True)


# ── Pagination view ───────────────────────────────────────────────────────────

class _PaginatorView(discord.ui.View):
    """Simple prev/next button paginator for warns list."""

    def __init__(self, pages: list[discord.Embed], owner: discord.User | discord.Member) -> None:
        super().__init__(timeout=120)
        self.pages = pages
        self.owner = owner
        self.current = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current >= len(self.pages) - 1

    async def _check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message(
                "❌ Apenas quem usou o comando pode navegar entre as páginas.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="◀ Anterior", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check(interaction):
            return
        self.current -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="Próxima ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check(interaction):
            return
        self.current += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


# ── Setup ─────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
