import asyncio
import random
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import (
    BOT_COLOR,
    COIN_EMOJI,
    ERROR_COLOR,
    GOLD_COLOR,
    SUCCESS_COLOR,
    WARNING_COLOR,
)

from .mines_foguetinho_helpers import (
    MINES_BOMBS,
    MINES_TOTAL,
    MinesBombinhaView,
    mines_embed as bombinha_embed,
    sample_foguetinho_crash,
)

COIN_NAME = "Sweet Coins"
SWEET_COIN_EMOJI = "🍬"

_RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
_SUITS = ["♠", "♥", "♦", "♣"]

_RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}


# ── Blackjack helpers ─────────────────────────────────────────────────────────

def _build_deck() -> list[tuple[str, str]]:
    return [(r, s) for r in _RANKS for s in _SUITS]


def _card_value(rank: str) -> int:
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)


def hand_value(cards: list[tuple[str, str]]) -> int:
    total = sum(_card_value(r) for r, _ in cards)
    aces = sum(1 for r, _ in cards if r == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def card_str(card: tuple[str, str]) -> str:
    return f"{card[0]}{card[1]}"


def _hand_str(cards: list[tuple[str, str]]) -> str:
    return " ".join(card_str(c) for c in cards)


def _is_natural(cards: list[tuple[str, str]]) -> bool:
    return len(cards) == 2 and hand_value(cards) == 21


# ── Blackjack View ────────────────────────────────────────────────────────────

class BlackjackView(discord.ui.View):
    def __init__(self, cog: "Economy", user_id: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self._first_action = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Este não é o seu jogo.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        game = self.cog._games.pop(self.user_id, None)
        if game is None:
            return
        embed = discord.Embed(
            title="🃏 Blackjack — Tempo esgotado",
            description="Você demorou demais para jogar. A aposta foi perdida.",
            color=ERROR_COLOR,
        )
        msg = game.get("message")
        if msg is not None:
            try:
                await msg.edit(embed=embed, view=None)
            except discord.HTTPException:
                pass

    def _build_game_embed(self, game: dict, *, reveal: bool = False, color: int = BOT_COLOR) -> discord.Embed:
        dealer_cards = game["dealer"]
        player_cards = game["player"]

        if reveal:
            dealer_display = _hand_str(dealer_cards)
            dealer_total = f"({hand_value(dealer_cards)})"
        else:
            dealer_display = f"{card_str(dealer_cards[0])} 🂠"
            dealer_total = ""

        player_display = _hand_str(player_cards)
        player_total = hand_value(player_cards)

        embed = discord.Embed(title="🃏 Blackjack", color=color)
        embed.add_field(
            name="Dealer",
            value=f"{dealer_display} {dealer_total}".strip(),
            inline=False,
        )
        embed.add_field(
            name="Sua mão",
            value=f"{player_display} ({player_total})",
            inline=False,
        )
        embed.add_field(
            name="Aposta",
            value=f"{SWEET_COIN_EMOJI} {game['bet']:,}",
            inline=True,
        )
        return embed

    async def _end_game(
        self,
        interaction: discord.Interaction,
        game: dict,
        *,
        result: str,
        description: str,
        color: int,
    ):
        self.stop()
        self.cog._games.pop(self.user_id, None)

        payout = 0
        if result == "win":
            payout = game["bet"] * 2
            await self.cog.bot.db.add_coins(self.user_id, interaction.guild_id, payout)
        elif result == "blackjack":
            payout = game["bet"] + int(game["bet"] * 1.5)
            await self.cog.bot.db.add_coins(self.user_id, interaction.guild_id, payout)
        elif result == "push":
            payout = game["bet"]
            await self.cog.bot.db.add_coins(self.user_id, interaction.guild_id, payout)

        embed = self._build_game_embed(game, reveal=True, color=color)
        embed.title = f"🃏 Blackjack — {description}"
        if payout:
            net = payout - game["bet"]
            embed.add_field(
                name="Resultado",
                value=f"+{SWEET_COIN_EMOJI} {net:,}" if net > 0 else f"{SWEET_COIN_EMOJI} 0 (empate)",
                inline=True,
            )
        else:
            embed.add_field(
                name="Resultado",
                value=f"-{SWEET_COIN_EMOJI} {game['bet']:,}",
                inline=True,
            )

        # Prefer editing via the button interaction (edits the game message directly).
        # Fall back to the stored WebhookMessage if needed.
        try:
            await interaction.edit_original_response(embed=embed, view=None)
        except discord.HTTPException:
            msg = game.get("message")
            if msg is not None:
                try:
                    await msg.edit(embed=embed, view=None)
                except discord.HTTPException:
                    pass

    @discord.ui.button(label="🃏 Pedir", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self._first_action = False
        # Disable double-down if it exists
        for child in self.children:
            if hasattr(child, "label") and "Dobrar" in child.label:
                child.disabled = True

        game = self.cog._games.get(self.user_id)
        if game is None:
            return

        deck = game["deck"]
        game["player"].append(deck.pop())
        total = hand_value(game["player"])

        if total > 21:
            embed = self._build_game_embed(game, reveal=True, color=ERROR_COLOR)
            embed.title = "🃏 Blackjack — Passou de 21!"
            embed.add_field(
                name="Resultado",
                value=f"-{SWEET_COIN_EMOJI} {game['bet']:,}",
                inline=True,
            )
            self.stop()
            self.cog._games.pop(self.user_id, None)
            try:
                await interaction.edit_original_response(embed=embed, view=None)
            except discord.HTTPException:
                msg = game.get("message")
                if msg:
                    try:
                        await msg.edit(embed=embed, view=None)
                    except discord.HTTPException:
                        pass
        else:
            embed = self._build_game_embed(game, color=BOT_COLOR)
            try:
                await interaction.edit_original_response(embed=embed, view=self)
            except discord.HTTPException:
                msg = game.get("message")
                if msg:
                    try:
                        await msg.edit(embed=embed, view=self)
                    except discord.HTTPException:
                        pass

    @discord.ui.button(label="✋ Parar", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self._first_action = False
        game = self.cog._games.get(self.user_id)
        if game is None:
            return
        await self._dealer_play_and_resolve(interaction, game)

    @discord.ui.button(label="2× Dobrar", style=discord.ButtonStyle.danger)
    async def double_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        game = self.cog._games.get(self.user_id)
        if game is None:
            return

        if not self._first_action:
            try:
                await interaction.followup.send(
                    "Dobrar só é permitido na primeira jogada.", ephemeral=True
                )
            except discord.HTTPException:
                pass
            return

        self._first_action = False

        extra = game["bet"]
        deducted = await self.cog.bot.db.deduct_coins(
            self.user_id, interaction.guild_id, extra
        )
        if not deducted:
            try:
                await interaction.followup.send(
                    f"Você não tem {SWEET_COIN_EMOJI} suficientes para dobrar.", ephemeral=True
                )
            except discord.HTTPException:
                pass
            return

        game["bet"] += extra
        game["player"].append(game["deck"].pop())
        player_total = hand_value(game["player"])

        if player_total > 21:
            embed = self._build_game_embed(game, reveal=True, color=ERROR_COLOR)
            embed.title = "🃏 Blackjack — Passou de 21! (Dobro)"
            embed.add_field(
                name="Resultado",
                value=f"-{SWEET_COIN_EMOJI} {game['bet']:,}",
                inline=True,
            )
            self.stop()
            self.cog._games.pop(self.user_id, None)
            try:
                await interaction.edit_original_response(embed=embed, view=None)
            except discord.HTTPException:
                msg = game.get("message")
                if msg:
                    try:
                        await msg.edit(embed=embed, view=None)
                    except discord.HTTPException:
                        pass
            return

        await self._dealer_play_and_resolve(interaction, game)

    async def _dealer_play_and_resolve(
        self, interaction: discord.Interaction, game: dict
    ):
        deck = game["deck"]
        dealer = game["dealer"]
        while hand_value(dealer) < 17:
            dealer.append(deck.pop())

        player_total = hand_value(game["player"])
        dealer_total = hand_value(dealer)

        if dealer_total > 21 or player_total > dealer_total:
            await self._end_game(
                interaction, game,
                result="win",
                description="Você ganhou!",
                color=SUCCESS_COLOR,
            )
        elif player_total == dealer_total:
            await self._end_game(
                interaction, game,
                result="push",
                description="Empate",
                color=WARNING_COLOR,
            )
        else:
            await self._end_game(
                interaction, game,
                result="lose",
                description="Você perdeu",
                color=ERROR_COLOR,
            )


# ── Cog ───────────────────────────────────────────────────────────────────────

class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._games: dict[int, dict] = {}
        self._mines_sessions: dict[int, dict] = {}

    # ── /banco group ──────────────────────────────────────────────────────────

    banco_group = app_commands.Group(name="banco", description="Comandos de banco")

    @banco_group.command(name="saldo", description="Veja seu saldo de Sweet Coins")
    @app_commands.describe(membro="Membro para verificar o saldo (opcional)")
    async def saldo(
        self,
        interaction: discord.Interaction,
        membro: discord.Member | None = None,
    ):
        await interaction.response.defer()
        target = membro or interaction.user

        db = self.bot.db
        user_data = await db.get_user(target.id, interaction.guild_id)
        rank = await db.get_rank(target.id, interaction.guild_id, by="balance")

        embed = discord.Embed(
            title=f"{SWEET_COIN_EMOJI} Saldo de {target.display_name}",
            color=GOLD_COLOR,
        )
        embed.add_field(
            name="Sweet Coins",
            value=f"{SWEET_COIN_EMOJI} **{user_data['balance']:,}**",
            inline=True,
        )
        embed.add_field(
            name="Posição no ranking",
            value=f"#{rank}",
            inline=True,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.followup.send(embed=embed)

    @banco_group.command(name="transferir", description="Transfere Sweet Coins para outro membro")
    @app_commands.describe(
        membro="Membro que receberá as moedas",
        valor="Quantidade a transferir",
    )
    async def transferir(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        valor: int,
    ):
        await interaction.response.defer()
        sender = interaction.user

        if membro.id == sender.id:
            embed = discord.Embed(
                description="Você não pode transferir moedas para si mesmo.",
                color=ERROR_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if membro.bot:
            embed = discord.Embed(
                description="Você não pode transferir moedas para um bot.",
                color=ERROR_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if valor <= 0:
            embed = discord.Embed(
                description="O valor da transferência deve ser maior que zero.",
                color=ERROR_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        db = self.bot.db
        deducted = await db.deduct_coins(sender.id, interaction.guild_id, valor)
        if not deducted:
            sender_data = await db.get_user(sender.id, interaction.guild_id)
            embed = discord.Embed(
                description=(
                    f"Saldo insuficiente. Você tem {SWEET_COIN_EMOJI} **{sender_data['balance']:,}** "
                    f"e tentou transferir {SWEET_COIN_EMOJI} **{valor:,}**."
                ),
                color=ERROR_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        await db.add_coins(membro.id, interaction.guild_id, valor)

        embed = discord.Embed(
            title=f"{SWEET_COIN_EMOJI} Transferência realizada",
            color=SUCCESS_COLOR,
        )
        embed.add_field(name="De", value=sender.mention, inline=True)
        embed.add_field(name="Para", value=membro.mention, inline=True)
        embed.add_field(
            name="Valor",
            value=f"{SWEET_COIN_EMOJI} **{valor:,}**",
            inline=True,
        )
        await interaction.followup.send(embed=embed)

    @banco_group.command(name="ranking", description="Top 10 membros mais ricos do servidor")
    async def ranking(self, interaction: discord.Interaction):
        await interaction.response.defer()
        top = await self.bot.db.get_leaderboard(interaction.guild_id, by="balance")

        embed = discord.Embed(
            title=f"{SWEET_COIN_EMOJI} Ranking de Sweet Coins",
            color=GOLD_COLOR,
        )

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, row in enumerate(top):
            member = interaction.guild.get_member(row["user_id"])
            name = member.display_name if member else f"<@{row['user_id']}>"
            prefix = medals[i] if i < 3 else f"`{i + 1}.`"
            lines.append(
                f"{prefix} **{name}** — {SWEET_COIN_EMOJI} {row['balance']:,}"
            )

        embed.description = "\n".join(lines) if lines else "Nenhum dado ainda."
        await interaction.followup.send(embed=embed)

    # ── /coinsdiarias ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="coinsdiarias", description="Resgate suas Sweet Coins diárias"
    )
    async def coinsdiarias(self, interaction: discord.Interaction):
        await interaction.response.defer()
        db = self.bot.db
        user_id = interaction.user.id
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        last_claim = await db.get_daily_claim(user_id)

        if last_claim == today_str:
            now = datetime.now(timezone.utc)
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            next_midnight = midnight.replace(day=midnight.day + 1) if midnight.day < 28 else (
                midnight.replace(
                    day=1,
                    month=midnight.month + 1 if midnight.month < 12 else 1,
                    year=midnight.year if midnight.month < 12 else midnight.year + 1,
                )
            )
            diff = next_midnight - now
            hours, rem = divmod(int(diff.total_seconds()), 3600)
            minutes = rem // 60

            embed = discord.Embed(
                title=f"{SWEET_COIN_EMOJI} Coins Diárias",
                description=(
                    f"Você já resgatou suas moedas hoje!\n"
                    f"Próximo resgate disponível em **{hours}h {minutes}min**."
                ),
                color=WARNING_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        amount = random.randint(150, 450)
        await db.set_daily_claim(user_id)
        await db.add_coins(user_id, interaction.guild_id, amount)

        motivational = random.choice([
            "Continue assim e logo você será o mais rico do servidor! 💪",
            "Consistência é a chave para acumular riquezas! 🗝️",
            "Cada dia é uma nova oportunidade de crescer! 🌟",
            "Seu esforço está valendo a pena! Continue voltando todo dia! 🔥",
            "Você está construindo seu império um dia de cada vez! 👑",
        ])

        embed = discord.Embed(
            title=f"{SWEET_COIN_EMOJI} Coins Diárias Resgatadas!",
            description=(
                f"Você recebeu {SWEET_COIN_EMOJI} **{amount:,} Sweet Coins**!\n\n"
                f"_{motivational}_"
            ),
            color=SUCCESS_COLOR,
        )
        embed.set_footer(text="Volte amanhã para mais moedas!")
        await interaction.followup.send(embed=embed)

    # ── /pix ──────────────────────────────────────────────────────────────────

    @app_commands.command(name="pix", description="Saiba como comprar Sweet Coins via Pix")
    async def pix(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cfg = await self.bot.db.get_guild_config(interaction.guild_id)
        pix_key = cfg.get("pix_key")

        if not pix_key:
            embed = discord.Embed(
                description="Pix não configurado neste servidor.",
                color=ERROR_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        def fmt_brl(centavos: int | float | None) -> str:
            if centavos is None:
                return "—"
            reais = centavos / 100
            return f"R$ {reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        price_100 = cfg.get("pix_price_100")
        price_500 = cfg.get("pix_price_500")
        price_1000 = cfg.get("pix_price_1000")

        table_lines = [
            f"{SWEET_COIN_EMOJI} **100 Sweet Coins** → {fmt_brl(price_100)}",
            f"{SWEET_COIN_EMOJI} **500 Sweet Coins** → {fmt_brl(price_500)}",
            f"{SWEET_COIN_EMOJI} **1.000 Sweet Coins** → {fmt_brl(price_1000)}",
        ]

        embed = discord.Embed(
            title=f"{SWEET_COIN_EMOJI} Comprar Sweet Coins via Pix",
            color=BOT_COLOR,
        )
        embed.add_field(
            name="Tabela de preços",
            value="\n".join(table_lines),
            inline=False,
        )
        embed.add_field(
            name="Chave Pix",
            value=f"`{pix_key}`",
            inline=False,
        )
        embed.add_field(
            name="Como pagar",
            value=(
                "1. Abra o app do seu banco\n"
                "2. Acesse a área de **Pix**\n"
                "3. Escaneie o QR Code ou use a chave acima\n"
                "4. Realize o pagamento e envie o comprovante para um administrador"
            ),
            inline=False,
        )
        embed.set_footer(text="Após a confirmação do pagamento, as moedas serão adicionadas à sua conta.")
        await interaction.followup.send(embed=embed)

    # ── /apostar group ────────────────────────────────────────────────────────

    apostar_group = app_commands.Group(name="apostar", description="Jogos de aposta")

    @apostar_group.command(name="blackjack", description="Jogue Blackjack com Sweet Coins")
    @app_commands.describe(valor="Valor da aposta (mínimo 10, máximo 50.000)")
    async def blackjack(self, interaction: discord.Interaction, valor: int):
        await interaction.response.defer()
        user_id = interaction.user.id

        if user_id in self._games:
            embed = discord.Embed(
                description="Você já tem um jogo de Blackjack em andamento! Termine-o primeiro.",
                color=WARNING_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if user_id in self._mines_sessions:
            embed = discord.Embed(
                description="Você já tem uma **Bombinha** em andamento! Termine ou espere acabar primeiro.",
                color=WARNING_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if valor < 10:
            embed = discord.Embed(
                description="A aposta mínima é de {SWEET_COIN_EMOJI} **10 Sweet Coins**.".format(
                    SWEET_COIN_EMOJI=SWEET_COIN_EMOJI
                ),
                color=ERROR_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        if valor > 50000:
            embed = discord.Embed(
                description=f"A aposta máxima é de {SWEET_COIN_EMOJI} **50.000 Sweet Coins**.",
                color=ERROR_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        db = self.bot.db
        deducted = await db.deduct_coins(user_id, interaction.guild_id, valor)
        if not deducted:
            user_data = await db.get_user(user_id, interaction.guild_id)
            embed = discord.Embed(
                description=(
                    f"Saldo insuficiente. Você tem {SWEET_COIN_EMOJI} **{user_data['balance']:,}** "
                    f"e tentou apostar {SWEET_COIN_EMOJI} **{valor:,}**."
                ),
                color=ERROR_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        deck = _build_deck()
        random.shuffle(deck)

        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]

        game = {
            "deck": deck,
            "player": player_hand,
            "dealer": dealer_hand,
            "bet": valor,
            "interaction": interaction,
        }

        # Natural blackjack check
        player_natural = _is_natural(player_hand)
        dealer_natural = _is_natural(dealer_hand)

        if player_natural:
            if dealer_natural:
                # Push
                await db.add_coins(user_id, interaction.guild_id, valor)
                embed = discord.Embed(
                    title="🃏 Blackjack — Empate!",
                    description="Ambos têm Blackjack natural! Aposta devolvida.",
                    color=WARNING_COLOR,
                )
                embed.add_field(
                    name="Sua mão",
                    value=f"{_hand_str(player_hand)} (21)",
                    inline=True,
                )
                embed.add_field(
                    name="Dealer",
                    value=f"{_hand_str(dealer_hand)} (21)",
                    inline=True,
                )
                await interaction.followup.send(embed=embed)
            else:
                payout = valor + int(valor * 1.5)
                await db.add_coins(user_id, interaction.guild_id, payout)
                net = int(valor * 1.5)
                embed = discord.Embed(
                    title="🃏 Blackjack Natural! 🎉",
                    description=f"Parabéns! Você ganhou {SWEET_COIN_EMOJI} **{net:,}**!",
                    color=SUCCESS_COLOR,
                )
                embed.add_field(
                    name="Sua mão",
                    value=f"{_hand_str(player_hand)} (21)",
                    inline=True,
                )
                embed.add_field(
                    name="Dealer",
                    value=f"{_hand_str(dealer_hand)} ({hand_value(dealer_hand)})",
                    inline=True,
                )
                await interaction.followup.send(embed=embed)
            return

        view = BlackjackView(self, user_id)

        dealer_display = f"{card_str(dealer_hand[0])} 🂠"
        player_display = _hand_str(player_hand)
        player_total = hand_value(player_hand)

        embed = discord.Embed(title="🃏 Blackjack", color=BOT_COLOR)
        embed.add_field(name="Dealer", value=dealer_display, inline=False)
        embed.add_field(
            name="Sua mão",
            value=f"{player_display} ({player_total})",
            inline=False,
        )
        embed.add_field(
            name="Aposta",
            value=f"{SWEET_COIN_EMOJI} {valor:,}",
            inline=True,
        )

        msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        game["message"] = msg
        self._games[user_id] = game

    @apostar_group.command(
        name="bombinha",
        description="Estilo Mines: abra número sem bomba. 3 bombas em 20 casas.",
    )
    @app_commands.describe(valor="Valor da aposta (mínimo 10, máximo 50.000)")
    async def bombinha_cmd(self, interaction: discord.Interaction, valor: int):
        await interaction.response.defer()
        user_id = interaction.user.id

        if user_id in self._mines_sessions:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="Você já tem uma Bombinha rodando.",
                    color=WARNING_COLOR,
                ),
                ephemeral=True,
            )
            return
        if user_id in self._games:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="Termine o Blackjack primeiro.",
                    color=WARNING_COLOR,
                ),
                ephemeral=True,
            )
            return

        if valor < 10:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=f"A aposta mínima é de {SWEET_COIN_EMOJI} **10** Sweet Coins.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return
        if valor > 50_000:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        "A aposta máxima é de "
                        f"{SWEET_COIN_EMOJI} **50.000** Sweet Coins."
                    ),
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        db = self.bot.db
        if not await db.deduct_coins(user_id, interaction.guild_id, valor):
            ud = await db.get_user(user_id, interaction.guild_id)
            await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        f"Saldo insuficiente. Você tem {SWEET_COIN_EMOJI} **{ud['balance']:,}** "
                        f"e tentou {SWEET_COIN_EMOJI} **{valor:,}**."
                    ),
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        bombs_idx = set(random.sample(range(MINES_TOTAL), MINES_BOMBS))
        game: dict = {
            "bombs": bombs_idx,
            "revealed_safe": set(),
            "bet": valor,
            "mult": 1.0,
            "boom_idx": None,
            "bomb_count": MINES_BOMBS,
            "finished": None,
            "channel_id": interaction.channel_id,
            "message_id": None,
        }
        view = MinesBombinhaView(self, user_id, interaction.guild_id, game)
        embed = bombinha_embed(game)
        msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        game["message_id"] = msg.id
        self._mines_sessions[user_id] = game

    @apostar_group.command(
        name="foguetinho",
        description="Foguetinho (crash): defina onde quer sacar. Se crashar antes, perde.",
    )
    @app_commands.describe(
        valor="Valor da aposta (mínimo 10, máximo 50.000)",
        multiplicador_alvo=(
            "Alvo onde você “saca” antes do crash ex.: 1.50 até 10.00 (mínimo 1.05)"
        ),
    )
    async def foguetinho_cmd(
        self,
        interaction: discord.Interaction,
        valor: int,
        multiplicador_alvo: float,
    ):
        await interaction.response.defer()
        user_id = interaction.user.id

        if user_id in self._games:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="Termine o Blackjack antes de jogar **Foguetinho**.",
                    color=WARNING_COLOR,
                ),
                ephemeral=True,
            )
            return
        if user_id in self._mines_sessions:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="Termine ou encerre sua **Bombinha** antes.",
                    color=WARNING_COLOR,
                ),
                ephemeral=True,
            )
            return

        meta = round(float(multiplicador_alvo), 2)

        if valor < 10:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        "A aposta mínima é de "
                        f"{SWEET_COIN_EMOJI} **10** Sweet Coins."
                    ),
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return
        if valor > 50_000:
            await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        "A aposta máxima é de "
                        f"{SWEET_COIN_EMOJI} **50.000** Sweet Coins."
                    ),
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return
        if meta < 1.05 or meta > 10.0:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="O multiplicador alvo deve ficar entre **1.05** e **10.00**.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        db = self.bot.db
        if not await db.deduct_coins(user_id, interaction.guild_id, valor):
            ud = await db.get_user(user_id, interaction.guild_id)
            await interaction.followup.send(
                embed=discord.Embed(
                    description=(
                        f"Saldo insuficiente. Você tem {SWEET_COIN_EMOJI} **{ud['balance']:,}** "
                        f"e tentou {SWEET_COIN_EMOJI} **{valor:,}**."
                    ),
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return

        crash = sample_foguetinho_crash()

        # Determine where the action ends: either the player's target or the crash point
        meta_cents = round(meta * 100)
        crash_cents = round(crash * 100)
        won = meta_cents < crash_cents
        end_mult = meta if won else crash

        # --- launch message ---
        launch_emb = discord.Embed(
            title="🚀 Foguetinho — Decolando!",
            description=f"**Alvo:** ×{meta:.2f} | **Aposta:** {SWEET_COIN_EMOJI} {valor:,}",
            color=BOT_COLOR,
        )
        launch_emb.add_field(name="Multiplicador", value="×1.00 🚀", inline=False)
        msg = await interaction.followup.send(embed=launch_emb, wait=True)

        # --- animated climb ---
        for step in range(1, 4):
            frac = step / 3
            current = round(1.0 + (end_mult - 1.0) * frac, 2)
            filled = int(frac * 10)
            bar = "▓" * filled + "░" * (10 - filled)
            step_emb = discord.Embed(
                title="🚀 Foguetinho — Subindo!",
                description=f"**Alvo:** ×{meta:.2f} | **Aposta:** {SWEET_COIN_EMOJI} {valor:,}",
                color=BOT_COLOR,
            )
            step_emb.add_field(name=f"[{bar}]", value=f"×{current:.2f} 🚀", inline=False)
            await msg.edit(embed=step_emb)
            await asyncio.sleep(0.65)

        await asyncio.sleep(0.4)

        # --- final result ---
        if won:
            payout = int(round(valor * meta))
            if payout <= 0:
                payout = valor
            await db.add_coins(user_id, interaction.guild_id, payout)
            net = payout - valor
            emb = discord.Embed(
                title="🚀 Foguetinho — Sacou!",
                description=(
                    f"Sacou em ×**{meta:.2f}** antes do crash em ×**{crash:.2f}**!"
                ),
                color=SUCCESS_COLOR,
            )
            emb.add_field(
                name="Ganhou",
                value=f"+{SWEET_COIN_EMOJI} **{net:,}** (total: **{payout:,}**)",
                inline=True,
            )
        else:
            emb = discord.Embed(
                title="💥 Foguetinho — Crashou!",
                description=(
                    f"Crashou em ×**{crash:.2f}** antes do seu alvo ×**{meta:.2f}**!\n"
                    f"Você perdeu {SWEET_COIN_EMOJI} **{valor:,}**."
                ),
                color=ERROR_COLOR,
            )

        emb.add_field(name="Crash", value=f"×{crash:.2f}", inline=True)
        emb.add_field(name="Seu alvo", value=f"×{meta:.2f}", inline=True)
        emb.set_footer(text="Ganhar = alvo menor que o ponto de crash.")
        await msg.edit(embed=emb)

    @apostar_group.command(name="roleta", description="Jogue roleta europeia com Sweet Coins")
    @app_commands.describe(
        valor="Valor da aposta (mínimo 10)",
        aposta="Tipo de aposta: número (0-36), vermelho, preto, par, impar, 1-12, 13-24, 25-36",
    )
    async def roleta(
        self,
        interaction: discord.Interaction,
        valor: int,
        aposta: str,
    ):
        await interaction.response.defer()
        user_id = interaction.user.id

        if user_id in self._games:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="Termine o **Blackjack** antes da roleta.",
                    color=WARNING_COLOR,
                ),
                ephemeral=True,
            )
            return
        if user_id in self._mines_sessions:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="Termine sua **Bombinha** antes da roleta.",
                    color=WARNING_COLOR,
                ),
                ephemeral=True,
            )
            return

        if valor < 10:
            embed = discord.Embed(
                description=f"A aposta mínima é de {SWEET_COIN_EMOJI} **10 Sweet Coins**.",
                color=ERROR_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        aposta_lower = aposta.strip().lower()
        valid_choices = {
            "vermelho", "preto", "par", "impar",
            "1-12", "13-24", "25-36",
        }

        # Check if it's a number bet
        is_number_bet = False
        number_bet: int | None = None
        if aposta_lower.isdigit() or (aposta_lower.lstrip("-").isdigit()):
            n = int(aposta_lower)
            if 0 <= n <= 36:
                is_number_bet = True
                number_bet = n
            else:
                embed = discord.Embed(
                    description="Número inválido. Escolha entre 0 e 36.",
                    color=ERROR_COLOR,
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
        elif aposta_lower not in valid_choices:
            embed = discord.Embed(
                description=(
                    "Tipo de aposta inválido. Escolhas válidas:\n"
                    "**número** (0-36), `vermelho`, `preto`, `par`, `impar`, `1-12`, `13-24`, `25-36`"
                ),
                color=ERROR_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        db = self.bot.db
        deducted = await db.deduct_coins(user_id, interaction.guild_id, valor)
        if not deducted:
            user_data = await db.get_user(user_id, interaction.guild_id)
            embed = discord.Embed(
                description=(
                    f"Saldo insuficiente. Você tem {SWEET_COIN_EMOJI} **{user_data['balance']:,}** "
                    f"e tentou apostar {SWEET_COIN_EMOJI} **{valor:,}**."
                ),
                color=ERROR_COLOR,
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        spinning_embed = discord.Embed(
            title="🎰 Roleta Europeia",
            description="🎡 Girando a roleta...",
            color=BOT_COLOR,
        )
        msg = await interaction.followup.send(embed=spinning_embed, wait=True)

        await asyncio.sleep(2)

        result_number = random.randint(0, 36)

        if result_number == 0:
            result_color = "🟢"
            result_color_name = "zero"
        elif result_number in _RED_NUMBERS:
            result_color = "🔴"
            result_color_name = "vermelho"
        else:
            result_color = "⚫"
            result_color_name = "preto"

        # Determine win/payout
        won = False
        payout_multiplier = 0

        if is_number_bet:
            if result_number == number_bet:
                won = True
                payout_multiplier = 35
        elif aposta_lower == "vermelho":
            if result_color_name == "vermelho":
                won = True
                payout_multiplier = 1
        elif aposta_lower == "preto":
            if result_color_name == "preto":
                won = True
                payout_multiplier = 1
        elif aposta_lower == "par":
            if result_number != 0 and result_number % 2 == 0:
                won = True
                payout_multiplier = 1
        elif aposta_lower == "impar":
            if result_number != 0 and result_number % 2 != 0:
                won = True
                payout_multiplier = 1
        elif aposta_lower == "1-12":
            if 1 <= result_number <= 12:
                won = True
                payout_multiplier = 2
        elif aposta_lower == "13-24":
            if 13 <= result_number <= 24:
                won = True
                payout_multiplier = 2
        elif aposta_lower == "25-36":
            if 25 <= result_number <= 36:
                won = True
                payout_multiplier = 2

        if won:
            win_amount = valor + valor * payout_multiplier
            await db.add_coins(user_id, interaction.guild_id, win_amount)
            net = valor * payout_multiplier

            embed = discord.Embed(
                title="🎰 Roleta Europeia — Você ganhou! 🎉",
                description=f"O número sorteado foi **{result_color} {result_number}**",
                color=SUCCESS_COLOR,
            )
            embed.add_field(name="Sua aposta", value=aposta, inline=True)
            embed.add_field(
                name="Ganho",
                value=f"+{SWEET_COIN_EMOJI} {net:,}",
                inline=True,
            )
        else:
            embed = discord.Embed(
                title="🎰 Roleta Europeia — Você perdeu",
                description=f"O número sorteado foi **{result_color} {result_number}**",
                color=ERROR_COLOR,
            )
            embed.add_field(name="Sua aposta", value=aposta, inline=True)
            embed.add_field(
                name="Perda",
                value=f"-{SWEET_COIN_EMOJI} {valor:,}",
                inline=True,
            )

        try:
            await msg.edit(embed=embed)
        except discord.HTTPException:
            pass

    # ── /banco-admin group ────────────────────────────────────────────────────

    banco_admin = app_commands.Group(
        name="banco-admin",
        description="Administração da economia do servidor",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @banco_admin.command(name="resetar-todos", description="Zera o saldo de Sweet Coins de TODOS os membros do servidor")
    async def resetar_todos(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db
        await db.reset_all_coins(interaction.guild_id)
        embed = discord.Embed(
            title="⚠️ Saldo Resetado",
            description=f"O saldo de {SWEET_COIN_EMOJI} **Sweet Coins** de **todos** os membros deste servidor foi zerado.",
            color=WARNING_COLOR,
        )
        await interaction.followup.send(embed=embed)

    @banco_admin.command(name="dar-todos", description="Dá uma quantidade de Sweet Coins para TODOS os membros do servidor")
    @app_commands.describe(valor="Quantidade de coins a dar")
    async def dar_todos(self, interaction: discord.Interaction, valor: int):
        await interaction.response.defer(ephemeral=False)
        if valor <= 0:
            await interaction.followup.send("O valor deve ser maior que zero.", ephemeral=True)
            return

        db = self.bot.db
        await db.give_coins_to_all(interaction.guild_id, valor)
        embed = discord.Embed(
            title="🎁 Moedas Distribuídas!",
            description=f"Todos os membros do servidor receberam {SWEET_COIN_EMOJI} **{valor:,} Sweet Coins**!",
            color=SUCCESS_COLOR,
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="leaderboard_coins", description="Top 10 membros mais ricos do servidor (Alias de /banco ranking)")
    async def leaderboard_coins(self, interaction: discord.Interaction):
        await interaction.response.defer()
        top = await self.bot.db.get_leaderboard(interaction.guild_id, by="balance")

        embed = discord.Embed(
            title=f"{SWEET_COIN_EMOJI} Ranking de Sweet Coins",
            color=GOLD_COLOR,
        )

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, row in enumerate(top):
            member = interaction.guild.get_member(row["user_id"])
            name = member.display_name if member else f"<@{row['user_id']}>"
            prefix = medals[i] if i < 3 else f"`{i + 1}.`"
            lines.append(
                f"{prefix} **{name}** — {SWEET_COIN_EMOJI} {row['balance']:,}"
            )

        embed.description = "\n".join(lines) if lines else "Nenhum dado ainda."
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
