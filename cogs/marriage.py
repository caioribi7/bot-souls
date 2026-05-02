import asyncio
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from config import (
    BOT_COLOR,
    SUCCESS_COLOR,
    ERROR_COLOR,
    WARNING_COLOR,
    COIN_EMOJI,
    WEDDING_GIF_URL,
)


# ─── Godparent utility (called from levels.py) ────────────────────────────────

async def get_godparent_xp_bonus(bot: commands.Bot, user_id: int, guild_id: int) -> float:
    """
    Returns 0.15 if the user is a godparent in any active marriage in the guild,
    0.0 otherwise. Called from levels.py to apply an XP multiplier.
    """
    marriages = await bot.db.get_godparent_marriages(user_id, guild_id)
    return 0.15 if marriages else 0.0


# ─── Embeds ───────────────────────────────────────────────────────────────────

WEDDING_COLOR = 0xFF69B4  # hot pink


def _proposal_embed(proposer: discord.Member, target: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        title="💍 Pedido de Casamento",
        description=(
            f"{proposer.mention} propôs casamento para {target.mention}!\n\n"
            f"Use `/casar aceitar` para aceitar ou\n"
            f"`/casar recusar` para recusar.\n\n"
            f"*Este pedido expira em 2 minutos.*"
        ),
        color=WEDDING_COLOR,
    )
    embed.set_thumbnail(url=proposer.display_avatar.url)
    embed.set_footer(text="💌 Que o amor floresça!")
    return embed


def _wedding_embed(user1: discord.Member, user2: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        title="💍 Casamento Realizado!",
        description=(
            f"✨ **{user1.mention}** e **{user2.mention}** agora são casados! 🎉\n\n"
            "Que este seja o começo de uma linda história juntos.\n"
            "❤️ Felicidades ao novo casal! ❤️"
        ),
        color=WEDDING_COLOR,
    )
    embed.set_image(url=WEDDING_GIF_URL)
    embed.set_footer(text="💒 Que sejam muito felizes!")
    return embed


def _divorce_embed(user1: discord.Member, user2: discord.Member | None) -> discord.Embed:
    name2 = user2.mention if user2 else "membro desconhecido"
    embed = discord.Embed(
        title="💔 Divórcio",
        description=(
            f"{user1.mention} e {name2} se divorciaram.\n\n"
            "*Às vezes os caminhos se separam...*"
        ),
        color=ERROR_COLOR,
    )
    embed.set_footer(text="O saldo do cofre foi mantido por ambos os cônjuges.")
    return embed


def _marriage_info_embed(
    marriage: dict,
    user1: discord.Member | None,
    user2: discord.Member | None,
    gp1: discord.Member | None,
    gp2: discord.Member | None,
) -> discord.Embed:
    u1_name = user1.mention if user1 else f"<@{marriage['user1_id']}>"
    u2_name = user2.mention if user2 else f"<@{marriage['user2_id']}>"

    embed = discord.Embed(
        title="💑 Informações do Casamento",
        color=WEDDING_COLOR,
    )
    embed.add_field(name="💍 Cônjuges", value=f"{u1_name}\n{u2_name}", inline=True)

    # Godparents
    gp_lines = []
    if marriage.get("godparent1_id"):
        gp_lines.append(gp1.mention if gp1 else f"<@{marriage['godparent1_id']}>")
    if marriage.get("godparent2_id"):
        gp_lines.append(gp2.mention if gp2 else f"<@{marriage['godparent2_id']}>")
    embed.add_field(
        name="🌹 Padrinhos",
        value="\n".join(gp_lines) if gp_lines else "*Nenhum padrinho ainda*",
        inline=True,
    )

    embed.add_field(
        name=f"{COIN_EMOJI} Cofre Compartilhado",
        value=f"**{marriage.get('shared_balance', 0):,}** moedas",
        inline=True,
    )

    # Parse married_at
    married_at_raw = marriage.get("married_at", "")
    try:
        if married_at_raw:
            dt = datetime.fromisoformat(married_at_raw)
            married_at_str = dt.strftime("%d/%m/%Y às %H:%M")
        else:
            married_at_str = "Desconhecido"
    except ValueError:
        married_at_str = married_at_raw

    embed.add_field(name="📅 Casados desde", value=married_at_str, inline=True)
    embed.set_footer(text="❤️ Que o amor seja eterno!")

    if user1:
        embed.set_thumbnail(url=user1.display_avatar.url)

    return embed


# ─── Confirm Divorce View ─────────────────────────────────────────────────────

class ConfirmDivorceView(discord.ui.View):
    def __init__(self, marriage_id: int, requester_id: int):
        super().__init__(timeout=30)
        self.marriage_id = marriage_id
        self.requester_id = requester_id
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "❌ Apenas quem solicitou o divórcio pode confirmar.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="✅ Confirmar Divórcio", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()

        db = interaction.client.db
        marriage = await db.get_marriage_by_id(self.marriage_id)
        if not marriage:
            await interaction.response.edit_message(
                content="❌ Casamento não encontrado.", view=None, embed=None
            )
            return

        await db.dissolve_marriage(self.marriage_id)

        guild = interaction.guild
        user1 = guild.get_member(marriage["user1_id"])
        user2 = guild.get_member(marriage["user2_id"])

        embed = _divorce_embed(
            user1 or interaction.user,
            user2 if user2 and user2.id != interaction.user.id else user1,
        )
        await interaction.response.edit_message(embed=embed, view=None, content=None)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            content="Divórcio cancelado.", embed=None, view=None
        )

    async def on_timeout(self):
        self.stop()


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Marriage(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # proposee_id → {"proposer_id": int, "guild_id": int}
        self._proposals: dict[int, dict] = {}

    casar_group = app_commands.Group(
        name="casar",
        description="Sistema de casamentos do servidor",
    )

    async def _start_divorce_flow(self, interaction: discord.Interaction):
        db = self.bot.db
        guild = interaction.guild
        user = interaction.user

        marriage = await db.get_marriage(user.id, guild.id)
        if not marriage:
            await interaction.response.send_message(
                "❌ Você não está casado(a).", ephemeral=True
            )
            return

        other_id = (
            marriage["user2_id"] if marriage["user1_id"] == user.id else marriage["user1_id"]
        )
        other = guild.get_member(other_id)
        other_mention = other.mention if other else f"<@{other_id}>"

        embed = discord.Embed(
            title="💔 Confirmar Divórcio",
            description=(
                f"Você tem certeza que deseja se divorciar de {other_mention}?\n\n"
                "⚠️ Esta ação é **irreversível**. O cofre compartilhado será preservado.\n"
                "Os padrinhos também serão removidos."
            ),
            color=WARNING_COLOR,
        )

        view = ConfirmDivorceView(
            marriage_id=marriage["id"], requester_id=user.id
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /casar propor ─────────────────────────────────────────────────────

    @casar_group.command(name="propor", description="Proponha casamento a outro membro")
    @app_commands.describe(membro="Membro para quem deseja propor casamento")
    async def propor(self, interaction: discord.Interaction, membro: discord.Member):
        db = self.bot.db
        guild = interaction.guild
        user = interaction.user

        if membro.id == user.id:
            await interaction.response.send_message(
                "❌ Você não pode se casar consigo mesmo.", ephemeral=True
            )
            return

        if membro.bot:
            await interaction.response.send_message(
                "❌ Você não pode se casar com um bot.", ephemeral=True
            )
            return

        # Check if proposer is already married
        proposer_marriage = await db.get_marriage(user.id, guild.id)
        if proposer_marriage:
            await interaction.response.send_message(
                "❌ Você já é casado! Divorce-se primeiro com `/casar divorciar`.",
                ephemeral=True,
            )
            return

        # Check if target is already married
        target_marriage = await db.get_marriage(membro.id, guild.id)
        if target_marriage:
            await interaction.response.send_message(
                f"❌ {membro.mention} já é casado(a).", ephemeral=True
            )
            return

        # Check if target already has a pending proposal
        if membro.id in self._proposals:
            await interaction.response.send_message(
                f"❌ {membro.mention} já tem um pedido de casamento pendente.", ephemeral=True
            )
            return

        # Register proposal
        self._proposals[membro.id] = {"proposer_id": user.id, "guild_id": guild.id}

        embed = _proposal_embed(user, membro)
        await interaction.response.send_message(embed=embed)

        # Auto-expire after 120 seconds
        asyncio.create_task(self._expire_proposal(membro.id, user.id, 120))

    async def _expire_proposal(self, proposee_id: int, proposer_id: int, delay: int):
        await asyncio.sleep(delay)
        proposal = self._proposals.get(proposee_id)
        if proposal and proposal.get("proposer_id") == proposer_id:
            self._proposals.pop(proposee_id, None)

    # ── /casar aceitar ────────────────────────────────────────────────────

    @casar_group.command(name="aceitar", description="Aceite um pedido de casamento pendente")
    async def aceitar(self, interaction: discord.Interaction):
        db = self.bot.db
        guild = interaction.guild
        user = interaction.user

        proposal = self._proposals.get(user.id)
        if not proposal:
            await interaction.response.send_message(
                "❌ Você não tem nenhum pedido de casamento pendente.", ephemeral=True
            )
            return

        proposer_id = proposal["proposer_id"]
        self._proposals.pop(user.id, None)

        # Double-check both are still unmarried
        existing_user = await db.get_marriage(user.id, guild.id)
        if existing_user:
            await interaction.response.send_message(
                "❌ Você já está casado(a).", ephemeral=True
            )
            return

        existing_proposer = await db.get_marriage(proposer_id, guild.id)
        if existing_proposer:
            await interaction.response.send_message(
                "❌ Quem te propôs casamento já está casado(a).", ephemeral=True
            )
            return

        await db.create_marriage(guild.id, proposer_id, user.id)

        proposer = guild.get_member(proposer_id)
        embed = _wedding_embed(proposer or interaction.user, user)
        await interaction.response.send_message(embed=embed)

    # ── /casar recusar ────────────────────────────────────────────────────

    @casar_group.command(name="recusar", description="Recuse um pedido de casamento pendente")
    async def recusar(self, interaction: discord.Interaction):
        user = interaction.user

        proposal = self._proposals.get(user.id)
        if not proposal:
            await interaction.response.send_message(
                "❌ Você não tem nenhum pedido de casamento pendente.", ephemeral=True
            )
            return

        proposer_id = proposal["proposer_id"]
        self._proposals.pop(user.id, None)

        proposer = interaction.guild.get_member(proposer_id)
        proposer_mention = proposer.mention if proposer else f"<@{proposer_id}>"

        embed = discord.Embed(
            title="💔 Pedido Recusado",
            description=(
                f"{user.mention} recusou o pedido de casamento de {proposer_mention}.\n\n"
                "*Às vezes o coração diz não...*"
            ),
            color=ERROR_COLOR,
        )
        await interaction.response.send_message(embed=embed)

    # ── /casar divorciar ──────────────────────────────────────────────────

    @casar_group.command(name="divorciar", description="Divorcie-se do seu cônjuge")
    async def divorciar(self, interaction: discord.Interaction):
        await self._start_divorce_flow(interaction)

    @app_commands.command(
        name="divorcio",
        description="Comando rápido para se divorciar",
    )
    async def divorcio_atalho(self, interaction: discord.Interaction):
        await self._start_divorce_flow(interaction)

    # ── /casar padrinho adicionar ─────────────────────────────────────────

    @casar_group.command(
        name="padrinho-adicionar",
        description="Adicione um padrinho ao seu casamento (máx. 2)",
    )
    @app_commands.describe(membro="Membro a ser adicionado como padrinho")
    async def padrinho_adicionar(
        self, interaction: discord.Interaction, membro: discord.Member
    ):
        db = self.bot.db
        guild = interaction.guild
        user = interaction.user

        marriage = await db.get_marriage(user.id, guild.id)
        if not marriage:
            await interaction.response.send_message(
                "❌ Você não está casado(a).", ephemeral=True
            )
            return

        # Must be one of the spouses
        if user.id not in (marriage["user1_id"], marriage["user2_id"]):
            await interaction.response.send_message(
                "❌ Apenas os cônjuges podem adicionar padrinhos.", ephemeral=True
            )
            return

        # Cannot add the other spouse
        other_id = (
            marriage["user2_id"] if marriage["user1_id"] == user.id else marriage["user1_id"]
        )
        if membro.id == other_id:
            await interaction.response.send_message(
                "❌ Você não pode adicionar seu cônjuge como padrinho.", ephemeral=True
            )
            return

        if membro.bot:
            await interaction.response.send_message(
                "❌ Bots não podem ser padrinhos.", ephemeral=True
            )
            return

        # Cannot add themselves
        if membro.id in (marriage["user1_id"], marriage["user2_id"]):
            await interaction.response.send_message(
                "❌ Os cônjuges não podem ser seus próprios padrinhos.", ephemeral=True
            )
            return

        # Determine which slot is free
        slot1_filled = bool(marriage.get("godparent1_id"))
        slot2_filled = bool(marriage.get("godparent2_id"))

        # Check if already a godparent
        if marriage.get("godparent1_id") == membro.id or marriage.get("godparent2_id") == membro.id:
            await interaction.response.send_message(
                f"❌ {membro.mention} já é padrinho deste casamento.", ephemeral=True
            )
            return

        if slot1_filled and slot2_filled:
            await interaction.response.send_message(
                "❌ Este casamento já tem 2 padrinhos (máximo atingido).", ephemeral=True
            )
            return

        slot = 1 if not slot1_filled else 2
        await db.set_godparent(marriage["id"], slot, membro.id)

        # Notify the new godparent
        user1 = guild.get_member(marriage["user1_id"])
        user2 = guild.get_member(marriage["user2_id"])
        u1_name = user1.mention if user1 else f"<@{marriage['user1_id']}>"
        u2_name = user2.mention if user2 else f"<@{marriage['user2_id']}>"

        notify_embed = discord.Embed(
            title="🌹 Você foi convidado a ser Padrinho!",
            description=(
                f"Parabéns, {membro.mention}! 🎉\n\n"
                f"Você foi adicionado como **padrinho** do casamento de "
                f"{u1_name} e {u2_name}!\n\n"
                "Como padrinho, você recebe um bônus de XP em mensagens. ✨"
            ),
            color=WEDDING_COLOR,
        )

        notified = False
        try:
            await membro.send(embed=notify_embed)
            notified = True
        except (discord.Forbidden, discord.HTTPException):
            pass

        success_embed = discord.Embed(
            title="🌹 Padrinho Adicionado",
            description=(
                f"{membro.mention} foi adicionado como padrinho do seu casamento!"
                + ("\n*(Notificação enviada por DM)*" if notified else "")
            ),
            color=SUCCESS_COLOR,
        )
        await interaction.response.send_message(embed=success_embed)

        # If couldn't DM, notify in channel
        if not notified:
            await interaction.followup.send(
                f"🌹 {membro.mention}, você foi adicionado como padrinho do casamento de "
                f"{u1_name} e {u2_name}! Você recebe +15% de XP por mensagem. ✨"
            )

    # ── /casar padrinho-remover ───────────────────────────────────────────

    @casar_group.command(
        name="padrinho-remover",
        description="Remova um padrinho do seu casamento",
    )
    @app_commands.describe(membro="Padrinho a ser removido")
    async def padrinho_remover(
        self, interaction: discord.Interaction, membro: discord.Member
    ):
        db = self.bot.db
        guild = interaction.guild
        user = interaction.user

        marriage = await db.get_marriage(user.id, guild.id)
        if not marriage:
            await interaction.response.send_message(
                "❌ Você não está casado(a).", ephemeral=True
            )
            return

        if user.id not in (marriage["user1_id"], marriage["user2_id"]):
            await interaction.response.send_message(
                "❌ Apenas os cônjuges podem remover padrinhos.", ephemeral=True
            )
            return

        if marriage.get("godparent1_id") == membro.id:
            slot = 1
        elif marriage.get("godparent2_id") == membro.id:
            slot = 2
        else:
            await interaction.response.send_message(
                f"❌ {membro.mention} não é padrinho deste casamento.", ephemeral=True
            )
            return

        await db.remove_godparent(marriage["id"], slot)

        embed = discord.Embed(
            title="🌹 Padrinho Removido",
            description=f"{membro.mention} foi removido como padrinho do seu casamento.",
            color=WARNING_COLOR,
        )
        await interaction.response.send_message(embed=embed)

    # ── /casar cofre-depositar ────────────────────────────────────────────

    @casar_group.command(
        name="cofre-depositar",
        description="Deposite moedas no cofre compartilhado do seu casamento",
    )
    @app_commands.describe(valor="Quantidade de moedas a depositar")
    async def cofre_depositar(self, interaction: discord.Interaction, valor: int):
        db = self.bot.db
        guild = interaction.guild
        user = interaction.user

        if valor <= 0:
            await interaction.response.send_message(
                "❌ O valor deve ser maior que zero.", ephemeral=True
            )
            return

        marriage = await db.get_marriage(user.id, guild.id)
        if not marriage:
            await interaction.response.send_message(
                "❌ Você não está casado(a).", ephemeral=True
            )
            return

        if user.id not in (marriage["user1_id"], marriage["user2_id"]):
            await interaction.response.send_message(
                "❌ Apenas os cônjuges podem usar o cofre.", ephemeral=True
            )
            return

        # Check user balance
        user_data = await db.get_user(user.id, guild.id)
        if user_data["balance"] < valor:
            await interaction.response.send_message(
                f"❌ Saldo insuficiente. Você tem **{user_data['balance']:,}** {COIN_EMOJI}, "
                f"mas tentou depositar **{valor:,}** {COIN_EMOJI}.",
                ephemeral=True,
            )
            return

        success = await db.marriage_deposit(marriage["id"], user.id, guild.id, valor)
        if not success:
            await interaction.response.send_message(
                "❌ Não foi possível realizar o depósito. Verifique seu saldo.", ephemeral=True
            )
            return

        # Fetch updated marriage
        updated = await db.get_marriage_by_id(marriage["id"])
        new_balance = updated["shared_balance"] if updated else marriage["shared_balance"] + valor

        embed = discord.Embed(
            title=f"{COIN_EMOJI} Depósito Realizado",
            description=(
                f"{user.mention} depositou **{valor:,}** {COIN_EMOJI} no cofre do casal!\n\n"
                f"💰 **Novo saldo do cofre:** {new_balance:,} {COIN_EMOJI}"
            ),
            color=SUCCESS_COLOR,
        )
        embed.set_footer(text="Use /casar cofre-saldo para ver o saldo a qualquer momento")
        await interaction.response.send_message(embed=embed)

    # ── /casar cofre-sacar ────────────────────────────────────────────────

    @casar_group.command(
        name="cofre-sacar",
        description="Saque moedas do cofre compartilhado do seu casamento",
    )
    @app_commands.describe(valor="Quantidade de moedas a sacar")
    async def cofre_sacar(self, interaction: discord.Interaction, valor: int):
        db = self.bot.db
        guild = interaction.guild
        user = interaction.user

        if valor <= 0:
            await interaction.response.send_message(
                "❌ O valor deve ser maior que zero.", ephemeral=True
            )
            return

        marriage = await db.get_marriage(user.id, guild.id)
        if not marriage:
            await interaction.response.send_message(
                "❌ Você não está casado(a).", ephemeral=True
            )
            return

        if user.id not in (marriage["user1_id"], marriage["user2_id"]):
            await interaction.response.send_message(
                "❌ Apenas os cônjuges podem usar o cofre.", ephemeral=True
            )
            return

        shared_balance = marriage.get("shared_balance", 0)
        if shared_balance < valor:
            await interaction.response.send_message(
                f"❌ Saldo insuficiente no cofre. O cofre tem **{shared_balance:,}** {COIN_EMOJI}, "
                f"mas você tentou sacar **{valor:,}** {COIN_EMOJI}.",
                ephemeral=True,
            )
            return

        success = await db.marriage_withdraw(marriage["id"], user.id, guild.id, valor)
        if not success:
            await interaction.response.send_message(
                "❌ Não foi possível realizar o saque. O cofre pode não ter saldo suficiente.",
                ephemeral=True,
            )
            return

        updated = await db.get_marriage_by_id(marriage["id"])
        new_balance = updated["shared_balance"] if updated else shared_balance - valor

        embed = discord.Embed(
            title=f"{COIN_EMOJI} Saque Realizado",
            description=(
                f"{user.mention} sacou **{valor:,}** {COIN_EMOJI} do cofre do casal!\n\n"
                f"💰 **Saldo restante no cofre:** {new_balance:,} {COIN_EMOJI}"
            ),
            color=SUCCESS_COLOR,
        )
        embed.set_footer(text="Use /casar cofre-saldo para ver o saldo a qualquer momento")
        await interaction.response.send_message(embed=embed)

    # ── /casar cofre-saldo ────────────────────────────────────────────────

    @casar_group.command(
        name="cofre-saldo",
        description="Veja o saldo do cofre compartilhado do seu casamento",
    )
    async def cofre_saldo(self, interaction: discord.Interaction):
        db = self.bot.db
        guild = interaction.guild
        user = interaction.user

        marriage = await db.get_marriage(user.id, guild.id)
        if not marriage:
            await interaction.response.send_message(
                "❌ Você não está casado(a).", ephemeral=True
            )
            return

        if user.id not in (marriage["user1_id"], marriage["user2_id"]):
            await interaction.response.send_message(
                "❌ Apenas os cônjuges podem ver o saldo do cofre.", ephemeral=True
            )
            return

        user1 = guild.get_member(marriage["user1_id"])
        user2 = guild.get_member(marriage["user2_id"])
        u1_name = user1.mention if user1 else f"<@{marriage['user1_id']}>"
        u2_name = user2.mention if user2 else f"<@{marriage['user2_id']}>"
        shared = marriage.get("shared_balance", 0)

        embed = discord.Embed(
            title=f"{COIN_EMOJI} Cofre do Casal",
            color=WEDDING_COLOR,
        )
        embed.add_field(name="💑 Casal", value=f"{u1_name} & {u2_name}", inline=False)
        embed.add_field(
            name=f"{COIN_EMOJI} Saldo Compartilhado",
            value=f"**{shared:,}** moedas",
            inline=True,
        )
        embed.set_footer(
            text="Use /casar cofre-depositar ou /casar cofre-sacar para movimentar o cofre"
        )
        await interaction.response.send_message(embed=embed)

    # ── /casar info ───────────────────────────────────────────────────────

    @casar_group.command(
        name="info",
        description="Veja as informações de casamento de um membro",
    )
    @app_commands.describe(membro="Membro cujo casamento você quer ver (padrão: você)")
    async def info(
        self, interaction: discord.Interaction, membro: discord.Member | None = None
    ):
        db = self.bot.db
        guild = interaction.guild
        target = membro or interaction.user

        marriage = await db.get_marriage(target.id, guild.id)
        if not marriage:
            name = target.display_name
            await interaction.response.send_message(
                f"❌ **{name}** não está casado(a) neste servidor.", ephemeral=True
            )
            return

        user1 = guild.get_member(marriage["user1_id"])
        user2 = guild.get_member(marriage["user2_id"])
        gp1 = guild.get_member(marriage["godparent1_id"]) if marriage.get("godparent1_id") else None
        gp2 = guild.get_member(marriage["godparent2_id"]) if marriage.get("godparent2_id") else None

        embed = _marriage_info_embed(marriage, user1, user2, gp1, gp2)
        await interaction.response.send_message(embed=embed)


# ─── Setup ────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot):
    await bot.add_cog(Marriage(bot))
