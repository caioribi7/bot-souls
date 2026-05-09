"""
cogs/testes.py – Comando /testar para validar boas-vindas, mensagem e tickets
"""
import discord
from discord import app_commands
from discord.ext import commands
from config import BOT_COLOR, SUCCESS_COLOR, ERROR_COLOR, WARNING_COLOR

from cogs.welcome import _build_welcome_image, _format_welcome_message, _build_dm_guide_embed
from cogs.guide import EmbedCreatorState, EmbedCreatorView, _control_embed
from cogs.tickets import TicketOpenView, _ticket_panel_embed


class Testes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    testar = app_commands.Group(
        name="testar",
        description="Comandos de teste para administradores",
        default_permissions=discord.Permissions(administrator=True),
    )

    # ── /testar boas-vindas ───────────────────────────────────────────────

    @testar.command(name="boas-vindas", description="Simula a entrada de um membro: envia o card nos canais e DM de guia para você")
    @app_commands.describe(membro="Membro a simular (padrão: você mesmo)")
    async def testar_bv(self, interaction: discord.Interaction, membro: discord.Member | None = None):
        await interaction.response.defer(ephemeral=True)
        member = membro or interaction.user
        guild = interaction.guild
        cfg = await self.bot.db.get_guild_config(guild.id)

        results = []

        # Canal 1
        ch1_id = cfg.get("welcome_channel_id") or 0
        if ch1_id:
            ch1 = guild.get_channel(int(ch1_id))
            if isinstance(ch1, discord.TextChannel):
                bg_url = cfg.get("welcome_image_url") or ""
                try:
                    img_buf = await _build_welcome_image(member, guild, bg_url=bg_url)
                    await ch1.send(file=discord.File(img_buf, filename="welcome.png"))
                    template = cfg.get("welcome_message") or "Seja bem-vindo(a), {user}! Você é o {count}º membro de **{server}**."
                    await ch1.send(_format_welcome_message(template, member))
                    results.append(f"✅ Canal 1: {ch1.mention}")
                except Exception as e:
                    results.append(f"⚠️ Canal 1 ({ch1.mention}): `{e}`")
            else:
                results.append("❌ Canal 1: não encontrado")
        else:
            results.append("— Canal 1: não configurado")

        # Canal 2
        ch2_id = cfg.get("welcome_channel2_id") or 0
        if ch2_id:
            ch2 = guild.get_channel(int(ch2_id))
            if isinstance(ch2, discord.TextChannel):
                bg_url2 = cfg.get("welcome_image_url2") or cfg.get("welcome_image_url") or ""
                try:
                    img_buf2 = await _build_welcome_image(member, guild, bg_url=bg_url2)
                    await ch2.send(file=discord.File(img_buf2, filename="welcome.png"))
                    template2 = cfg.get("welcome_message2") or cfg.get("welcome_message") or "Seja bem-vindo(a), {user}!"
                    await ch2.send(_format_welcome_message(template2, member))
                    results.append(f"✅ Canal 2: {ch2.mention}")
                except Exception as e:
                    results.append(f"⚠️ Canal 2 ({ch2.mention}): `{e}`")
            else:
                results.append("❌ Canal 2: não encontrado")
        else:
            results.append("— Canal 2: não configurado")

        # DM
        dm_enabled = cfg.get("welcome_dm_enabled", 1)
        if dm_enabled:
            try:
                dm_embed = _build_dm_guide_embed(guild)
                await member.send(content="*(Teste de DM de boas-vindas)*", embed=dm_embed)
                results.append("✅ DM de guia enviada")
            except discord.Forbidden:
                results.append("⚠️ DM de guia: usuário com DMs fechadas")
        else:
            results.append("— DM de guia: desativada")

        embed = discord.Embed(
            title="🔍 Teste de Boas-Vindas",
            description=f"Simulação para **{member.display_name}**:\n\n" + "\n".join(results),
            color=SUCCESS_COLOR,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /testar mensagem ──────────────────────────────────────────────────

    @testar.command(name="mensagem", description="Abre o Embed Creator com um exemplo pré-preenchido")
    @app_commands.describe(canal="Canal de destino para teste")
    async def testar_mensagem(self, interaction: discord.Interaction, canal: discord.TextChannel | None = None):
        dest = canal or interaction.channel
        if not isinstance(dest, discord.TextChannel):
            return await interaction.response.send_message("❌ Canal inválido.", ephemeral=True)

        state = EmbedCreatorState(dest)
        state.titulo = "📢 [TESTE] Anúncio de Exemplo"
        state.descricao = (
            "Este é um **anúncio de teste** criado pelo Embed Creator!\n\n"
            "✅ Você pode personalizar:\n"
            "• Título, descrição, cor\n"
            "• Thumbnail e imagem\n"
            "• Autor e rodapé\n"
            "• Menção @here\n\n"
            "Clique nos botões abaixo para editar cada campo."
        )
        state.cor = BOT_COLOR
        state.cor_hex = "#5865F2"
        state.footer_texto = "Embed Creator — Sistema de Anúncios"

        view = EmbedCreatorView(state, interaction.user.id)
        embed = _control_embed(state)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /testar ticket ────────────────────────────────────────────────────

    @testar.command(name="ticket", description="Exibe como ficará o painel de tickets com a configuração atual")
    async def testar_ticket(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = await self.bot.db.get_tickets_config(interaction.guild.id)
        if not config:
            config = {}

        panel_embed = _ticket_panel_embed(config)
        panel_embed.title = f"[PREVIEW] {panel_embed.title}"
        view = TicketOpenView(config)

        ch_id = config.get("channel_id") or 0
        ch = interaction.guild.get_channel(int(ch_id)) if ch_id else None

        info = discord.Embed(
            title="🔍 Teste do Sistema de Tickets",
            color=BOT_COLOR,
        )
        info.add_field(name="Canal do Painel", value=ch.mention if ch else "*(não configurado)*", inline=True)

        cats = []
        if config.get("cat_duvidas_enabled", 1): cats.append(config.get("cat_duvidas_label") or "❓ Dúvidas")
        if config.get("cat_parcerias_enabled", 1): cats.append(config.get("cat_parcerias_label") or "🤝 Parcerias")
        if config.get("cat_outros_enabled", 1): cats.append(config.get("cat_outros_label") or "💬 Outros")
        info.add_field(name="Categorias Ativas", value=" | ".join(cats) if cats else "*(nenhuma)*", inline=True)
        info.set_footer(text="O select menu abaixo é apenas pré-visualização — não abrirá tickets reais")

        await interaction.followup.send(embeds=[info, panel_embed], view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Testes(bot))
