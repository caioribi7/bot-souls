"""
cogs/guide.py  –  /guia interativo + /mensagem com Embed Creator por modais
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_COLOR, SUCCESS_COLOR, ERROR_COLOR, WARNING_COLOR


# ─── Guia Interativo ──────────────────────────────────────────────────────────

class GuideView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Este guia foi aberto por outro usuário.", ephemeral=True)
            return False
        return True

    async def _swap(self, interaction, title, text):
        embed = discord.Embed(title=title, description=text, color=BOT_COLOR)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🪪 Perfil & Rank", style=discord.ButtonStyle.secondary, row=0)
    async def profile_btn(self, interaction, _):
        await self._swap(interaction, "🪪 Perfil & Rank",
            "`/perfil ver [membro]` - card visual\n"
            "`/perfil editar` - menu interativo\n"
            "`/perfil banner [url]` - banner (suporta GIF)\n"
            "`/perfil icone [url]` - badge do avatar\n"
            "`/perfil tema` - claro/escuro\n"
            "`/perfil cor`, `/perfil cor-preset`, `/perfil fundo`\n"
            "`/perfil bio`, `/perfil info`, `/perfil resetar`\n"
            "`/leaderboard` - ranking em imagem")

    @discord.ui.button(label="💰 Sweet Coins", style=discord.ButtonStyle.secondary, row=0)
    async def eco_btn(self, interaction, _):
        await self._swap(interaction, "💰 Sweet Coins",
            "`/banco saldo [membro]` - saldo\n"
            "`/banco transferir membro valor` - transferir moedas\n"
            "`/banco ranking` - top ricos\n"
            "`/coinsdiarias` - resgate diário\n"
            "`/apostar blackjack valor` - blackjack\n"
            "`/apostar bombinha valor` - 💣 Mines\n"
            "`/apostar foguetinho valor multiplicador` - 🚀 Crash\n"
            "`/apostar roleta valor aposta` - roleta\n"
            "`/pix` - compra de coins via Pix")

    @discord.ui.button(label="🏪 Loja", style=discord.ButtonStyle.secondary, row=0)
    async def shop_btn(self, interaction, _):
        await self._swap(interaction, "🏪 Loja e Mercado",
            "Clique em **🛒 Ver Loja** no painel para abrir o catálogo\n"
            "Clique em **✨ Criar Cargo** para criar seu cargo personalizado\n"
            "Clique em **🔄 Mercado** para comprar cargos de outros jogadores\n"
            "Clique em **🎒 Meu Inventário** para equipar seus cargos\n"
            "`/mercado listar cargo preco` - vender cargo\n"
            "`/mercado cancelar id` - cancelar anúncio")

    @discord.ui.button(label="🎉 Sorteios", style=discord.ButtonStyle.secondary, row=0)
    async def give_btn(self, interaction, _):
        await self._swap(interaction, "🎉 Sorteios",
            "`/sorteio criar premio duracao ganhadores`\n"
            "`/sorteio encerrar id`\n"
            "`/sorteio resorteio id`\n"
            "`/sorteio lista`")

    @discord.ui.button(label="📨 Anônimos", style=discord.ButtonStyle.secondary, row=0)
    async def anon_btn(self, interaction, _):
        await self._swap(interaction, "📨 Mensagens Anônimas",
            "Clique em `💌 Enviar mensagem anônima` no painel público.\n"
            "As mensagens aparecem no canal de envio como GIF com o texto.\n"
            "Admins: `/anon-admin configurar`, `/anon-admin status`, `/anon-admin ativar`.")

    @discord.ui.button(label="🛡️ Clãs", style=discord.ButtonStyle.secondary, row=1)
    async def clan_btn(self, interaction, _):
        await self._swap(interaction, "🛡️ Clãs",
            "`/clan criar nome [cor] [descricao]`\n"
            "`/clan convidar membro`, `/clan aceitar`, `/clan recusar`\n"
            "`/clan info`, `/clan lista`, `/clan editar`\n"
            "`/clan deixar`, `/clan kick`, `/clan transferir`, `/clan deletar`\n"
            "Quanto mais membros, maior bônus de XP do clã.")

    @discord.ui.button(label="💍 Casamentos", style=discord.ButtonStyle.secondary, row=1)
    async def marriage_btn(self, interaction, _):
        await self._swap(interaction, "💍 Casamentos",
            "`/casar propor`, `/casar aceitar`, `/casar recusar`, `/casar divorciar`\n"
            "`/casar padrinho adicionar/remover` (máx. 2 padrinhos)\n"
            "`/casar cofre depositar`, `/casar cofre sacar`, `/casar cofre saldo`\n"
            "`/casar info [membro]`\n"
            "Padrinhos ativos recebem bônus de XP.")

    @discord.ui.button(label="🎫 Tickets", style=discord.ButtonStyle.secondary, row=1)
    async def ticket_btn(self, interaction, _):
        await self._swap(interaction, "🎫 Tickets",
            "Selecione uma categoria no painel de tickets para abrir seu ticket.\n"
            "Categorias: ❓ Dúvidas | 🤝 Parcerias | 💬 Outros\n"
            "Canal privado criado automaticamente.\n"
            "`/ticket fechar` — fecha o ticket atual.\n"
            "Admins: `/ticket configurar`, `/ticket painel`.")

    @discord.ui.button(label="⚔️ Moderação", style=discord.ButtonStyle.secondary, row=1)
    async def mod_btn(self, interaction, _):
        await self._swap(interaction, "⚔️ Moderação",
            "`/mod ban`, `/mod kick`, `/mod timeout`\n"
            "`/mod warn`, `/mod warns`, `/mod remover-warn`, `/mod limpar-warns`\n"
            "`/mod lock`, `/mod unlock`, `/mod nuke`\n"
            "`/limpar quantidade [canal]`\n"
            "`/slowmode segundos [canal]`")

    @discord.ui.button(label="⚙️ Admin Setup", style=discord.ButtonStyle.primary, row=1)
    async def setup_btn(self, interaction, _):
        await self._swap(interaction, "⚙️ Setup Inicial",
            "`/painel` - painel central de configurações\n"
            "`/loja-admin configurar canal` - cria painel da loja\n"
            "`/boas-vindas configurar canal mensagem` - até 2 canais + DM\n"
            "`/ticket configurar` - painel interativo de tickets\n"
            "`/anon-admin configurar canal_menu canal_envio [log]`\n"
            "`/xp-admin ...` para níveis e recompensas\n"
            "`/mensagem` - Embed Creator interativo (clique e configure)")


# ─── Embed Creator ────────────────────────────────────────────────────────────

class EmbedCreatorState:
    """Mantém o estado do embed em construção."""
    def __init__(self, canal: discord.TextChannel):
        self.canal = canal
        self.titulo = "📢 Anúncio"
        self.descricao = ""
        self.cor = BOT_COLOR
        self.cor_hex = "#5865F2"
        self.thumbnail_url = ""
        self.image_url = ""
        self.autor_texto = ""
        self.footer_texto = ""
        self.marcar_here = False

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=self.titulo or discord.Embed.Empty,
            description=self.descricao or discord.Embed.Empty,
            color=self.cor,
            timestamp=datetime.now(timezone.utc),
        )
        if self.autor_texto:
            embed.set_author(name=self.autor_texto)
        if self.footer_texto:
            embed.set_footer(text=self.footer_texto)
        elif not self.footer_texto:
            embed.set_footer(text="")
        if self.thumbnail_url:
            embed.set_thumbnail(url=self.thumbnail_url)
        if self.image_url:
            embed.set_image(url=self.image_url)
        return embed


# ── Modais ────────────────────────────────────────────────────────────────────

class ModalTitulo(discord.ui.Modal, title="✏️ Editar Título"):
    campo = discord.ui.TextInput(label="Título do embed", max_length=256, required=False)

    def __init__(self, state: EmbedCreatorState, view: "EmbedCreatorView"):
        super().__init__()
        self.state = state
        self._view = view
        self.campo.default = state.titulo

    async def on_submit(self, interaction: discord.Interaction):
        self.state.titulo = self.campo.value
        await self._view.refresh(interaction)


class ModalDescricao(discord.ui.Modal, title="📝 Editar Descrição"):
    campo = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, max_length=4000, required=False)

    def __init__(self, state: EmbedCreatorState, view: "EmbedCreatorView"):
        super().__init__()
        self.state = state
        self._view = view
        self.campo.default = state.descricao

    async def on_submit(self, interaction: discord.Interaction):
        self.state.descricao = self.campo.value
        await self._view.refresh(interaction)


class ModalCor(discord.ui.Modal, title="🎨 Editar Cor"):
    campo = discord.ui.TextInput(label="Cor em Hex (ex: #FF5733)", max_length=7, required=False)

    def __init__(self, state: EmbedCreatorState, view: "EmbedCreatorView"):
        super().__init__()
        self.state = state
        self._view = view
        self.campo.default = state.cor_hex

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.campo.value.strip().lstrip("#")
        try:
            cor = int(raw, 16)
            self.state.cor = cor
            self.state.cor_hex = f"#{raw.upper()}"
        except ValueError:
            pass
        await self._view.refresh(interaction)


class ModalThumbnail(discord.ui.Modal, title="🖼️ Thumbnail (imagem pequena)"):
    campo = discord.ui.TextInput(label="URL da thumbnail", required=False, max_length=512)

    def __init__(self, state: EmbedCreatorState, view: "EmbedCreatorView"):
        super().__init__()
        self.state = state
        self._view = view
        self.campo.default = state.thumbnail_url

    async def on_submit(self, interaction: discord.Interaction):
        self.state.thumbnail_url = self.campo.value.strip()
        await self._view.refresh(interaction)


class ModalImagem(discord.ui.Modal, title="🖼️ Imagem Grande"):
    campo = discord.ui.TextInput(label="URL da imagem grande", required=False, max_length=512)

    def __init__(self, state: EmbedCreatorState, view: "EmbedCreatorView"):
        super().__init__()
        self.state = state
        self._view = view
        self.campo.default = state.image_url

    async def on_submit(self, interaction: discord.Interaction):
        self.state.image_url = self.campo.value.strip()
        await self._view.refresh(interaction)


class ModalAutor(discord.ui.Modal, title="👤 Texto do Autor"):
    campo = discord.ui.TextInput(label="Autor (deixe vazio para remover)", required=False, max_length=256)

    def __init__(self, state: EmbedCreatorState, view: "EmbedCreatorView"):
        super().__init__()
        self.state = state
        self._view = view
        self.campo.default = state.autor_texto

    async def on_submit(self, interaction: discord.Interaction):
        self.state.autor_texto = self.campo.value.strip()
        await self._view.refresh(interaction)


class ModalFooter(discord.ui.Modal, title="📌 Texto do Rodapé"):
    campo = discord.ui.TextInput(label="Rodapé (deixe vazio para remover)", required=False, max_length=2048)

    def __init__(self, state: EmbedCreatorState, view: "EmbedCreatorView"):
        super().__init__()
        self.state = state
        self._view = view
        self.campo.default = state.footer_texto

    async def on_submit(self, interaction: discord.Interaction):
        self.state.footer_texto = self.campo.value.strip()
        await self._view.refresh(interaction)


# ── View Principal ────────────────────────────────────────────────────────────

def _control_embed(state: EmbedCreatorState) -> discord.Embed:
    """Painel de controle do Embed Creator."""
    lines = [
        f"**📢 Canal destino:** {state.canal.mention}",
        f"**✏️ Título:** {state.titulo or '*(vazio)*'}",
        f"**📝 Descrição:** {(state.descricao[:80] + '…') if len(state.descricao) > 80 else state.descricao or '*(vazia)*'}",
        f"**🎨 Cor:** `{state.cor_hex}`",
        f"**🖼️ Thumbnail:** {'✅' if state.thumbnail_url else '—'}",
        f"**🖼️ Imagem grande:** {'✅' if state.image_url else '—'}",
        f"**👤 Autor:** {state.autor_texto or '—'}",
        f"**📌 Rodapé:** {state.footer_texto or '—'}",
        f"**📣 @here:** {'✅ Sim' if state.marcar_here else '❌ Não'}",
    ]
    embed = discord.Embed(
        title="✨ Embed Creator",
        description="\n".join(lines),
        color=state.cor,
    )
    embed.set_footer(text="Use os botões abaixo para personalizar e depois clique em 🚀 Enviar")
    return embed


class EmbedCreatorView(discord.ui.View):
    def __init__(self, state: EmbedCreatorState, author_id: int):
        super().__init__(timeout=300)
        self.state = state
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Este painel pertence a outro usuário.", ephemeral=True)
            return False
        return True

    async def refresh(self, interaction: discord.Interaction):
        embed = _control_embed(self.state)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="✏️ Título", style=discord.ButtonStyle.secondary, row=0)
    async def btn_titulo(self, interaction, _):
        await interaction.response.send_modal(ModalTitulo(self.state, self))

    @discord.ui.button(label="📝 Descrição", style=discord.ButtonStyle.secondary, row=0)
    async def btn_desc(self, interaction, _):
        await interaction.response.send_modal(ModalDescricao(self.state, self))

    @discord.ui.button(label="🎨 Cor", style=discord.ButtonStyle.secondary, row=0)
    async def btn_cor(self, interaction, _):
        await interaction.response.send_modal(ModalCor(self.state, self))

    @discord.ui.button(label="👤 Autor", style=discord.ButtonStyle.secondary, row=0)
    async def btn_autor(self, interaction, _):
        await interaction.response.send_modal(ModalAutor(self.state, self))

    @discord.ui.button(label="📌 Rodapé", style=discord.ButtonStyle.secondary, row=0)
    async def btn_footer(self, interaction, _):
        await interaction.response.send_modal(ModalFooter(self.state, self))

    @discord.ui.button(label="🖼️ Thumbnail", style=discord.ButtonStyle.secondary, row=1)
    async def btn_thumb(self, interaction, _):
        await interaction.response.send_modal(ModalThumbnail(self.state, self))

    @discord.ui.button(label="🖼️ Imagem", style=discord.ButtonStyle.secondary, row=1)
    async def btn_imagem(self, interaction, _):
        await interaction.response.send_modal(ModalImagem(self.state, self))

    @discord.ui.button(label="📣 @here: OFF", style=discord.ButtonStyle.secondary, row=1)
    async def btn_here(self, interaction, button: discord.ui.Button):
        self.state.marcar_here = not self.state.marcar_here
        button.label = f"📣 @here: {'ON' if self.state.marcar_here else 'OFF'}"
        button.style = discord.ButtonStyle.success if self.state.marcar_here else discord.ButtonStyle.secondary
        await self.refresh(interaction)

    @discord.ui.button(label="👁️ Pré-visualizar", style=discord.ButtonStyle.primary, row=2)
    async def btn_preview(self, interaction, _):
        preview = self.state.build_embed()
        preview.title = f"[PREVIEW] {preview.title or ''}"
        await interaction.response.send_message(embed=preview, ephemeral=True)

    @discord.ui.button(label="🚀 Enviar", style=discord.ButtonStyle.success, row=2)
    async def btn_enviar(self, interaction, _):
        if not self.state.descricao and not self.state.titulo:
            return await interaction.response.send_message("❌ Adicione pelo menos um título ou descrição.", ephemeral=True)
        embed = self.state.build_embed()
        content = "@here" if self.state.marcar_here else None
        try:
            await self.state.canal.send(content=content, embed=embed)
        except discord.Forbidden:
            return await interaction.response.send_message(f"❌ Sem permissão para enviar em {self.state.canal.mention}.", ephemeral=True)
        # Desativa todos os botões
        for child in self.children:
            child.disabled = True
        success = discord.Embed(
            title="✅ Mensagem Enviada!",
            description=f"O anúncio foi publicado em {self.state.canal.mention}.",
            color=SUCCESS_COLOR,
        )
        await interaction.response.edit_message(embed=success, view=self)

    @discord.ui.button(label="🗑️ Cancelar", style=discord.ButtonStyle.danger, row=2)
    async def btn_cancelar(self, interaction, _):
        for child in self.children:
            child.disabled = True
        embed = discord.Embed(description="❌ Embed Creator cancelado.", color=ERROR_COLOR)
        await interaction.response.edit_message(embed=embed, view=self)


# ─── Cog ─────────────────────────────────────────────────────────────────────

class Guide(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="guia", description="Guia interativo com todos os sistemas do bot")
    async def guia(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📘 Guia do Bot",
            description="Escolha uma categoria nos botões abaixo para ver os comandos.\nEste guia cobre perfil, economia, loja, clãs, casamento, tickets, moderação e setup.",
            color=BOT_COLOR,
        )
        view = GuideView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="mensagem", description="📢 Embed Creator interativo — crie e envie anúncios personalizados")
    @app_commands.describe(canal="Canal onde o anúncio será publicado")
    @app_commands.checks.has_permissions(administrator=True)
    async def mensagem(self, interaction: discord.Interaction, canal: discord.TextChannel):
        state = EmbedCreatorState(canal)
        view = EmbedCreatorView(state, interaction.user.id)
        embed = _control_embed(state)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @mensagem.error
    async def mensagem_error(self, interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("Você precisa ser administrador para usar este comando.", ephemeral=True)
            return
        raise error


async def setup(bot):
    await bot.add_cog(Guide(bot))
