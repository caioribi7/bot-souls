from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_COLOR


def _mensagem_para_linhas(mensagem: str, separador: str | None) -> list[str]:
    """Aceita quebras reais, \\n digitado no slash, e um separador customizado."""
    text = (
        mensagem.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("/n", "\n")
    )
    sep = (separador or "").strip()
    if sep:
        parts = [p.strip() for p in text.split(sep)]
    else:
        parts = [line.strip() for line in text.splitlines()]
    return [p for p in parts if p]


class GuideView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Este guia interativo foi aberto por outro usuário.",
                ephemeral=True,
            )
            return False
        return True

    async def _swap(self, interaction: discord.Interaction, title: str, text: str):
        embed = discord.Embed(title=title, description=text, color=BOT_COLOR)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🪪 Perfil & Rank", style=discord.ButtonStyle.secondary, row=0)
    async def profile_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._swap(
            interaction,
            "🪪 Perfil & Rank",
            "\n".join(
                [
                    "`/perfil ver [membro]` - card visual",
                    "`/perfil editar` - menu interativo",
                    "`/perfil banner [url] [arquivo]` - suporta GIF",
                    "`/perfil icone [url] [arquivo]` - badge do avatar",
                    "`/perfil tema` - claro/escuro",
                    "`/perfil cor`, `/perfil cor-preset`, `/perfil fundo`",
                    "`/perfil bio`, `/perfil info`, `/perfil resetar`",
                    "`/leaderboard` - ranking em imagem",
                ]
            ),
        )

    @discord.ui.button(label="💰 Sweet Coins", style=discord.ButtonStyle.secondary, row=0)
    async def eco_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._swap(
            interaction,
            "💰 Sweet Coins",
            "\n".join(
                [
                    "`/banco saldo [membro]` - saldo",
                    "`/banco transferir membro valor` - transferir moedas",
                    "`/banco ranking` - top ricos",
                    "`/coinsdiarias` - resgate diário",
                    "`/apostar blackjack valor` - blackjack",
                    "`/apostar bombinha valor` - 💣 Mines (Bombinha)",
                    "`/apostar foguetinho valor multiplicador_alvo` - 🚀 crash (Foguetinho)",
                    "`/apostar roleta valor aposta` - roleta",
                    "`/pix` - compra de coins via Pix",
                ]
            ),
        )

    @discord.ui.button(label="🏪 Loja", style=discord.ButtonStyle.secondary, row=0)
    async def shop_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._swap(
            interaction,
            "🏪 Loja e Mercado",
            "\n".join(
                [
                    "Clique em **🛒 Ver Loja** no painel para abrir o catálogo",
                    "Clique em **✨ Criar Cargo** para criar seu cargo personalizado",
                    "Clique em **🔄 Mercado** para comprar cargos de outros jogadores",
                    "Clique em **🎒 Meu Inventário** para equipar e desequipar seus cargos",
                    "`/mercado listar cargo preco` - vender cargo no mercado",
                    "`/mercado cancelar id` - cancelar seu anúncio",
                ]
            ),
        )

    @discord.ui.button(label="🎉 Sorteios", style=discord.ButtonStyle.secondary, row=0)
    async def give_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._swap(
            interaction,
            "🎉 Sorteios",
            "\n".join(
                [
                    "`/sorteio criar premio duracao ganhadores`",
                    "`/sorteio encerrar id_sorteio`",
                    "`/sorteio resorteio id_sorteio`",
                    "`/sorteio lista`",
                ]
            ),
        )

    @discord.ui.button(label="📨 Anônimos", style=discord.ButtonStyle.secondary, row=0)
    async def anon_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._swap(
            interaction,
            "📨 Mensagens Anônimas",
            "\n".join(
                [
                    "Clique em `💌 Enviar mensagem anônima` no **canal de menu** (painel público).",
                    "As mensagens vão ao **canal de envio** como GIF com o texto.",
                    "Admins: `/anon-admin configurar` (menu + envio + log opcional), `/anon-admin status`, `/anon-admin ativar`.",
                ]
            ),
        )

    @discord.ui.button(label="🛡️ Clãs", style=discord.ButtonStyle.secondary, row=1)
    async def clan_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._swap(
            interaction,
            "🛡️ Clãs",
            "\n".join(
                [
                    "`/clan criar nome [cor] [descricao]`",
                    "`/clan convidar membro`, `/clan aceitar`, `/clan recusar`",
                    "`/clan info`, `/clan lista`, `/clan editar`",
                    "`/clan deixar`, `/clan kick`, `/clan transferir`, `/clan deletar`",
                    "Quanto mais membros, maior bônus de XP do clã.",
                ]
            ),
        )

    @discord.ui.button(label="💍 Casamentos", style=discord.ButtonStyle.secondary, row=1)
    async def marriage_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._swap(
            interaction,
            "💍 Casamentos",
            "\n".join(
                [
                    "`/casar propor`, `/casar aceitar`, `/casar recusar`, `/casar divorciar`",
                    "`/casar padrinho adicionar/remover` (máx. 2 padrinhos)",
                    "`/casar cofre depositar`, `/casar cofre sacar`, `/casar cofre saldo`",
                    "`/casar info [membro]`",
                    "Padrinhos ativos recebem bônus de XP.",
                ]
            ),
        )

    @discord.ui.button(label="🎫 Tickets", style=discord.ButtonStyle.secondary, row=1)
    async def ticket_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._swap(
            interaction,
            "🎫 Tickets",
            "\n".join(
                [
                    "Usuários abrem por botão `📬 Abrir Ticket` no painel.",
                    "Canal privado criado automaticamente.",
                    "`/ticket fechar` fecha o ticket atual.",
                    "Admins: `/ticket configurar`, `/ticket painel`.",
                ]
            ),
        )

    @discord.ui.button(label="⚔️ Moderação", style=discord.ButtonStyle.secondary, row=1)
    async def mod_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._swap(
            interaction,
            "⚔️ Moderação",
            "\n".join(
                [
                    "`/mod ban`, `/mod kick`, `/mod timeout`",
                    "`/mod warn`, `/mod warns`, `/mod remover-warn`, `/mod limpar-warns`",
                    "`/mod lock`, `/mod unlock`, `/mod nuke`",
                    "`/limpar quantidade [canal]`",
                    "`/slowmode segundos [canal]`",
                ]
            ),
        )

    @discord.ui.button(label="⚙️ Admin Setup", style=discord.ButtonStyle.primary, row=1)
    async def setup_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._swap(
            interaction,
            "⚙️ Setup Inicial",
            "\n".join(
                [
                    "`/painel` - painel central de configurações",
                    "`/loja-admin configurar canal` - cria painel da loja",
                    "`/boas-vindas configurar canal mensagem`",
                    "`/ticket configurar canal categoria log`",
                    "`/anon-admin configurar canal_menu canal_envio [log]`",
                    "`/xp-admin ...` para níveis e recompensas",
                    "`/mensagem` — use `\\n` no texto ou `separador_linhas` (ex: `|`) para várias linhas.",
                ]
            ),
        )


class Guide(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="guia", description="Guia interativo com todos os sistemas do bot")
    async def guia(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📘 Guia do Bot Supremo",
            description=(
                "Escolha uma categoria nos botões abaixo para ver os comandos.\n"
                "Este guia cobre perfil, economia, loja, clãs, casamento, tickets, moderação e setup."
            ),
            color=BOT_COLOR,
        )
        view = GuideView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="mensagem", description="Enviar anúncio oficial em um canal")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        canal="Canal do anúncio",
        titulo="Título da mensagem",
        mensagem=(
            "Texto do anúncio. Use quebras reais, ou digite \\n entre partes, "
            "ou use separador_linhas (ex: | ou //)."
        ),
        marcar_here="Marcar @here no anúncio",
        separar_linhas="Inserir linha divisória entre cada parte",
        separador_linhas="Opcional: caractere(s) que separam trechos (ex: |  ou  //). Vazio = só \\n ou Enter.",
    )
    async def mensagem(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        titulo: str,
        mensagem: str,
        marcar_here: bool = True,
        separar_linhas: bool = False,
        separador_linhas: str | None = None,
    ):
        lines = _mensagem_para_linhas(mensagem, separador_linhas)
        if not lines:
            await interaction.response.send_message(
                "A mensagem está vazia após processar linhas/separador.",
                ephemeral=True,
            )
            return

        text = "\n".join(lines)
        desc = text
        if separar_linhas and len(lines) > 1:
            desc = "\n━━━━━━━━━━━━━━━━━━\n".join(lines)

        embed = discord.Embed(title=titulo, description=desc, color=BOT_COLOR)
        embed.set_footer(text=f"Anúncio de {interaction.user.display_name}")
        embed.timestamp = datetime.utcnow()
        content = "@here" if marcar_here else None
        await canal.send(content=content, embed=embed)
        await interaction.response.send_message(
            f"✅ Mensagem enviada em {canal.mention}.",
            ephemeral=True,
        )

    @mensagem.error
    async def mensagem_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Você precisa ser administrador para usar este comando.",
                ephemeral=True,
            )
            return
        raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Guide(bot))
