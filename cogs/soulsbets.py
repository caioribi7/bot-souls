"""SoulsBets — apostas em partidas do Brasileirão e Champions League.

Requer chave da API football-data.org (gratuita em football-data.org/client/register).
Configure com /soulsbets config canal <#canal> e /soulsbets config api <chave>.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import BOT_COLOR, ERROR_COLOR, GOLD_COLOR, SUCCESS_COLOR, WARNING_COLOR

SWEET_COIN_EMOJI = "🍬"
FOOTBALL_API_BASE = "https://api.football-data.org/v4"

# Competições suportadas
COMPETITIONS = {
    "BSA": "🏟️ Brasileirão — Série A",
    "CL":  "🏆 UEFA Champions League",
}

# Odds fixas
ODDS = {"HOME": 2.0, "DRAW": 3.0, "AWAY": 2.0}
ODDS_LABEL = {"HOME": "🏠 Casa", "DRAW": "🤝 Empate", "AWAY": "✈️ Fora"}


# ── Modal de aposta ───────────────────────────────────────────────────────────

class BetModal(discord.ui.Modal):
    amount_input: discord.ui.TextInput = discord.ui.TextInput(
        label="Quantidade de Sweet Coins",
        placeholder="Ex: 200 (mín 10 – máx 50.000)",
        min_length=1,
        max_length=10,
    )

    def __init__(self, match_db_id: int, prediction: str, label: str):
        super().__init__(title=f"Apostar: {label}")
        self.match_db_id = match_db_id
        self.prediction = prediction

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.amount_input.value.strip().replace(".", "").replace(",", "")
        if not raw.isdigit():
            await interaction.response.send_message(
                "Valor inválido. Use apenas números.", ephemeral=True
            )
            return

        amount = int(raw)
        if amount < 10:
            await interaction.response.send_message(
                f"Mínimo: {SWEET_COIN_EMOJI} **10**.", ephemeral=True
            )
            return
        if amount > 50_000:
            await interaction.response.send_message(
                f"Máximo: {SWEET_COIN_EMOJI} **50.000**.", ephemeral=True
            )
            return

        db = interaction.client.db  # type: ignore[attr-defined]

        match = await db.get_fb_match(self.match_db_id)
        if not match or match["resolved"] or match["status"] not in ("SCHEDULED", "TIMED"):
            await interaction.response.send_message(
                "Esta partida não está mais aberta para apostas.", ephemeral=True
            )
            return

        existing = await db.get_fb_bet(self.match_db_id, interaction.user.id, interaction.guild_id)
        if existing:
            await interaction.response.send_message(
                "Você já apostou nesta partida.", ephemeral=True
            )
            return

        deducted = await db.deduct_coins(interaction.user.id, interaction.guild_id, amount)
        if not deducted:
            ud = await db.get_user(interaction.user.id, interaction.guild_id)
            await interaction.response.send_message(
                f"Saldo insuficiente. Você tem {SWEET_COIN_EMOJI} **{ud['balance']:,}**.",
                ephemeral=True,
            )
            return

        await db.create_fb_bet(
            guild_id=interaction.guild_id,
            match_id=self.match_db_id,
            user_id=interaction.user.id,
            prediction=self.prediction,
            amount=amount,
        )

        odds = ODDS[self.prediction]
        potential = int(round(amount * odds))
        net = potential - amount

        embed = discord.Embed(
            title="✅ Aposta registrada!",
            color=SUCCESS_COLOR,
        )
        embed.add_field(name="Previsão", value=ODDS_LABEL[self.prediction], inline=True)
        embed.add_field(name="Apostado", value=f"{SWEET_COIN_EMOJI} {amount:,}", inline=True)
        embed.add_field(
            name="Retorno potencial",
            value=f"{SWEET_COIN_EMOJI} {potential:,} (lucro **+{net:,}**)",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ── View dos botões de aposta ─────────────────────────────────────────────────

class MatchBetView(discord.ui.View):
    """View persistente com 3 botões: Casa | Empate | Fora."""

    def __init__(self, match_db_id: int, home_team: str, away_team: str, *, closed: bool = False):
        super().__init__(timeout=None)
        self.match_db_id = match_db_id

        ht = home_team[:22]
        at = away_team[:22]

        self.add_item(self._make_btn(
            f"sb_home_{match_db_id}",
            f"🏠 {ht} (×{ODDS['HOME']:.1f})",
            discord.ButtonStyle.primary,
            "HOME",
            closed,
        ))
        self.add_item(self._make_btn(
            f"sb_draw_{match_db_id}",
            f"🤝 Empate (×{ODDS['DRAW']:.1f})",
            discord.ButtonStyle.secondary,
            "DRAW",
            closed,
        ))
        self.add_item(self._make_btn(
            f"sb_away_{match_db_id}",
            f"✈️ {at} (×{ODDS['AWAY']:.1f})",
            discord.ButtonStyle.danger,
            "AWAY",
            closed,
        ))

    def _make_btn(
        self,
        custom_id: str,
        label: str,
        style: discord.ButtonStyle,
        prediction: str,
        disabled: bool,
    ) -> discord.ui.Button:
        btn: discord.ui.Button = discord.ui.Button(
            label=label,
            style=style,
            custom_id=custom_id,
            disabled=disabled,
        )
        match_id = self.match_db_id

        async def _cb(interaction: discord.Interaction, pred: str = prediction) -> None:
            await interaction.response.send_modal(
                BetModal(match_id, pred, ODDS_LABEL[pred])
            )

        btn.callback = _cb  # type: ignore[method-assign]
        return btn


# ── Helpers de embed ──────────────────────────────────────────────────────────

def _match_embed(
    match: dict,
    bets: list[dict] | None = None,
    *,
    result: str | None = None,
) -> discord.Embed:
    comp_label = COMPETITIONS.get(match["competition"], match["competition"])

    try:
        dt = datetime.fromisoformat(match["match_date"].replace("Z", "+00:00"))
        date_str = dt.strftime("%d/%m/%Y às %H:%Mh UTC")
    except Exception:
        date_str = match["match_date"]

    home = match["home_team"]
    away = match["away_team"]
    status = match.get("status", "SCHEDULED")

    if result:
        title = f"{comp_label}"
        if result == "HOME_TEAM":
            desc = f"**{home}** {match.get('home_score',0)} × {match.get('away_score',0)} {away}\n🏆 Vencedor: **{home}**"
            color = SUCCESS_COLOR
        elif result == "AWAY_TEAM":
            desc = f"{home} {match.get('home_score',0)} × {match.get('away_score',0)} **{away}**\n🏆 Vencedor: **{away}**"
            color = SUCCESS_COLOR
        else:
            desc = f"{home} {match.get('home_score',0)} × {match.get('away_score',0)} {away}\n🤝 Empate"
            color = WARNING_COLOR
    else:
        title = comp_label
        desc = f"**{home}** vs **{away}**\n📅 {date_str}"
        color = BOT_COLOR if status in ("SCHEDULED", "TIMED") else ERROR_COLOR

    embed = discord.Embed(title=title, description=desc, color=color)

    if bets:
        counts = {"HOME": 0, "DRAW": 0, "AWAY": 0}
        totals = {"HOME": 0, "DRAW": 0, "AWAY": 0}
        for b in bets:
            p = b["prediction"]
            if p in counts:
                counts[p] += 1
                totals[p] += b["amount"]

        lines = []
        for pred in ("HOME", "DRAW", "AWAY"):
            lab = ODDS_LABEL[pred]
            c = counts[pred]
            t = totals[pred]
            lines.append(f"{lab}: **{c}** aposta(s) | {SWEET_COIN_EMOJI} {t:,} apostados")
        embed.add_field(name="📊 Apostas", value="\n".join(lines), inline=False)

    if result:
        embed.set_footer(text="Partida encerrada — apostas resolvidas")
    elif status in ("SCHEDULED", "TIMED"):
        embed.set_footer(text="Apostas abertas • Odds fixas: Casa×2 | Empate×3 | Fora×2")
    else:
        embed.set_footer(text="Apostas encerradas — aguardando resultado")

    return embed


# ── Cog ───────────────────────────────────────────────────────────────────────

class SoulsBets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None

    async def cog_load(self) -> None:
        self._session = aiohttp.ClientSession()
        await self._register_active_views()
        self.task_post_matches.start()
        self.task_resolve_bets.start()

    async def cog_unload(self) -> None:
        self.task_post_matches.cancel()
        self.task_resolve_bets.cancel()
        if self._session:
            await self._session.close()

    async def _register_active_views(self) -> None:
        """Recria views persistentes para partidas não resolvidas após restart."""
        try:
            matches = await self.bot.db.get_all_unresolved_fb_matches()
            for m in matches:
                closed = m["status"] not in ("SCHEDULED", "TIMED")
                view = MatchBetView(m["id"], m["home_team"], m["away_team"], closed=closed)
                self.bot.add_view(view, message_id=m["message_id"] or None)
        except Exception:
            pass

    # ── Background tasks ──────────────────────────────────────────────────────

    @tasks.loop(hours=3)
    async def task_post_matches(self) -> None:
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            try:
                cfg = await self.bot.db.get_soulsbets_config(guild.id)
                if not cfg["enabled"] or not cfg["channel_id"] or not cfg["api_key"]:
                    continue
                ch = self.bot.get_channel(cfg["channel_id"])
                if not ch or not hasattr(ch, "send"):
                    continue
                await self._post_upcoming_matches(guild.id, ch, cfg["api_key"])
            except Exception:
                pass

    @tasks.loop(minutes=30)
    async def task_resolve_bets(self) -> None:
        await self.bot.wait_until_ready()
        try:
            await self._check_and_resolve()
        except Exception:
            pass

    @task_post_matches.before_loop
    async def _before_post(self) -> None:
        await asyncio.sleep(30)

    @task_resolve_bets.before_loop
    async def _before_resolve(self) -> None:
        await asyncio.sleep(60)

    # ── API helpers ───────────────────────────────────────────────────────────

    async def _fetch_upcoming(self, api_key: str, competition: str) -> tuple[list[dict], str | None]:
        """Retorna (partidas, erro_str). erro_str é None se OK."""
        if not self._session:
            return [], "sessão HTTP não iniciada"

        date_from = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        date_to = (datetime.now(timezone.utc) + timedelta(days=14)).strftime("%Y-%m-%d")
        url = f"{FOOTBALL_API_BASE}/competitions/{competition}/matches"
        params = {"dateFrom": date_from, "dateTo": date_to}

        try:
            async with self._session.get(
                url,
                headers={"X-Auth-Token": api_key},
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 403:
                    return [], f"API retornou 403 — chave inválida ou competição **{competition}** não inclusa no plano"
                if resp.status == 404:
                    return [], f"Competição **{competition}** não encontrada na API"
                if resp.status != 200:
                    return [], f"API retornou HTTP {resp.status} para {competition}"
                data = await resp.json()
                matches = [
                    m for m in data.get("matches", [])
                    if m.get("status") in ("SCHEDULED", "TIMED")
                ]
                return matches, None
        except asyncio.TimeoutError:
            return [], f"Timeout ao conectar na API ({competition})"
        except Exception as exc:
            return [], f"Erro inesperado ({competition}): {exc}"

    async def _fetch_finished(self, api_key: str, competition: str) -> list[dict]:
        if not self._session:
            return []
        date_from = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
        date_to = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        url = f"{FOOTBALL_API_BASE}/competitions/{competition}/matches"
        params = {"status": "FINISHED", "dateFrom": date_from, "dateTo": date_to}
        try:
            async with self._session.get(
                url,
                headers={"X-Auth-Token": api_key},
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return data.get("matches", [])
        except Exception:
            return []

    async def _post_upcoming_matches(
        self,
        guild_id: int,
        channel: discord.abc.Messageable,
        api_key: str,
    ) -> dict:
        """Retorna resumo: {posted: int, skipped: int, errors: list[str]}"""
        db = self.bot.db
        posted = 0
        skipped = 0
        errors: list[str] = []

        for comp_code in ("BSA", "CL"):
            matches, err = await self._fetch_upcoming(api_key, comp_code)
            if err:
                errors.append(err)
                continue

            if not matches:
                errors.append(f"Nenhuma partida encontrada nos próximos 14 dias para **{comp_code}**")
                continue

            for m in matches[:5]:
                ext_id = m.get("id")
                if not ext_id:
                    continue
                if await db.fb_match_exists(guild_id, ext_id):
                    skipped += 1
                    continue

                home = m["homeTeam"]["name"]
                away = m["awayTeam"]["name"]
                utc_date = m.get("utcDate", "")
                match_status = m.get("status", "SCHEDULED")

                match_db_id = await db.create_fb_match(
                    guild_id=guild_id,
                    external_id=ext_id,
                    competition=comp_code,
                    home_team=home,
                    away_team=away,
                    match_date=utc_date,
                )
                await db.update_fb_match(match_db_id, status=match_status)

                embed = _match_embed({
                    "competition": comp_code,
                    "home_team": home,
                    "away_team": away,
                    "match_date": utc_date,
                    "status": match_status,
                })
                view = MatchBetView(match_db_id, home, away)
                try:
                    msg = await channel.send(embed=embed, view=view)  # type: ignore[union-attr]
                    await db.update_fb_match(match_db_id, message_id=msg.id)
                    self.bot.add_view(view, message_id=msg.id)
                    posted += 1
                except discord.HTTPException as exc:
                    errors.append(f"Erro ao postar partida: {exc}")

                await asyncio.sleep(1)

        return {"posted": posted, "skipped": skipped, "errors": errors}

    async def _check_and_resolve(self) -> None:
        db = self.bot.db
        all_matches = await db.get_all_unresolved_fb_matches()
        if not all_matches:
            return

        # Agrupa por guild para evitar múltiplas buscas de config
        by_guild: dict[int, list[dict]] = {}
        for m in all_matches:
            by_guild.setdefault(m["guild_id"], []).append(m)

        for guild_id, guild_matches in by_guild.items():
            try:
                cfg = await db.get_soulsbets_config(guild_id)
                if not cfg["api_key"]:
                    continue
                api_key = cfg["api_key"]

                for comp_code in ("BSA", "CL"):
                    comp_matches = [m for m in guild_matches if m["competition"] == comp_code]
                    if not comp_matches:
                        continue

                    finished = await self._fetch_finished(api_key, comp_code)
                    finished_by_ext: dict[int, dict] = {f["id"]: f for f in finished}

                    for match in comp_matches:
                        api_data = finished_by_ext.get(match["external_id"])
                        if not api_data:
                            continue

                        score = api_data.get("score", {})
                        winner = score.get("winner")
                        full_time = score.get("fullTime", {})
                        home_score = full_time.get("home")
                        away_score = full_time.get("away")

                        if winner is None:
                            continue

                        await db.update_fb_match(
                            match["id"],
                            status="FINISHED",
                            winner=winner,
                            home_score=home_score,
                            away_score=away_score,
                            resolved=1,
                        )

                        bets = await db.get_fb_bets_for_match(match["id"])
                        if winner == "HOME_TEAM":
                            winning_pred = "HOME"
                        elif winner == "AWAY_TEAM":
                            winning_pred = "AWAY"
                        else:
                            winning_pred = "DRAW"

                        for bet in bets:
                            if bet["resolved"]:
                                continue
                            won = bet["prediction"] == winning_pred
                            payout = int(round(bet["amount"] * ODDS[bet["prediction"]])) if won else 0
                            await db.resolve_fb_bet(bet["id"], won, payout)
                            if won and payout > 0:
                                await db.add_coins(bet["user_id"], guild_id, payout)

                        await self._update_match_message(guild_id, match, bets, winner, home_score, away_score)
            except Exception:
                pass

    async def _update_match_message(
        self,
        guild_id: int,
        match: dict,
        bets: list[dict],
        winner: str,
        home_score: int | None,
        away_score: int | None,
    ) -> None:
        if not match.get("message_id"):
            return
        cfg = await self.bot.db.get_soulsbets_config(guild_id)
        ch = self.bot.get_channel(cfg["channel_id"])
        if not ch or not hasattr(ch, "fetch_message"):
            return

        updated_match = {**match, "home_score": home_score, "away_score": away_score}
        embed = _match_embed(updated_match, bets, result=winner)

        try:
            msg = await ch.fetch_message(match["message_id"])  # type: ignore[union-attr]
            await msg.edit(embed=embed, view=None)
        except discord.HTTPException:
            pass

    # ── Slash commands ────────────────────────────────────────────────────────

    soulsbets_group = app_commands.Group(
        name="soulsbets",
        description="Apostas em futebol — Brasileirão e Champions League",
    )

    # ── Admin commands ────────────────────────────────────────────────────────

    @soulsbets_group.command(name="canal", description="[Admin] Define o canal onde as partidas são publicadas")
    @app_commands.describe(canal="Canal de texto para publicar os jogos")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.set_soulsbets_config(interaction.guild_id, channel_id=canal.id)
        await interaction.followup.send(
            embed=discord.Embed(
                description=f"✅ Canal configurado: {canal.mention}",
                color=SUCCESS_COLOR,
            )
        )

    @soulsbets_group.command(name="api", description="[Admin] Define a chave da API football-data.org")
    @app_commands.describe(chave="Chave da API (registre em football-data.org)")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_api(self, interaction: discord.Interaction, chave: str):
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.set_soulsbets_config(interaction.guild_id, api_key=chave)
        await interaction.followup.send(
            embed=discord.Embed(
                description="✅ Chave da API configurada com sucesso.",
                color=SUCCESS_COLOR,
            )
        )

    @soulsbets_group.command(name="info", description="[Admin] Mostra a configuração atual do SoulsBets")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await self.bot.db.get_soulsbets_config(interaction.guild_id)

        canal_mention = (
            f"<#{cfg['channel_id']}>" if cfg["channel_id"] else "❌ Não configurado"
        )
        api_status = "✅ Configurada" if cfg["api_key"] else "❌ Não configurada"

        embed = discord.Embed(title="⚙️ SoulsBets — Configuração", color=BOT_COLOR)
        embed.add_field(name="Canal", value=canal_mention, inline=True)
        embed.add_field(name="API Key", value=api_status, inline=True)
        embed.add_field(name="Ativo", value="✅ Sim" if cfg["enabled"] else "❌ Não", inline=True)
        embed.add_field(
            name="Como obter API key",
            value="Registre-se em football-data.org — plano gratuito inclui Brasileirão e Champions League.",
            inline=False,
        )
        await interaction.followup.send(embed=embed)

    @soulsbets_group.command(name="publicar", description="[Admin] Publica manualmente as próximas partidas")
    @app_commands.checks.has_permissions(administrator=True)
    async def publicar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cfg = await self.bot.db.get_soulsbets_config(interaction.guild_id)

        if not cfg["channel_id"]:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="Configure o canal primeiro: `/soulsbets canal`.",
                    color=ERROR_COLOR,
                )
            )
            return
        if not cfg["api_key"]:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="Configure a API key primeiro: `/soulsbets api`.",
                    color=ERROR_COLOR,
                )
            )
            return

        ch = self.bot.get_channel(cfg["channel_id"])
        if not ch or not hasattr(ch, "send"):
            await interaction.followup.send(
                embed=discord.Embed(
                    description="Canal não encontrado ou inválido.", color=ERROR_COLOR
                )
            )
            return

        await interaction.followup.send(
            embed=discord.Embed(description="🔍 Buscando partidas nos próximos 14 dias...", color=BOT_COLOR)
        )

        result = await self._post_upcoming_matches(interaction.guild_id, ch, cfg["api_key"])

        posted = result["posted"]
        skipped = result["skipped"]
        errors = result["errors"]

        if posted > 0:
            color = SUCCESS_COLOR
            desc = f"✅ **{posted}** partida(s) publicadas em {ch.mention}."  # type: ignore[union-attr]
        elif skipped > 0 and not errors:
            color = WARNING_COLOR
            desc = f"⚠️ Nenhuma partida nova — **{skipped}** já estavam publicadas."
        else:
            color = ERROR_COLOR
            desc = "❌ Nenhuma partida foi publicada."

        if skipped > 0 and posted > 0:
            desc += f"\n⏭️ {skipped} já publicada(s) anteriormente (ignoradas)."

        embed = discord.Embed(description=desc, color=color)
        if errors:
            embed.add_field(
                name="⚠️ Avisos / Erros",
                value="\n".join(f"• {e}" for e in errors),
                inline=False,
            )
        await interaction.edit_original_response(embed=embed)

    # ── Public commands ───────────────────────────────────────────────────────

    @soulsbets_group.command(name="minhasapostas", description="Veja suas últimas apostas")
    async def minhasapostas(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        bets = await self.bot.db.get_user_fb_bets(interaction.user.id, interaction.guild_id)

        if not bets:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="Você ainda não fez nenhuma aposta.", color=WARNING_COLOR
                )
            )
            return

        embed = discord.Embed(title="⚽ Suas Apostas", color=GOLD_COLOR)
        lines = []
        for b in bets:
            status_icon = "⏳" if not b["resolved"] else ("✅" if b["won"] else "❌")
            pred_label = ODDS_LABEL.get(b["prediction"], b["prediction"])
            result_str = (
                f"| +{SWEET_COIN_EMOJI}{b['payout']:,}" if b["won"] and b["resolved"]
                else (f"| -{SWEET_COIN_EMOJI}{b['amount']:,}" if b["resolved"] else "| pendente")
            )
            lines.append(
                f"{status_icon} **{b['home_team']} vs {b['away_team']}** "
                f"({b['competition']}) — {pred_label} "
                f"{SWEET_COIN_EMOJI}{b['amount']:,} {result_str}"
            )

        embed.description = "\n".join(lines[:10])
        await interaction.followup.send(embed=embed)

    @soulsbets_group.command(name="partidas", description="Lista partidas abertas para apostas")
    async def partidas(self, interaction: discord.Interaction):
        await interaction.response.defer()
        active = await self.bot.db.get_active_fb_matches(interaction.guild_id)

        if not active:
            await interaction.followup.send(
                embed=discord.Embed(
                    description="Nenhuma partida disponível no momento.",
                    color=WARNING_COLOR,
                )
            )
            return

        embed = discord.Embed(title="⚽ Partidas Disponíveis para Apostas", color=BOT_COLOR)
        for m in active[:10]:
            comp = COMPETITIONS.get(m["competition"], m["competition"])
            try:
                dt = datetime.fromisoformat(m["match_date"].replace("Z", "+00:00"))
                date_str = dt.strftime("%d/%m %H:%Mh")
            except Exception:
                date_str = m["match_date"]
            status = "🟢 Aberta" if m["status"] in ("SCHEDULED", "TIMED") else "🔴 Fechada"
            embed.add_field(
                name=comp,
                value=f"**{m['home_team']}** vs **{m['away_team']}**\n📅 {date_str} • {status}",
                inline=False,
            )

        cfg = await self.bot.db.get_soulsbets_config(interaction.guild_id)
        if cfg["channel_id"]:
            embed.set_footer(text=f"Aposte no canal <#{cfg['channel_id']}>")
        await interaction.followup.send(embed=embed)

    # ── Error handler ─────────────────────────────────────────────────────────

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="❌ Você precisa de permissão de **administrador** para usar este comando.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(SoulsBets(bot))
