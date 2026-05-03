import random
import asyncio
from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import commands, tasks
from config import GOLD_COLOR, ERROR_COLOR, SUCCESS_COLOR, BOT_COLOR


def parse_duration(s: str) -> int | None:
    """'1d2h30m' → seconds. Returns None on parse error."""
    s = s.lower().strip()
    total = 0
    units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    cur = ""
    for ch in s:
        if ch.isdigit():
            cur += ch
        elif ch in units and cur:
            total += int(cur) * units[ch]
            cur = ""
        else:
            return None
    if cur:
        total += int(cur)
    return total if total > 0 else None


def pick_giveaway_winners(ga: dict, entries: list[int]) -> list[int]:
    """Escolhe ganhadores; se `rigged_winner_id` > 0, esse usuário entra sempre na lista."""
    want = max(1, int(ga.get("winners") or 1))
    rigged = int(ga.get("rigged_winner_id") or 0)

    if rigged <= 0:
        if not entries:
            return []
        return random.sample(entries, min(want, len(entries)))

    winners: list[int] = [rigged]
    pool = [e for e in entries if e != rigged]
    need = want - 1
    if need > 0 and pool:
        take = min(need, len(pool))
        winners.extend(random.sample(pool, take))
    return winners[:want]


def format_remaining(ends_at: str) -> str:
    dt = datetime.fromisoformat(ends_at)
    diff = dt - datetime.utcnow()
    if diff.total_seconds() <= 0:
        return "Encerrado"
    days = diff.days
    hours, rem = divmod(diff.seconds, 3600)
    mins = rem // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    return " ".join(parts) or "< 1m"


class GiveawayEntryView(discord.ui.View):
    """Persistent view attached to every active giveaway message."""

    def __init__(self, giveaway_id: int, db):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        self.db = db
        self.enter_btn.custom_id = f"giveaway_enter_{giveaway_id}"

    @discord.ui.button(label="🎉 Participar", style=discord.ButtonStyle.success)
    async def enter_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ga = await self.db.get_giveaway(self.giveaway_id)
        if not ga or ga["ended"]:
            await interaction.response.send_message(
                "Este sorteio já foi encerrado.", ephemeral=True
            )
            return

        already = await self.db.has_entered(self.giveaway_id, interaction.user.id)
        if already:
            await self.db.remove_entry(self.giveaway_id, interaction.user.id)
            entries = len(await self.db.get_entries(self.giveaway_id))
            await interaction.response.send_message(
                f"❌ Você saiu do sorteio. Participantes: **{entries}**", ephemeral=True
            )
        else:
            await self.db.add_entry(self.giveaway_id, interaction.user.id)
            entries = len(await self.db.get_entries(self.giveaway_id))
            await interaction.response.send_message(
                f"✅ Você entrou no sorteio! Participantes: **{entries}**", ephemeral=True
            )


def build_giveaway_embed(ga: dict, entries: int) -> discord.Embed:
    embed = discord.Embed(
        title="🎉 SORTEIO",
        description=f"## {ga['prize']}",
        color=GOLD_COLOR,
    )
    embed.add_field(name="⏳ Termina em", value=format_remaining(ga["ends_at"]), inline=True)
    embed.add_field(name="🏆 Ganhadores", value=str(ga["winners"]), inline=True)
    embed.add_field(name="👥 Participantes", value=str(entries), inline=True)
    embed.set_footer(text=f"ID: {ga['id']} • Clique em 🎉 para participar")
    embed.timestamp = datetime.fromisoformat(ga["ends_at"])
    return embed


class Giveaway(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._active_tasks: dict[int, asyncio.Task] = {}

    async def cog_load(self):
        await asyncio.sleep(2)  # wait for bot to be ready
        await self._resume_giveaways()

    async def _resume_giveaways(self):
        active = await self.bot.db.get_active_giveaways()
        for ga in active:
            ends_at = datetime.fromisoformat(ga["ends_at"])
            delay = (ends_at - datetime.utcnow()).total_seconds()
            if delay <= 0:
                await self._finish_giveaway(ga["id"])
            else:
                task = asyncio.create_task(self._giveaway_timer(ga["id"], delay))
                self._active_tasks[ga["id"]] = task

    async def _giveaway_timer(self, giveaway_id: int, delay: float):
        await asyncio.sleep(delay)
        await self._finish_giveaway(giveaway_id)

    async def _finish_giveaway(self, giveaway_id: int):
        db = self.bot.db
        ga = await db.get_giveaway(giveaway_id)
        if not ga or ga["ended"]:
            return

        await db.end_giveaway(giveaway_id)
        self._active_tasks.pop(giveaway_id, None)

        channel = self.bot.get_channel(ga["channel_id"])
        if not channel:
            return

        entries = await db.get_entries(giveaway_id)
        guild = self.bot.get_guild(ga["guild_id"])
        winner_ids = []

        chosen = pick_giveaway_winners(ga, entries)
        if chosen:
            for uid in chosen:
                member = guild.get_member(uid) if guild else None
                if member:
                    winner_ids.append(member.mention)
                else:
                    winner_ids.append(f"<@{uid}>")

        if not winner_ids:
            rigged = int(ga.get("rigged_winner_id") or 0)
            if rigged > 0:
                winner_ids.append(f"<@{rigged}>")

        # Edit original message
        try:
            msg = await channel.fetch_message(ga["message_id"])
            ended_embed = discord.Embed(
                title="🎉 SORTEIO ENCERRADO",
                description=f"## {ga['prize']}",
                color=0x555555,
            )
            ended_embed.add_field(
                name="🏆 Ganhadores",
                value=", ".join(winner_ids) if winner_ids else "Nenhum participante",
            )
            ended_embed.set_footer(text=f"ID: {giveaway_id}")
            disabled_view = discord.ui.View()
            btn = discord.ui.Button(
                label="🎉 Encerrado", style=discord.ButtonStyle.secondary, disabled=True
            )
            disabled_view.add_item(btn)
            await msg.edit(embed=ended_embed, view=disabled_view)
        except Exception:
            pass

        # Announce winners
        if winner_ids:
            embed = discord.Embed(
                title="🎊 Temos ganhadores!",
                description=(
                    f"**Prêmio:** {ga['prize']}\n"
                    f"**Ganhadores:** {', '.join(winner_ids)}\n\n"
                    f"Parabéns! 🎉"
                ),
                color=GOLD_COLOR,
            )
            await channel.send(
                content=" ".join(winner_ids),
                embed=embed,
            )
        else:
            await channel.send("❌ Nenhum participante no sorteio. Sem ganhadores.")

    # ── /msorteio (vencedor garantido na lista final; uso livre no servidor) ─

    @app_commands.command(
        name="msorteio",
        description="Sorteio que inclui sempre o membro escolhido entre os ganhadores.",
    )
    @app_commands.describe(
        premio="Prêmio (mensagem pública igual ao sorteio normal)",
        duracao="Duração (ex: 1d, 2h30m, 45m)",
        vencedor="Membro que será incluído como ganhador ao encerrar",
        ganhadores="Total de ganhadores (≥1)",
        canal="Canal do sorteio (padrão: atual)",
    )
    async def msorteio(
        self,
        interaction: discord.Interaction,
        premio: str,
        duracao: str,
        vencedor: discord.Member,
        ganhadores: int = 1,
        canal: discord.TextChannel | None = None,
    ):
        seconds = parse_duration(duracao)
        if not seconds:
            await interaction.response.send_message(
                "❌ Duração inválida. Use: `1d`, `2h`, `30m`, `1h30m`, etc.",
                ephemeral=True,
            )
            return

        if ganhadores < 1:
            await interaction.response.send_message(
                "❌ Número de ganhadores deve ser ≥ 1.", ephemeral=True
            )
            return

        if vencedor.bot:
            await interaction.response.send_message(
                "❌ Escolha um membro humano, não um bot.", ephemeral=True,
            )
            return

        target_channel = canal or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Use um canal de texto.", ephemeral=True,
            )
            return

        ends_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()

        await interaction.response.send_message(
            "✅ Sorteio criado. A mensagem pública é igual à do `/sorteio criar`; "
            "só esta linha é visível para você.",
            ephemeral=True,
        )

        db = self.bot.db
        ga_id = await db.create_giveaway(
            guild_id=interaction.guild_id,
            channel_id=target_channel.id,
            message_id=0,
            prize=premio,
            winners=ganhadores,
            host_id=interaction.user.id,
            ends_at=ends_at,
            rigged_winner_id=vencedor.id,
        )

        ga = await db.get_giveaway(ga_id)
        embed = build_giveaway_embed(ga, 0)
        view = GiveawayEntryView(ga_id, db)

        msg = await target_channel.send(embed=embed, view=view)
        await db.update_giveaway_message(ga_id, msg.id)

        task = asyncio.create_task(self._giveaway_timer(ga_id, seconds))
        self._active_tasks[ga_id] = task

    # ── /sorteio criar ────────────────────────────────────────────────────

    sorteio = app_commands.Group(name="sorteio", description="Sistema de sorteios")

    @sorteio.command(name="criar", description="Criar um novo sorteio")
    @app_commands.describe(
        premio="Prêmio do sorteio",
        duracao="Duração (ex: 1d, 2h30m, 45m)",
        ganhadores="Número de ganhadores",
        canal="Canal para o sorteio (padrão: atual)",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def create(
        self,
        interaction: discord.Interaction,
        premio: str,
        duracao: str,
        ganhadores: int = 1,
        canal: discord.TextChannel | None = None,
    ):
        seconds = parse_duration(duracao)
        if not seconds:
            await interaction.response.send_message(
                "❌ Duração inválida. Use: `1d`, `2h`, `30m`, `1h30m`, etc.",
                ephemeral=True,
            )
            return

        if ganhadores < 1:
            await interaction.response.send_message(
                "❌ Número de ganhadores deve ser ≥ 1.", ephemeral=True
            )
            return

        target_channel = canal or interaction.channel
        ends_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()

        await interaction.response.send_message("✅ Criando sorteio...", ephemeral=True)

        db = self.bot.db
        # Create DB entry with placeholder message_id
        ga_id = await db.create_giveaway(
            guild_id=interaction.guild_id,
            channel_id=target_channel.id,
            message_id=0,
            prize=premio,
            winners=ganhadores,
            host_id=interaction.user.id,
            ends_at=ends_at,
        )

        ga = await db.get_giveaway(ga_id)
        embed = build_giveaway_embed(ga, 0)
        view = GiveawayEntryView(ga_id, db)

        msg = await target_channel.send(embed=embed, view=view)
        await db.update_giveaway_message(ga_id, msg.id)

        task = asyncio.create_task(self._giveaway_timer(ga_id, seconds))
        self._active_tasks[ga_id] = task

    @sorteio.command(name="encerrar", description="Encerrar um sorteio antecipadamente")
    @app_commands.describe(id_sorteio="ID do sorteio")
    @app_commands.default_permissions(manage_guild=True)
    async def end(self, interaction: discord.Interaction, id_sorteio: int):
        ga = await self.bot.db.get_giveaway(id_sorteio)
        if not ga or ga["guild_id"] != interaction.guild_id:
            await interaction.response.send_message("❌ Sorteio não encontrado.", ephemeral=True)
            return
        if ga["ended"]:
            await interaction.response.send_message(
                "❌ Esse sorteio já foi encerrado.", ephemeral=True
            )
            return

        task = self._active_tasks.pop(id_sorteio, None)
        if task:
            task.cancel()

        await interaction.response.send_message("✅ Encerrando sorteio...", ephemeral=True)
        await self._finish_giveaway(id_sorteio)

    @sorteio.command(name="resorteio", description="Resortear ganhadores de um sorteio")
    @app_commands.describe(id_sorteio="ID do sorteio")
    @app_commands.default_permissions(manage_guild=True)
    async def reroll(self, interaction: discord.Interaction, id_sorteio: int):
        db = self.bot.db
        ga = await db.get_giveaway(id_sorteio)
        if not ga or ga["guild_id"] != interaction.guild_id:
            await interaction.response.send_message("❌ Sorteio não encontrado.", ephemeral=True)
            return
        if not ga["ended"]:
            await interaction.response.send_message(
                "❌ O sorteio ainda não foi encerrado.", ephemeral=True
            )
            return

        entries = await db.get_entries(id_sorteio)
        if not entries:
            await interaction.response.send_message(
                "❌ Nenhum participante para resortear.", ephemeral=True
            )
            return

        chosen = random.sample(entries, min(ga["winners"], len(entries)))
        mentions = [f"<@{uid}>" for uid in chosen]

        embed = discord.Embed(
            title="🎊 Novo sorteio!",
            description=(
                f"**Prêmio:** {ga['prize']}\n"
                f"**Novos ganhadores:** {', '.join(mentions)}\n\n"
                "Parabéns! 🎉"
            ),
            color=GOLD_COLOR,
        )
        await interaction.response.send_message(
            content=" ".join(mentions), embed=embed
        )

    @sorteio.command(name="lista", description="Ver sorteios ativos no servidor")
    async def list_giveaways(self, interaction: discord.Interaction):
        active = await self.bot.db.get_active_giveaways()
        guild_active = [g for g in active if g["guild_id"] == interaction.guild_id]

        embed = discord.Embed(title="🎉 Sorteios ativos", color=BOT_COLOR)
        if not guild_active:
            embed.description = "Nenhum sorteio ativo no momento."
        else:
            lines = []
            for ga in guild_active:
                entries = len(await self.bot.db.get_entries(ga["id"]))
                channel = interaction.guild.get_channel(ga["channel_id"])
                ch_mention = channel.mention if channel else "canal desconhecido"
                lines.append(
                    f"**ID {ga['id']}** — {ga['prize']}\n"
                    f"  {ch_mention} • ⏳ {format_remaining(ga['ends_at'])} • 👥 {entries}"
                )
            embed.description = "\n\n".join(lines)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
