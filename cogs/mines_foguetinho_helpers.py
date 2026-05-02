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
    desc += f"Seguras encontradas: **{len(revealed)}** / **{MINES_TOTAL - MINES_BOMBS}** • Bombas ocultas: **{MINES_BOMBS}**"

    col = BOT_COLOR if not ended else (ERROR_COLOR if boom is not None else SUCCESS_COLOR)

    embed = discord.Embed(
        title="💣 Bombinha",
        description=desc,
        color=col,
    )
    embed.add_field(name="Aposta", value=f"{SWEET_COIN_EMOJI} **{bet:,}**", inline=True)
    embed.add_field(name="Multiplicador", value=f"**×{mult:.2f}**", inline=True)
    if not ended:
        embed.set_footer(
            text="Clique num número para abrir. Sacar paga aposta × multiplicador atual. 3 bombas no tabuleiro."
        )
    return embed


async def _noop_ix(interaction: discord.Interaction) -> None:
    await interaction.response.defer()


def mines_apply_safe_mult(game: dict) -> None:
    r_ok = len(game["revealed_safe"])
    bombs_ct = game["bomb_count"]
    safe_total = MINES_TOTAL - bombs_ct
    unrevealed = MINES_TOTAL - r_ok
    safe_left = max(1, safe_total - r_ok)
    game["mult"] *= unrevealed / safe_left


class BombinhaSacarBtn(discord.ui.Button):
    def __init__(self, *, disabled: bool):
        super().__init__(label="💰 Sacar", style=discord.ButtonStyle.success, row=4, disabled=disabled)

    async def callback(self, interaction: discord.Interaction):
        v = interaction.view
        if not isinstance(v, MinesBombinhaView):
            await interaction.response.defer()
            return
        await v.cash_out(interaction)


class BombinhaCellBtn(discord.ui.Button):
    def __init__(self, idx: int):
        row = idx // MINES_COLS
        label = str(idx + 1)
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=row)
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        v = interaction.view
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
        boom = g.get("boom_idx")
        rv = g["revealed_safe"]
        bombs = g["bombs"]
        ended = boom is not None or g.get("finished")

        if ended:
            for i in range(MINES_TOTAL):
                row = i // MINES_COLS
                if i in bombs:
                    lab = "💥" if i == boom else "💣"
                    btn = discord.ui.Button(
                        style=discord.ButtonStyle.danger,
                        label=lab,
                        row=row,
                        disabled=True,
                    )
                elif i in rv:
                    btn = discord.ui.Button(
                        style=discord.ButtonStyle.success, label="✓", row=row, disabled=True
                    )
                else:
                    btn = discord.ui.Button(
                        style=discord.ButtonStyle.secondary, label="·", row=row, disabled=True
                    )
                btn.callback = _noop_ix  # type: ignore[method-assign]
                self.add_item(btn)
            return

        for i in range(MINES_TOTAL):
            row = i // MINES_COLS
            if i in rv:
                btn = discord.ui.Button(
                    style=discord.ButtonStyle.success, label="✓", row=row, disabled=True
                )
                btn.callback = _noop_ix  # type: ignore[method-assign]
            else:
                btn = BombinhaCellBtn(i)
            self.add_item(btn)

        self.add_item(BombinhaSacarBtn(disabled=len(rv) < 1))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Esta Bombinha não é sua.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        popped = self.cog._mines_sessions.pop(self.user_id, None)
        if not popped:
            return

        cid = popped.get("channel_id")
        mid = popped.get("message_id")

        bot = self.cog.bot

        embed = discord.Embed(
            title="💣 Bombinha — Tempo esgotado",
            description=f"Você perdeu a aposta ({SWEET_COIN_EMOJI} **{popped['bet']:,}**).",
            color=ERROR_COLOR,
        )

        if cid and mid:
            ch = bot.get_channel(cid)
            if ch and hasattr(ch, "fetch_message"):
                try:
                    msg = await ch.fetch_message(mid)
                    await msg.edit(embed=embed, view=None)
                    return
                except discord.HTTPException:
                    pass

    async def on_pick(self, interaction: discord.Interaction, idx: int) -> None:
        g = self.game
        if g.get("boom_idx") or g.get("finished"):
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
            await interaction.response.edit_message(embed=embed, view=None)
            return

        g["revealed_safe"].add(idx)
        mines_apply_safe_mult(g)

        max_safe = MINES_TOTAL - g["bomb_count"]
        if len(g["revealed_safe"]) >= max_safe:
            payout = max(0, int(round(g["bet"] * round(g["mult"], 8))))
            if payout < g["bet"]:
                payout = g["bet"]

            await db.add_coins(self.user_id, self.guild_id, payout)
            g["finished"] = "clean"
            self.stop()
            self.cog._mines_sessions.pop(self.user_id, None)
            profit = payout - g["bet"]
            emb = mines_embed(g)
            emb.title = "💣 Bombinha — Tabuleiro limpo!"
            emb.description = (emb.description or "") + (
                f"\n\n🎉 **{SWEET_COIN_EMOJI} {payout:,}** ganhos ( lucro **+{profit:,}** )"
            )
            await interaction.response.edit_message(embed=emb, view=None)
            return

        self._rebuild_buttons()
        await interaction.response.edit_message(embed=mines_embed(g), view=self)

    async def cash_out(self, interaction: discord.Interaction) -> None:
        g = self.game
        if g.get("boom_idx") or g.get("finished"):
            await interaction.response.send_message("Rodada já encerrou.", ephemeral=True)
            return
        if len(g["revealed_safe"]) < 1:
            await interaction.response.send_message("Abra ao menos uma casa segura antes de sacar.", ephemeral=True)
            return

        db = self.cog.bot.db
        payout = max(1, int(round(g["bet"] * round(g["mult"], 8))))
        if payout < g["bet"]:
            payout = g["bet"]

        await db.add_coins(self.user_id, self.guild_id, payout)
        g["finished"] = "cashout"
        profit = payout - g["bet"]
        self.stop()
        self.cog._mines_sessions.pop(self.user_id, None)

        emb = mines_embed(g)
        emb.title = "💣 Bombinha — Sacou!"
        emb.description = (emb.description or "") + (
            f"\n\n💰 Você sacou **{SWEET_COIN_EMOJI} {payout:,}** ( lucro líquido **+{profit:,}** )."
        )
        emb.color = SUCCESS_COLOR
        await interaction.response.edit_message(embed=emb, view=None)
