"""Bombinha (mines) e utilitários de RNG para Foguetinho (crash). Usado pelo cog Economy."""

from __future__ import annotations

import random
from typing import Any

import discord

from config import BOT_COLOR, ERROR_COLOR, SUCCESS_COLOR

SWEET_COIN_EMOJI = "🍬"

MINES_ROWS = 4
MINES_COLS = 5
MINES_TOTAL = MINES_ROWS * MINES_COLS  # 20
MINES_BOMBS = 3


def sample_foguetinho_crash() -> float:
    """Ponto de crash (multiplicador). Mais massa próxima de 1.x, cauda longa."""
    lam = random.uniform(2.85, 4.9)
    raw = random.expovariate(lam) + 1.0
    return float(min(199.99, max(1.05, round(raw, 2))))


def mines_embed(game: dict) -> discord.Embed:
    bet = game["bet"]
    mult = game["mult"]
    revealed: set[int] = game["revealed_safe"]
    bombs: set[int] = game["bombs"]
    boom = game.get("boom_idx")
    ended = boom is not None or game.get("finished")

    rows_txt = []
    for r in range(MINES_ROWS):
        cells = []
        for c in range(MINES_COLS):
            idx = r * MINES_COLS + c
            if ended:
                if idx in bombs:
                    cells.append("💥" if idx == boom else "💣")
                elif idx in revealed:
                    cells.append("✅")
                else:
                    cells.append("▫️")
            else:
                cells.append("✅" if idx in revealed else "❔")
        rows_txt.append(" ".join(cells))

    desc = "```\n" + "\n".join(rows_txt) + "\n```\n"
    desc += (
        f"Seguras encontradas: **{len(revealed)}** / **{MINES_TOTAL - MINES_BOMBS}**"
        f" • Bombas ocultas: **{MINES_BOMBS}**"
    )

    col = BOT_COLOR if not ended else (ERROR_COLOR if boom is not None else SUCCESS_COLOR)

    embed = discord.Embed(title="💣 Bombinha", description=desc, color=col)
    embed.add_field(name="Aposta", value=f"{SWEET_COIN_EMOJI} **{bet:,}**", inline=True)
    embed.add_field(name="Multiplicador", value=f"**×{mult:.2f}**", inline=True)
    if not ended:
        n_revealed = len(revealed)
        if n_revealed > 0:
            potential = int(round(bet * mult))
            embed.add_field(
                name="Sacar agora",
                value=f"{SWEET_COIN_EMOJI} **{potential:,}** (lucro **+{potential - bet:,}**)",
                inline=True,
            )
        embed.set_footer(
            text="Clique num número para abrir. Sacar paga aposta × multiplicador. 3 bombas no tabuleiro."
        )
    return embed


def mines_apply_safe_mult(game: dict) -> None:
    r_ok = len(game["revealed_safe"])
    bombs_ct = game["bomb_count"]
    safe_total = MINES_TOTAL - bombs_ct
    unrevealed = MINES_TOTAL - r_ok
    safe_left = max(1, safe_total - r_ok)
    game["mult"] *= unrevealed / safe_left


class BombinhaSacarBtn(discord.ui.Button):
    def __init__(self, *, disabled: bool, user_id: int):
        super().__init__(
            label="💰 Sacar",
            style=discord.ButtonStyle.success,
            row=4,
            disabled=disabled,
            custom_id=f"ms_{user_id}",
        )

    async def callback(self, interaction: discord.Interaction):
        v: MinesBombinhaView | None = self.view  # type: ignore[assignment]
        if not isinstance(v, MinesBombinhaView):
            await interaction.response.defer()
            return
        await v.cash_out(interaction)


class BombinhaCellBtn(discord.ui.Button):
    def __init__(self, idx: int, user_id: int):
        row = idx // MINES_COLS
        super().__init__(
            label=str(idx + 1),
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id=f"mc_{user_id}_{idx}",
        )
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        v: MinesBombinhaView | None = self.view  # type: ignore[assignment]
        if not isinstance(v, MinesBombinhaView):
            await interaction.response.defer()
            return
        await v.on_pick(interaction, self.idx)


class MinesBombinhaView(discord.ui.View):
    timeout = 180.0

    def __init__(self, cog: Any, user_id: int, guild_id: int, game: dict):
        super().__init__(timeout=self.timeout)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.game = game
        self._rebuild_buttons()

    def _rebuild_buttons(self) -> None:
        self.clear_items()
        g = self.game
        rv = g["revealed_safe"]
        uid = self.user_id

        for i in range(MINES_TOTAL):
            row = i // MINES_COLS
            if i in rv:
                btn: discord.ui.Button = discord.ui.Button(
                    style=discord.ButtonStyle.success,
                    label="✓",
                    row=row,
                    disabled=True,
                    custom_id=f"mcs_{uid}_{i}",
                )
            else:
                btn = BombinhaCellBtn(i, uid)
            self.add_item(btn)

        self.add_item(BombinhaSacarBtn(disabled=len(rv) < 1, user_id=uid))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Esta Bombinha não é sua.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        popped = self.cog._mines_sessions.pop(self.user_id, None)
        if not popped:
            return

        embed = discord.Embed(
            title="💣 Bombinha — Tempo esgotado",
            description=f"Você demorou demais. Aposta perdida ({SWEET_COIN_EMOJI} **{popped['bet']:,}**).",
            color=ERROR_COLOR,
        )

        cid = popped.get("channel_id")
        mid = popped.get("message_id")
        if not (cid and mid):
            return

        bot = self.cog.bot
        try:
            ch = bot.get_channel(cid) or await bot.fetch_channel(cid)
            if ch and hasattr(ch, "fetch_message"):
                msg = await ch.fetch_message(mid)
                await msg.edit(embed=embed, view=None)
        except Exception:
            pass

    async def on_pick(self, interaction: discord.Interaction, idx: int) -> None:
        g = self.game
        if g.get("boom_idx") is not None or g.get("finished"):
            await interaction.response.defer()
            return
        if idx in g["revealed_safe"]:
            await interaction.response.defer()
            return

        db = self.cog.bot.db

        if idx in g["bombs"]:
            g["boom_idx"] = idx
            self.stop()
            self.cog._mines_sessions.pop(self.user_id, None)
            embed = mines_embed(g)
            embed.title = "💣 Bombinha — 💥 Explodiu!"
            embed.description = (embed.description or "") + (
                f"\n\n💥 Você pisou na bomba! **-{SWEET_COIN_EMOJI} {g['bet']:,}**"
            )
            try:
                await interaction.response.edit_message(embed=embed, view=None)
            except discord.HTTPException:
                if interaction.message:
                    try:
                        await interaction.message.edit(embed=embed, view=None)
                    except discord.HTTPException:
                        pass
            return

        g["revealed_safe"].add(idx)
        mines_apply_safe_mult(g)

        max_safe = MINES_TOTAL - g["bomb_count"]
        if len(g["revealed_safe"]) >= max_safe:
            payout = max(g["bet"], int(round(g["bet"] * g["mult"])))
            await db.add_coins(self.user_id, self.guild_id, payout)
            g["finished"] = "clean"
            self.stop()
            self.cog._mines_sessions.pop(self.user_id, None)
            profit = payout - g["bet"]
            emb = mines_embed(g)
            emb.title = "💣 Bombinha — Tabuleiro limpo! 🎉"
            emb.description = (emb.description or "") + (
                f"\n\n🎉 **{SWEET_COIN_EMOJI} {payout:,}** ganhos (lucro **+{profit:,}**)"
            )
            try:
                await interaction.response.edit_message(embed=emb, view=None)
            except discord.HTTPException:
                if interaction.message:
                    try:
                        await interaction.message.edit(embed=emb, view=None)
                    except discord.HTTPException:
                        pass
            return

        self._rebuild_buttons()
        try:
            await interaction.response.edit_message(embed=mines_embed(g), view=self)
        except discord.HTTPException:
            if interaction.message:
                try:
                    await interaction.message.edit(embed=mines_embed(g), view=self)
                except discord.HTTPException:
                    pass

    async def cash_out(self, interaction: discord.Interaction) -> None:
        g = self.game
        if g.get("boom_idx") is not None or g.get("finished"):
            await interaction.response.send_message(
                "Rodada já encerrou.", ephemeral=True
            )
            return
        if len(g["revealed_safe"]) < 1:
            await interaction.response.send_message(
                "Abra ao menos uma casa segura antes de sacar.", ephemeral=True
            )
            return

        db = self.cog.bot.db
        payout = max(g["bet"], int(round(g["bet"] * g["mult"])))
        await db.add_coins(self.user_id, self.guild_id, payout)
        g["finished"] = "cashout"
        profit = payout - g["bet"]
        self.stop()
        self.cog._mines_sessions.pop(self.user_id, None)

        emb = mines_embed(g)
        emb.title = "💣 Bombinha — Sacou!"
        emb.description = (emb.description or "") + (
            f"\n\n💰 Você sacou **{SWEET_COIN_EMOJI} {payout:,}** (lucro **+{profit:,}**)."
        )
        emb.color = SUCCESS_COLOR
        try:
            await interaction.response.edit_message(embed=emb, view=None)
        except discord.HTTPException:
            if interaction.message:
                try:
                    await interaction.message.edit(embed=emb, view=None)
                except discord.HTTPException:
                    pass
