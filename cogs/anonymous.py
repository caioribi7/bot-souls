import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from config import ANON_LOVE_GIF_URL, BOT_COLOR
from utils.anon_card import build_anonymous_card

ANON_BUTTON_CUSTOM_ID = "anon_panel_send_v1"


class AnonPanelButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="💌 Enviar mensagem anônima",
            style=discord.ButtonStyle.primary,
            custom_id=ANON_BUTTON_CUSTOM_ID,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        db = interaction.client.db  # type: ignore[attr-defined]
        cfg = await db.get_anon_config(guild.id)
        if not cfg:
            await interaction.response.send_message(
                "❌ O sistema de mensagens anônimas ainda não foi configurado.",
                ephemeral=True,
            )
            return
        if not cfg.get("enabled"):
            await interaction.response.send_message(
                "❌ As mensagens anônimas estão desativadas no momento.",
                ephemeral=True,
            )
            return
        menu_id = int(cfg.get("menu_channel_id") or cfg["channel_id"])
        if interaction.channel_id != menu_id:
            await interaction.response.send_message(
                "❌ Use o botão no canal de menu das mensagens anônimas.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(AnonMessageModal())


class AnonPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(AnonPanelButton())


class AnonMessageModal(discord.ui.Modal, title="💌 Mensagem anônima"):
    body = discord.ui.TextInput(
        label="Sua mensagem",
        style=discord.TextStyle.paragraph,
        placeholder="O que você quer dizer anonimamente? Aparecerá num cartão com GIF.",
        required=True,
        max_length=900,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Use isto dentro de um servidor.", ephemeral=True)
            return

        db = interaction.client.db  # type: ignore[attr-defined]
        cfg = await db.get_anon_config(guild.id)
        if not cfg or not cfg.get("enabled"):
            await interaction.followup.send("❌ Sistema indisponível ou desativado.", ephemeral=True)
            return

        menu_id = int(cfg.get("menu_channel_id") or cfg["channel_id"])
        if interaction.channel_id != menu_id:
            await interaction.followup.send("❌ Canal inválido para este envio.", ephemeral=True)
            return

        out_ch = guild.get_channel(int(cfg["channel_id"]))
        if not isinstance(out_ch, discord.TextChannel):
            await interaction.followup.send(
                "❌ Canal de envio não encontrado. Peça a um admin para reconfigurar.",
                ephemeral=True,
            )
            return

        text = str(self.body.value).strip()
        if not text:
            await interaction.followup.send("❌ Mensagem vazia.", ephemeral=True)
            return

        try:
            gif_buf = await build_anonymous_card(text, ANON_LOVE_GIF_URL)
        except (OSError, ValueError, asyncio.TimeoutError):
            await interaction.followup.send(
                "❌ Não foi possível gerar o cartão. Tente de novo em instantes.",
                ephemeral=True,
            )
            return

        gif_buf.seek(0)
        file = discord.File(gif_buf, filename="mensagem_anonima.gif")
        try:
            await out_ch.send(file=file)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Não tenho permissão para enviar no canal de mensagens anônimas.",
                ephemeral=True,
            )
            return

        log_id = int(cfg.get("log_channel_id") or 0)
        if log_id:
            log_ch = guild.get_channel(log_id)
            if isinstance(log_ch, discord.TextChannel):
                log_embed = discord.Embed(
                    title="📋 Log — mensagem anônima",
                    description=text[:3500] if text else "—",
                    color=0xFFA500,
                )
                log_embed.add_field(
                    name="Autor",
                    value=f"{interaction.user.mention} (`{interaction.user.id}`)",
                    inline=False,
                )
                log_embed.add_field(
                    name="Canal de envio",
                    value=out_ch.mention,
                    inline=True,
                )
                log_embed.set_thumbnail(url=interaction.user.display_avatar.url)
                log_embed.set_footer(text="Conteúdo público foi postado como GIF no canal configurado.")
                try:
                    await log_ch.send(embed=log_embed)
                except discord.Forbidden:
                    pass

        await interaction.followup.send("✅ Sua mensagem foi enviada anonimamente!", ephemeral=True)


class Anonymous(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(AnonPanelView())

    anon_admin = app_commands.Group(
        name="anon-admin",
        description="Configurar o sistema de mensagens anônimas",
        default_permissions=discord.Permissions(administrator=True),
    )

    @anon_admin.command(
        name="configurar",
        description="Define o canal do menu (botão) e o canal onde o GIF será postado",
    )
    @app_commands.describe(
        canal_menu="Canal onde ficará o painel com o botão de envio",
        canal_envio="Canal onde as mensagens aparecem como GIF",
        canal_log="Canal de log para moderadores (opcional)",
    )
    async def configurar(
        self,
        interaction: discord.Interaction,
        canal_menu: discord.TextChannel,
        canal_envio: discord.TextChannel,
        canal_log: discord.TextChannel | None = None,
    ) -> None:
        me = interaction.guild.me if interaction.guild else None
        if me:
            perms_menu = canal_menu.permissions_for(me)
            perms_envio = canal_envio.permissions_for(me)
            if not (perms_menu.send_messages and perms_menu.embed_links and perms_menu.attach_files):
                await interaction.response.send_message(
                    "❌ Preciso de permissão para enviar mensagens, embeds e anexos no **canal de menu**.",
                    ephemeral=True,
                )
                return
            if not (perms_envio.send_messages and perms_envio.attach_files):
                await interaction.response.send_message(
                    "❌ Preciso de permissão para enviar mensagens e anexos no **canal de envio**.",
                    ephemeral=True,
                )
                return

        await interaction.response.defer(ephemeral=True)

        log_id = canal_log.id if canal_log else 0
        old = await self.bot.db.get_anon_config(interaction.guild_id)

        if old:
            bid = int(old.get("button_message_id") or 0)
            if bid:
                old_menu = int(old.get("menu_channel_id") or old["channel_id"])
                oc = interaction.guild.get_channel(old_menu) if interaction.guild else None
                if isinstance(oc, discord.TextChannel):
                    try:
                        msg = await oc.fetch_message(bid)
                        await msg.delete()
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        pass

        await self.bot.db.set_anon_config(
            interaction.guild_id,
            canal_envio.id,
            canal_menu.id,
            log_id,
        )

        embed = discord.Embed(
            title="💌 Mensagens anônimas",
            description=(
                "Clique no botão abaixo para escrever sua mensagem. "
                "Ela será publicada **anonimamente** no canal de envio, em forma de **GIF** com o texto."
            ),
            color=BOT_COLOR,
        )
        embed.set_footer(text="Sem comandos — só use o botão neste canal.")

        view = AnonPanelView()
        try:
            msg = await canal_menu.send(embed=embed, view=view)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Sem permissão para enviar no **canal de menu**.", ephemeral=True
            )
            return
        except discord.HTTPException:
            await interaction.followup.send(
                "❌ Falha ao publicar o painel. Tente de novo.", ephemeral=True
            )
            return

        await self.bot.db.update_anon_button_message(interaction.guild_id, msg.id)

        lines = [
            f"✅ **Menu:** {canal_menu.mention}",
            f"✅ **Envio (GIF):** {canal_envio.mention}",
        ]
        if canal_log:
            lines.append(f"📋 **Log:** {canal_log.mention}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @anon_admin.command(name="ativar", description="Ativar ou desativar mensagens anônimas")
    @app_commands.describe(ativo="True para ativar, False para desativar")
    async def toggle(self, interaction: discord.Interaction, ativo: bool) -> None:
        cfg = await self.bot.db.get_anon_config(interaction.guild_id)
        if not cfg:
            await interaction.response.send_message(
                "❌ Configure primeiro com `/anon-admin configurar`.",
                ephemeral=True,
            )
            return
        await self.bot.db.toggle_anon(interaction.guild_id, ativo)
        status = "ativadas ✅" if ativo else "desativadas ❌"
        await interaction.response.send_message(f"Mensagens anônimas {status}.", ephemeral=True)

    @anon_admin.command(
        name="status",
        description="Ver configuração atual do sistema anônimo",
    )
    async def status(self, interaction: discord.Interaction) -> None:
        cfg = await self.bot.db.get_anon_config(interaction.guild_id)
        if not cfg:
            await interaction.response.send_message("❌ Sistema não configurado.", ephemeral=True)
            return

        out_ch = interaction.guild.get_channel(int(cfg["channel_id"]))
        menu_ch = interaction.guild.get_channel(int(cfg.get("menu_channel_id") or cfg["channel_id"]))
        log_ch = interaction.guild.get_channel(int(cfg.get("log_channel_id") or 0))

        embed = discord.Embed(title="💬 Sistema anônimo — status", color=BOT_COLOR)
        embed.add_field(
            name="Status",
            value="✅ Ativo" if cfg.get("enabled") else "❌ Inativo",
            inline=True,
        )
        embed.add_field(
            name="Canal de menu",
            value=menu_ch.mention if menu_ch else "❌ Não encontrado",
            inline=True,
        )
        embed.add_field(
            name="Canal de envio",
            value=out_ch.mention if out_ch else "❌ Não encontrado",
            inline=True,
        )
        embed.add_field(
            name="Log",
            value=log_ch.mention if log_ch else "Não configurado",
            inline=True,
        )
        embed.add_field(
            name="Formato",
            value="GIF + texto (fundo flores/anime em `ANON_LOVE_GIF_URL`)",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Anonymous(bot))
