"""
cogs/clans.py  –  Sistema de clãs para o Community Bot
discord.py 2.x  •  app_commands (slash)  •  Mensagens em português
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_COLOR, SUCCESS_COLOR, ERROR_COLOR, WARNING_COLOR

# ── Regex para validação de nome ──────────────────────────────────────────────

_NAME_RE = re.compile(r'^[a-zA-Z0-9 À-ÿ]+$')
_HEX_RE = re.compile(r'^#([0-9A-Fa-f]{6})$')

# ── Helper: parse hex color ───────────────────────────────────────────────────

def _parse_hex(hex_str: str) -> Optional[discord.Color]:
    """Parse #RRGGBB string into discord.Color, or None if invalid."""
    m = _HEX_RE.match(hex_str.strip())
    if not m:
        return None
    return discord.Color(int(m.group(1), 16))


def _hex_to_int(hex_str: str) -> int:
    """Convert #RRGGBB to int."""
    return int(hex_str.lstrip('#'), 16)


# ── XP Bonus export ───────────────────────────────────────────────────────────

async def get_clan_xp_bonus(bot: commands.Bot, user_id: int, guild_id: int) -> float:
    """
    Returns the XP bonus for a clan member based on clan size.
    +0.05 per 5 members (rounded down), capped at +1.0.
    1-4 members = 0.0, 5-9 = 0.05, 10-14 = 0.10, ..., 100+ = 1.0 (cap).
    """
    clan = await bot.db.get_user_clan(user_id, guild_id)
    if not clan:
        return 0.0
    members = await bot.db.get_clan_members(clan['id'])
    count = len(members)
    bonus = min((count // 5) * 0.05, 1.0)
    return bonus


# ── Confirm / Deny view for deletion ─────────────────────────────────────────

class ConfirmDeleteView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=30)
        self.owner_id = owner_id
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Apenas o dono do clã pode confirmar esta ação.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        await interaction.response.send_message(
            embed=discord.Embed(description="❌ Exclusão cancelada.", color=WARNING_COLOR),
            ephemeral=True,
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


# ── Paginated list view ───────────────────────────────────────────────────────

class ClanListView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], invoker_id: int):
        super().__init__(timeout=60)
        self.pages = pages
        self.current = 0
        self.invoker_id = invoker_id
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "Apenas quem usou o comando pode navegar.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="◀ Anterior", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="Próximo ▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


# ── Main Cog ──────────────────────────────────────────────────────────────────

class Clans(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Maps user_id → clan_id for pending invites (in-memory mirror of DB)
        self._pending_invites: dict[int, int] = {}

    # ── Group ─────────────────────────────────────────────────────────────────

    clan_group = app_commands.Group(
        name="clan",
        description="Comandos de gerenciamento de clãs",
    )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_channel_overwrites(
        self, guild: discord.Guild, role: discord.Role
    ) -> dict:
        return {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            role: discord.PermissionOverwrite(view_channel=True),
        }

    async def _get_member_role_label(self, member_role: str) -> str:
        mapping = {"owner": "👑 Dono", "admin": "⭐ Admin", "member": "👤 Membro"}
        return mapping.get(member_role, "👤 Membro")

    async def _is_owner_or_admin(
        self, clan_id: int, user_id: int
    ) -> tuple[bool, str]:
        """Returns (True, member_role) if user is owner or admin, else (False, '')."""
        members = await self.bot.db.get_clan_members(clan_id)
        for m in members:
            if m["user_id"] == user_id:
                if m["member_role"] in ("owner", "admin"):
                    return True, m["member_role"]
                return False, m["member_role"]
        return False, ""

    async def _get_user_member_role(self, clan_id: int, user_id: int) -> Optional[str]:
        members = await self.bot.db.get_clan_members(clan_id)
        for m in members:
            if m["user_id"] == user_id:
                return m["member_role"]
        return None

    # ── /clan criar ───────────────────────────────────────────────────────────

    @clan_group.command(name="criar", description="Cria um novo clã")
    @app_commands.describe(
        nome="Nome do clã (máx. 24 caracteres, letras e números)",
        cor="Cor do clã em hexadecimal (ex: #FF5733). Padrão: #5865F2",
        descricao="Descrição do clã (máx. 100 caracteres)",
    )
    async def criar(
        self,
        interaction: discord.Interaction,
        nome: str,
        cor: str = "#5865F2",
        descricao: str = "",
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        # ── Validations ────────────────────────────────────────────────────
        if len(nome) > 24:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ O nome do clã deve ter no máximo 24 caracteres.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        if not _NAME_RE.match(nome):
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ O nome do clã pode conter apenas letras, números e espaços.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        if len(descricao) > 100:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ A descrição deve ter no máximo 100 caracteres.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        parsed_color = _parse_hex(cor)
        if parsed_color is None:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Cor inválida. Use o formato hexadecimal, ex: `#FF5733`.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Check if user is already in a clan
        existing = await self.bot.db.get_user_clan(user.id, guild.id)
        if existing:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Você já faz parte do clã **{existing['name']}**. Saia antes de criar um novo.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Check if name is taken
        name_taken = await self.bot.db.get_clan_by_name(guild.id, nome)
        if name_taken:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Já existe um clã com o nome **{nome}**.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # ── Create Discord structures ──────────────────────────────────────
        # 1. Role
        try:
            role = await guild.create_role(
                name=nome,
                color=parsed_color,
                mentionable=False,
                hoist=False,
                reason=f"Clã criado por {user}",
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Não tenho permissão para criar cargos no servidor.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
        except discord.HTTPException as e:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Erro ao criar cargo: {e}",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        overwrites = self._make_channel_overwrites(guild, role)

        # 2. Category
        try:
            category = await guild.create_category(
                name=f"🛡️ {nome}",
                overwrites=overwrites,
                reason=f"Clã {nome}",
            )
        except discord.Forbidden:
            await role.delete(reason="Rollback: falha ao criar categoria")
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Não tenho permissão para criar categorias no servidor.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await role.delete(reason="Rollback: falha ao criar categoria")
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Erro ao criar categoria: {e}",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # 3. Text channel
        text_channel_name = nome.lower().replace(' ', '-')
        try:
            text_channel = await guild.create_text_channel(
                name=text_channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Clã {nome}",
            )
        except discord.Forbidden:
            await category.delete(reason="Rollback")
            await role.delete(reason="Rollback")
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Não tenho permissão para criar canais de texto.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await category.delete(reason="Rollback")
            await role.delete(reason="Rollback")
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Erro ao criar canal de texto: {e}",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # 4. Voice channel
        try:
            voice_channel = await guild.create_voice_channel(
                name=nome,
                category=category,
                overwrites=overwrites,
                reason=f"Clã {nome}",
            )
        except discord.Forbidden:
            await text_channel.delete(reason="Rollback")
            await category.delete(reason="Rollback")
            await role.delete(reason="Rollback")
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Não tenho permissão para criar canais de voz.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await text_channel.delete(reason="Rollback")
            await category.delete(reason="Rollback")
            await role.delete(reason="Rollback")
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Erro ao criar canal de voz: {e}",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # 5. Welcome message in text channel
        welcome_embed = discord.Embed(
            title=f"🛡️ Clã {nome} criado!",
            description=f"Bem-vindo(a), {user.mention}! Este é o canal do seu clã.",
            color=parsed_color,
        )
        if descricao:
            welcome_embed.add_field(name="Descrição", value=descricao, inline=False)
        welcome_embed.set_footer(text="Use /clan convidar para recrutar membros!")
        try:
            await text_channel.send(embed=welcome_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

        # 6. Save to database
        color_hex = cor.upper() if cor.startswith('#') else f"#{cor.upper()}"
        clan_id = await self.bot.db.create_clan(
            guild_id=guild.id,
            name=nome,
            owner_id=user.id,
            role_id=role.id,
            text_channel_id=text_channel.id,
            voice_channel_id=voice_channel.id,
            color_hex=color_hex,
            description=descricao,
        )

        # 7. Add owner as member
        await self.bot.db.add_clan_member(clan_id, user.id, member_role='owner')

        # 8. Assign role to owner
        try:
            await user.add_roles(role, reason=f"Dono do clã {nome}")
        except (discord.Forbidden, discord.HTTPException):
            pass

        success_embed = discord.Embed(
            title="✅ Clã criado com sucesso!",
            description=(
                f"O clã **{nome}** foi criado!\n\n"
                f"**Cargo:** {role.mention}\n"
                f"**Canal:** {text_channel.mention}"
            ),
            color=SUCCESS_COLOR,
        )
        success_embed.set_footer(text=f"ID do clã: {clan_id}")
        await interaction.followup.send(embed=success_embed, ephemeral=True)

    # ── /clan convidar ────────────────────────────────────────────────────────

    @clan_group.command(name="convidar", description="Convida um membro para o seu clã")
    @app_commands.describe(membro="Membro a ser convidado")
    async def convidar(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        # Get invoker's clan
        clan = await self.bot.db.get_user_clan(user.id, guild.id)
        if not clan:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Você não faz parte de nenhum clã.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Check if invoker is owner or admin
        authorized, _ = await self._is_owner_or_admin(clan['id'], user.id)
        if not authorized:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Apenas o dono ou administradores do clã podem convidar membros.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Target cannot be a bot
        if membro.bot:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Você não pode convidar bots para o clã.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Target cannot already be in a clan
        target_clan = await self.bot.db.get_user_clan(membro.id, guild.id)
        if target_clan:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ {membro.mention} já faz parte do clã **{target_clan['name']}**.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Check for existing pending invite
        if membro.id in self._pending_invites:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ {membro.mention} já tem um convite pendente.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Create invite in DB and memory
        await self.bot.db.create_clan_invite(clan['id'], membro.id)
        self._pending_invites[membro.id] = clan['id']

        invite_embed = discord.Embed(
            title="📨 Convite de Clã",
            description=(
                f"{membro.mention}, você foi convidado(a) para o clã **{clan['name']}**!\n\n"
                f"Use `/clan aceitar` para entrar ou `/clan recusar` para recusar.\n"
                f"Este convite expira em **120 segundos**."
            ),
            color=BOT_COLOR,
        )
        invite_embed.set_footer(text=f"Convidado por {user.display_name}")

        try:
            await interaction.channel.send(embed=invite_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

        await interaction.followup.send(
            embed=discord.Embed(
                description=f"✅ Convite enviado para {membro.mention}.",
                color=SUCCESS_COLOR,
            ),
            ephemeral=True,
        )

        # Cleanup invite after 120 seconds
        async def _cleanup_invite():
            await asyncio.sleep(120)
            if self._pending_invites.get(membro.id) == clan['id']:
                del self._pending_invites[membro.id]
                try:
                    await self.bot.db.remove_clan_invite(clan['id'], membro.id)
                except Exception:
                    pass

        asyncio.create_task(_cleanup_invite())

    # ── /clan aceitar ─────────────────────────────────────────────────────────

    @clan_group.command(name="aceitar", description="Aceita um convite de clã pendente")
    async def aceitar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        guild = interaction.guild

        # Check for pending invite in memory
        clan_id = self._pending_invites.get(user.id)
        if clan_id is None:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Você não possui nenhum convite de clã pendente.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Verify invite in DB
        invite_valid = await self.bot.db.get_clan_invite(clan_id, user.id)
        if not invite_valid:
            # Clean up stale memory entry
            self._pending_invites.pop(user.id, None)
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Convite expirado ou inválido.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Make sure user is still not in a clan
        existing = await self.bot.db.get_user_clan(user.id, guild.id)
        if existing:
            self._pending_invites.pop(user.id, None)
            await self.bot.db.remove_clan_invite(clan_id, user.id)
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ Você já faz parte do clã **{existing['name']}**.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Fetch clan data
        clan = await self.bot.db.get_clan(clan_id)
        if not clan:
            self._pending_invites.pop(user.id, None)
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ O clã não existe mais.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Add member to clan
        await self.bot.db.add_clan_member(clan_id, user.id, member_role='member')

        # Assign clan role
        role = guild.get_role(clan['role_id'])
        if role:
            try:
                await user.add_roles(role, reason=f"Entrou no clã {clan['name']}")
            except (discord.Forbidden, discord.HTTPException):
                pass

        # Remove invite
        self._pending_invites.pop(user.id, None)
        await self.bot.db.remove_clan_invite(clan_id, user.id)

        # Send welcome in clan text channel
        text_channel = guild.get_channel(clan['text_channel_id'])
        if text_channel:
            welcome = discord.Embed(
                title="🎉 Novo membro!",
                description=f"{user.mention} entrou no clã **{clan['name']}**! Bem-vindo(a)!",
                color=SUCCESS_COLOR,
            )
            try:
                await text_channel.send(embed=welcome)
            except (discord.Forbidden, discord.HTTPException):
                pass

        await interaction.followup.send(
            embed=discord.Embed(
                description=f"✅ Você entrou no clã **{clan['name']}**!",
                color=SUCCESS_COLOR,
            ),
            ephemeral=True,
        )

    # ── /clan recusar ─────────────────────────────────────────────────────────

    @clan_group.command(name="recusar", description="Recusa um convite de clã pendente")
    async def recusar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user

        clan_id = self._pending_invites.get(user.id)
        if clan_id is None:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Você não possui nenhum convite de clã pendente.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        clan = await self.bot.db.get_clan(clan_id)
        clan_name = clan['name'] if clan else "desconhecido"

        self._pending_invites.pop(user.id, None)
        try:
            await self.bot.db.remove_clan_invite(clan_id, user.id)
        except Exception:
            pass

        # Notify in clan channel
        if clan:
            text_channel = interaction.guild.get_channel(clan['text_channel_id'])
            if text_channel:
                decline_embed = discord.Embed(
                    description=f"**{user.display_name}** recusou o convite para o clã.",
                    color=WARNING_COLOR,
                )
                try:
                    await text_channel.send(embed=decline_embed)
                except (discord.Forbidden, discord.HTTPException):
                    pass

        await interaction.followup.send(
            embed=discord.Embed(
                description=f"✅ Você recusou o convite para o clã **{clan_name}**.",
                color=SUCCESS_COLOR,
            ),
            ephemeral=True,
        )

    # ── /clan kick ────────────────────────────────────────────────────────────

    @clan_group.command(name="kick", description="Remove um membro do clã")
    @app_commands.describe(membro="Membro a ser removido")
    async def kick(self, interaction: discord.Interaction, membro: discord.Member):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        clan = await self.bot.db.get_user_clan(user.id, guild.id)
        if not clan:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Você não faz parte de nenhum clã.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        authorized, invoker_role = await self._is_owner_or_admin(clan['id'], user.id)
        if not authorized:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Apenas o dono ou administradores do clã podem remover membros.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        target_role = await self._get_user_member_role(clan['id'], membro.id)
        if target_role is None:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ {membro.mention} não é membro deste clã.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        if target_role == 'owner':
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Não é possível remover o dono do clã.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Admins cannot kick other admins (only owner can)
        if target_role == 'admin' and invoker_role != 'owner':
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Apenas o dono pode remover administradores.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        await self.bot.db.remove_clan_member(clan['id'], membro.id)

        # Remove clan role
        role = guild.get_role(clan['role_id'])
        if role:
            try:
                await membro.remove_roles(role, reason=f"Removido do clã {clan['name']}")
            except (discord.Forbidden, discord.HTTPException):
                pass

        # Notify in clan channel
        text_channel = guild.get_channel(clan['text_channel_id'])
        if text_channel:
            kick_embed = discord.Embed(
                title="👢 Membro removido",
                description=f"**{membro.display_name}** foi removido do clã.",
                color=WARNING_COLOR,
            )
            try:
                await text_channel.send(embed=kick_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        await interaction.followup.send(
            embed=discord.Embed(
                description=f"✅ {membro.mention} foi removido do clã **{clan['name']}**.",
                color=SUCCESS_COLOR,
            ),
            ephemeral=True,
        )

    # ── /clan promover ────────────────────────────────────────────────────────

    @clan_group.command(name="promover", description="Promove um membro a administrador")
    @app_commands.describe(membro="Membro a ser promovido")
    async def promover(self, interaction: discord.Interaction, membro: discord.Member):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        clan = await self.bot.db.get_user_clan(user.id, guild.id)
        if not clan:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Você não faz parte de nenhum clã.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        invoker_role = await self._get_user_member_role(clan['id'], user.id)
        if invoker_role != 'owner':
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Apenas o dono do clã pode promover membros.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        target_role = await self._get_user_member_role(clan['id'], membro.id)
        if target_role is None:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ {membro.mention} não é membro deste clã.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        if target_role == 'owner':
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Não é possível promover acima do dono.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        if target_role == 'admin':
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ {membro.mention} já é administrador do clã.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Promote: remove then re-add as admin
        await self.bot.db.remove_clan_member(clan['id'], membro.id)
        await self.bot.db.add_clan_member(clan['id'], membro.id, member_role='admin')

        text_channel = guild.get_channel(clan['text_channel_id'])
        if text_channel:
            promo_embed = discord.Embed(
                title="⭐ Novo Administrador",
                description=f"{membro.mention} foi promovido(a) a **Administrador** do clã **{clan['name']}**!",
                color=SUCCESS_COLOR,
            )
            try:
                await text_channel.send(embed=promo_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        await interaction.followup.send(
            embed=discord.Embed(
                description=f"✅ {membro.mention} foi promovido(a) a **Administrador** do clã.",
                color=SUCCESS_COLOR,
            ),
            ephemeral=True,
        )

    # ── /clan deixar ──────────────────────────────────────────────────────────

    @clan_group.command(name="deixar", description="Sai do seu clã atual")
    async def deixar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        clan = await self.bot.db.get_user_clan(user.id, guild.id)
        if not clan:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Você não faz parte de nenhum clã.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        member_role = await self._get_user_member_role(clan['id'], user.id)
        if member_role == 'owner':
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        "❌ Você é o dono do clã e não pode simplesmente sair.\n\n"
                        "Use `/clan deletar` para deletar o clã ou "
                        "`/clan transferir` para transferir a liderança."
                    ),
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        await self.bot.db.remove_clan_member(clan['id'], user.id)

        # Remove clan role
        role = guild.get_role(clan['role_id'])
        if role:
            try:
                await user.remove_roles(role, reason=f"Saiu do clã {clan['name']}")
            except (discord.Forbidden, discord.HTTPException):
                pass

        text_channel = guild.get_channel(clan['text_channel_id'])
        if text_channel:
            leave_embed = discord.Embed(
                description=f"**{user.display_name}** saiu do clã.",
                color=WARNING_COLOR,
            )
            try:
                await text_channel.send(embed=leave_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        await interaction.followup.send(
            embed=discord.Embed(
                description=f"✅ Você saiu do clã **{clan['name']}**.",
                color=SUCCESS_COLOR,
            ),
            ephemeral=True,
        )

    # ── /clan deletar ─────────────────────────────────────────────────────────

    @clan_group.command(name="deletar", description="Deleta o seu clã permanentemente")
    async def deletar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        clan = await self.bot.db.get_user_clan(user.id, guild.id)
        if not clan:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Você não faz parte de nenhum clã.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        member_role = await self._get_user_member_role(clan['id'], user.id)
        if member_role != 'owner':
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Apenas o dono do clã pode deletá-lo.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Confirm view
        view = ConfirmDeleteView(owner_id=user.id)
        confirm_embed = discord.Embed(
            title="⚠️ Confirmar exclusão",
            description=(
                f"Você tem certeza que deseja deletar o clã **{clan['name']}**?\n\n"
                "⚠️ **Esta ação é irreversível!** Todos os canais, cargo e dados serão removidos.\n\n"
                "Esta confirmação expira em **30 segundos**."
            ),
            color=WARNING_COLOR,
        )
        msg = await interaction.followup.send(embed=confirm_embed, view=view, ephemeral=True)

        await view.wait()

        if not view.confirmed:
            return

        # ── Delete everything ──────────────────────────────────────────────
        members = await self.bot.db.get_clan_members(clan['id'])

        # Remove role from all members
        role = guild.get_role(clan['role_id'])
        if role:
            for m_data in members:
                member_obj = guild.get_member(m_data['user_id'])
                if member_obj:
                    try:
                        await member_obj.remove_roles(role, reason=f"Clã {clan['name']} deletado")
                    except (discord.Forbidden, discord.HTTPException):
                        pass

        # Delete text channel
        text_channel = guild.get_channel(clan['text_channel_id'])
        if text_channel:
            try:
                await text_channel.delete(reason=f"Clã {clan['name']} deletado")
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                pass

        # Delete voice channel
        voice_channel = guild.get_channel(clan['voice_channel_id'])
        if voice_channel:
            try:
                await voice_channel.delete(reason=f"Clã {clan['name']} deletado")
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                pass

        # Delete category (must be empty first — channels already deleted)
        # Find category by checking parent of text_channel (already deleted), so we need to find it
        # We stored no category_id in DB, so try to find by name
        category = discord.utils.get(guild.categories, name=f"🛡️ {clan['name']}")
        if category:
            try:
                await category.delete(reason=f"Clã {clan['name']} deletado")
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                pass

        # Delete role
        if role:
            try:
                await role.delete(reason=f"Clã {clan['name']} deletado")
            except (discord.Forbidden, discord.HTTPException, discord.NotFound):
                pass

        # Delete from DB
        await self.bot.db.delete_clan(clan['id'])

        # Clear any pending invites for this clan
        to_remove = [uid for uid, cid in self._pending_invites.items() if cid == clan['id']]
        for uid in to_remove:
            self._pending_invites.pop(uid, None)

        done_embed = discord.Embed(
            title="🗑️ Clã deletado",
            description=f"O clã **{clan['name']}** foi permanentemente deletado.",
            color=SUCCESS_COLOR,
        )
        try:
            await interaction.channel.send(embed=done_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ── /clan transferir ──────────────────────────────────────────────────────

    @clan_group.command(name="transferir", description="Transfere a liderança do clã para outro membro")
    @app_commands.describe(membro="Membro que receberá a liderança")
    async def transferir(self, interaction: discord.Interaction, membro: discord.Member):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        clan = await self.bot.db.get_user_clan(user.id, guild.id)
        if not clan:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Você não faz parte de nenhum clã.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        invoker_role = await self._get_user_member_role(clan['id'], user.id)
        if invoker_role != 'owner':
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Apenas o dono do clã pode transferir a liderança.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        if membro.id == user.id:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Você não pode transferir a liderança para si mesmo.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        target_role = await self._get_user_member_role(clan['id'], membro.id)
        if target_role is None:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description=f"❌ {membro.mention} não é membro deste clã.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Update owner in DB
        await self.bot.db.update_clan(clan['id'], owner_id=membro.id)

        # Update member roles: old owner → member, new owner → owner
        await self.bot.db.remove_clan_member(clan['id'], user.id)
        await self.bot.db.add_clan_member(clan['id'], user.id, member_role='member')

        await self.bot.db.remove_clan_member(clan['id'], membro.id)
        await self.bot.db.add_clan_member(clan['id'], membro.id, member_role='owner')

        text_channel = guild.get_channel(clan['text_channel_id'])
        if text_channel:
            transfer_embed = discord.Embed(
                title="👑 Nova Liderança",
                description=(
                    f"{membro.mention} é o(a) novo(a) dono(a) do clã **{clan['name']}**!\n"
                    f"Parabéns, {membro.mention}!"
                ),
                color=BOT_COLOR,
            )
            try:
                await text_channel.send(embed=transfer_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

        await interaction.followup.send(
            embed=discord.Embed(
                description=f"✅ Liderança do clã **{clan['name']}** transferida para {membro.mention}.",
                color=SUCCESS_COLOR,
            ),
            ephemeral=True,
        )

    # ── /clan info ────────────────────────────────────────────────────────────

    @clan_group.command(name="info", description="Exibe informações sobre um clã")
    @app_commands.describe(
        nome_ou_membro="Nome do clã ou membro (opcional — padrão: seu próprio clã)"
    )
    async def info(
        self,
        interaction: discord.Interaction,
        nome_ou_membro: str = "",
    ):
        await interaction.response.defer()
        guild = interaction.guild
        user = interaction.user
        clan = None

        if nome_ou_membro:
            # Try as member mention / ID / name
            member_obj: Optional[discord.Member] = None
            # Check if it's a mention
            if nome_ou_membro.startswith('<@') and nome_ou_membro.endswith('>'):
                raw = nome_ou_membro.strip('<@!>')
                if raw.isdigit():
                    member_obj = guild.get_member(int(raw))
            else:
                # Try to find by display name or username
                member_obj = guild.get_member_named(nome_ou_membro)

            if member_obj:
                clan = await self.bot.db.get_user_clan(member_obj.id, guild.id)

            if not clan:
                # Try as clan name
                clan = await self.bot.db.get_clan_by_name(guild.id, nome_ou_membro)
        else:
            # Default: user's own clan
            clan = await self.bot.db.get_user_clan(user.id, guild.id)

        if not clan:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Clã não encontrado.",
                    color=ERROR_COLOR,
                ),
            )

        members = await self.bot.db.get_clan_members(clan['id'])
        member_count = len(members)

        # Find owner
        owner_id = clan['owner_id']
        owner = guild.get_member(owner_id)
        owner_display = owner.mention if owner else f"<@{owner_id}>"

        # XP bonus
        xp_bonus = min((member_count // 5) * 0.05, 1.0)

        # Color
        color_int = _hex_to_int(clan.get('color_hex', '#5865F2'))

        embed = discord.Embed(
            title=f"🛡️ {clan['name']}",
            description=clan.get('description') or "*Sem descrição.*",
            color=color_int,
        )
        embed.add_field(name="👑 Dono", value=owner_display, inline=True)
        embed.add_field(name="👥 Membros", value=str(member_count), inline=True)
        embed.add_field(name="⭐ Bônus de XP", value=f"+{xp_bonus:.0%}", inline=True)
        embed.add_field(name="🎨 Cor", value=clan.get('color_hex', '#5865F2'), inline=True)

        # Creation date
        created_at = clan.get('created_at')
        if created_at:
            if isinstance(created_at, str):
                try:
                    created_dt = datetime.fromisoformat(created_at)
                    embed.add_field(
                        name="📅 Criado em",
                        value=discord.utils.format_dt(created_dt, style='D'),
                        inline=True,
                    )
                except ValueError:
                    embed.add_field(name="📅 Criado em", value=created_at, inline=True)
            elif hasattr(created_at, 'strftime'):
                embed.add_field(
                    name="📅 Criado em",
                    value=discord.utils.format_dt(created_at, style='D'),
                    inline=True,
                )

        # Member list (up to 15)
        role_emojis = {'owner': '👑', 'admin': '⭐', 'member': '👤'}
        if members:
            # Sort: owner first, then admin, then member
            role_order = {'owner': 0, 'admin': 1, 'member': 2}
            sorted_members = sorted(members, key=lambda m: role_order.get(m.get('member_role', 'member'), 2))
            lines = []
            for m_data in sorted_members[:15]:
                m_obj = guild.get_member(m_data['user_id'])
                m_name = m_obj.display_name if m_obj else f"<@{m_data['user_id']}>"
                emoji = role_emojis.get(m_data.get('member_role', 'member'), '👤')
                lines.append(f"{emoji} {m_name}")
            if len(members) > 15:
                lines.append(f"*...e mais {len(members) - 15} membros*")
            embed.add_field(name="Membros", value="\n".join(lines), inline=False)

        role = guild.get_role(clan['role_id'])
        if role:
            embed.set_footer(text=f"Cargo: {role.name}")

        await interaction.followup.send(embed=embed)

    # ── /clan lista ───────────────────────────────────────────────────────────

    @clan_group.command(name="lista", description="Lista todos os clãs do servidor")
    async def lista(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild

        all_clans = await self.bot.db.get_all_clans(guild.id)

        if not all_clans:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Nenhum clã encontrado neste servidor.",
                    color=ERROR_COLOR,
                )
            )

        # Build pages (5 clans per page)
        per_page = 5
        pages: list[discord.Embed] = []
        total_pages = (len(all_clans) + per_page - 1) // per_page

        for page_idx in range(total_pages):
            chunk = all_clans[page_idx * per_page:(page_idx + 1) * per_page]
            embed = discord.Embed(
                title=f"🛡️ Clãs do servidor — {guild.name}",
                color=BOT_COLOR,
            )
            embed.set_footer(text=f"Página {page_idx + 1}/{total_pages} • {len(all_clans)} clãs no total")

            for clan in chunk:
                members = await self.bot.db.get_clan_members(clan['id'])
                member_count = len(members)
                owner = guild.get_member(clan['owner_id'])
                owner_name = owner.display_name if owner else f"ID {clan['owner_id']}"

                created_at = clan.get('created_at', '')
                created_str = ''
                if created_at:
                    if isinstance(created_at, str):
                        try:
                            created_dt = datetime.fromisoformat(created_at)
                            created_str = discord.utils.format_dt(created_dt, style='d')
                        except ValueError:
                            created_str = str(created_at)
                    elif hasattr(created_at, 'strftime'):
                        created_str = discord.utils.format_dt(created_at, style='d')

                embed.add_field(
                    name=f"🛡️ {clan['name']}",
                    value=(
                        f"👑 Dono: **{owner_name}**\n"
                        f"👥 Membros: **{member_count}**\n"
                        f"📅 Criado: {created_str or 'N/A'}"
                    ),
                    inline=True,
                )

            pages.append(embed)

        if len(pages) == 1:
            await interaction.followup.send(embed=pages[0])
        else:
            view = ClanListView(pages=pages, invoker_id=interaction.user.id)
            await interaction.followup.send(embed=pages[0], view=view)

    # ── /clan editar ──────────────────────────────────────────────────────────

    @clan_group.command(name="editar", description="Edita as configurações do seu clã")
    @app_commands.describe(
        nome="Novo nome do clã (opcional)",
        descricao="Nova descrição (opcional)",
        cor="Nova cor em hexadecimal, ex: #FF5733 (opcional)",
    )
    async def editar(
        self,
        interaction: discord.Interaction,
        nome: str = "",
        descricao: str = "",
        cor: str = "",
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        clan = await self.bot.db.get_user_clan(user.id, guild.id)
        if not clan:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Você não faz parte de nenhum clã.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        member_role = await self._get_user_member_role(clan['id'], user.id)
        if member_role != 'owner':
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Apenas o dono do clã pode editá-lo.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        if not nome and not descricao and not cor:
            return await interaction.followup.send(
                embed=discord.Embed(
                    description="❌ Forneça pelo menos um campo para editar (`nome`, `descricao` ou `cor`).",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )

        # Validate fields
        new_name: Optional[str] = None
        new_desc: Optional[str] = None
        new_color: Optional[discord.Color] = None
        new_color_hex: Optional[str] = None

        if nome:
            if len(nome) > 24:
                return await interaction.followup.send(
                    embed=discord.Embed(
                        description="❌ O nome do clã deve ter no máximo 24 caracteres.",
                        color=ERROR_COLOR,
                    ),
                    ephemeral=True,
                )
            if not _NAME_RE.match(nome):
                return await interaction.followup.send(
                    embed=discord.Embed(
                        description="❌ O nome do clã pode conter apenas letras, números e espaços.",
                        color=ERROR_COLOR,
                    ),
                    ephemeral=True,
                )
            # Check if new name is taken by another clan
            existing = await self.bot.db.get_clan_by_name(guild.id, nome)
            if existing and existing['id'] != clan['id']:
                return await interaction.followup.send(
                    embed=discord.Embed(
                        description=f"❌ Já existe um clã com o nome **{nome}**.",
                        color=ERROR_COLOR,
                    ),
                    ephemeral=True,
                )
            new_name = nome

        if descricao:
            if len(descricao) > 100:
                return await interaction.followup.send(
                    embed=discord.Embed(
                        description="❌ A descrição deve ter no máximo 100 caracteres.",
                        color=ERROR_COLOR,
                    ),
                    ephemeral=True,
                )
            new_desc = descricao

        if cor:
            parsed = _parse_hex(cor)
            if parsed is None:
                return await interaction.followup.send(
                    embed=discord.Embed(
                        description="❌ Cor inválida. Use o formato hexadecimal, ex: `#FF5733`.",
                        color=ERROR_COLOR,
                    ),
                    ephemeral=True,
                )
            new_color = parsed
            new_color_hex = cor.upper() if cor.startswith('#') else f"#{cor.upper()}"

        changes: dict = {}
        if new_name:
            changes['name'] = new_name
        if new_desc is not None:
            changes['description'] = new_desc
        if new_color_hex:
            changes['color_hex'] = new_color_hex

        if changes:
            await self.bot.db.update_clan(clan['id'], **changes)

        # Update role color
        role = guild.get_role(clan['role_id'])
        if role and new_color:
            try:
                await role.edit(color=new_color, reason=f"Cor do clã {clan['name']} atualizada")
            except (discord.Forbidden, discord.HTTPException) as e:
                await interaction.followup.send(
                    embed=discord.Embed(
                        description=f"⚠️ Não foi possível atualizar a cor do cargo: {e}",
                        color=WARNING_COLOR,
                    ),
                    ephemeral=True,
                )

        # Update role name and channel names if name changed
        if new_name:
            if role:
                try:
                    await role.edit(name=new_name, reason=f"Clã renomeado para {new_name}")
                except (discord.Forbidden, discord.HTTPException) as e:
                    await interaction.followup.send(
                        embed=discord.Embed(
                            description=f"⚠️ Não foi possível renomear o cargo: {e}",
                            color=WARNING_COLOR,
                        ),
                        ephemeral=True,
                    )

            # Update text channel
            text_channel = guild.get_channel(clan['text_channel_id'])
            if text_channel:
                new_text_name = new_name.lower().replace(' ', '-')
                try:
                    await text_channel.edit(
                        name=new_text_name, reason=f"Clã renomeado para {new_name}"
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass

            # Update voice channel
            voice_channel = guild.get_channel(clan['voice_channel_id'])
            if voice_channel:
                try:
                    await voice_channel.edit(
                        name=new_name, reason=f"Clã renomeado para {new_name}"
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass

            # Update category
            old_category = discord.utils.get(guild.categories, name=f"🛡️ {clan['name']}")
            if old_category:
                try:
                    await old_category.edit(
                        name=f"🛡️ {new_name}", reason=f"Clã renomeado para {new_name}"
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass

        # Build result embed
        updated_parts = []
        if new_name:
            updated_parts.append(f"**Nome:** {new_name}")
        if new_desc is not None:
            updated_parts.append(f"**Descrição:** {new_desc or '*removida*'}")
        if new_color_hex:
            updated_parts.append(f"**Cor:** {new_color_hex}")

        result_embed = discord.Embed(
            title="✅ Clã atualizado",
            description="\n".join(updated_parts) if updated_parts else "Nenhuma alteração realizada.",
            color=SUCCESS_COLOR,
        )
        await interaction.followup.send(embed=result_embed, ephemeral=True)


# ── Setup ─────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot):
    await bot.add_cog(Clans(bot))
