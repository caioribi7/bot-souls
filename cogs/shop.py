"""
cogs/shop.py — Loja de Cargos + Mercado de Cargos
Discord.py 2.x, slash commands, Portuguese.
Currency: Sweet Coins 🍬
"""
from __future__ import annotations

import io
import logging
import re
from typing import TYPE_CHECKING

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
from utils.card_generator import generate_shop_card

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

SWEET_COIN = "🍬"
MAX_ITEMS_PER_PAGE = 20
MAX_LISTINGS_PER_USER = 3
HEX_RE = re.compile(r"^#?([0-9A-Fa-f]{6})$")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_color(raw: str) -> discord.Color | None:
    m = HEX_RE.match(raw.strip())
    if not m:
        return None
    return discord.Color(int(m.group(1), 16))


def _truncate(text: str, n: int = 100) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


# ── Image + Embed builders ───────────────────────────────────────────────────

async def _build_shop_image(
    guild: discord.Guild,
    items: list[dict],
    shop_config: dict,
) -> io.BytesIO:
    icon_url = str(guild.icon.url) if guild.icon else ""
    custom_price = shop_config.get("custom_role_price", 5000)
    return await generate_shop_card(
        guild_name=guild.name,
        guild_icon_url=icon_url,
        items=items,
        custom_role_price=custom_price,
    )


def _shop_embed_for_image() -> discord.Embed:
    """Minimal embed that displays the attached shop image."""
    embed = discord.Embed(color=GOLD_COLOR)
    embed.set_image(url="attachment://loja.png")
    embed.set_footer(text="Use os botões abaixo para comprar · Sweet Coins 🍬")
    return embed


async def _build_market_embed(
    guild: discord.Guild,
    listings: list[dict],
) -> discord.Embed:
    embed = discord.Embed(
        title="🔄 Mercado de Cargos",
        color=BOT_COLOR,
    )
    if not listings:
        embed.description = "Nenhum cargo à venda no momento."
        return embed

    lines: list[str] = []
    for listing in listings:
        role = guild.get_role(listing["role_id"])
        role_str = role.mention if role else "`cargo removido`"
        seller = guild.get_member(listing["seller_id"])
        seller_str = seller.mention if seller else f"`id:{listing['seller_id']}`"
        lines.append(
            f"**#{listing['id']}** {role_str} — `{listing['price']:,}` {SWEET_COIN} — {seller_str}"
        )

    embed.description = "\n".join(lines)
    embed.set_footer(text="Clique em 'Comprar' nos botões abaixo")
    return embed


# ── Confirm View ─────────────────────────────────────────────────────────────

class BuyConfirmView(discord.ui.View):
    """Ephemeral yes/no confirmation — uses only the button's own interaction."""

    def __init__(self, label: str):
        super().__init__(timeout=60)
        self.confirmed: bool = False

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        for child in self.children:
            child.disabled = True  # type: ignore[union-attr]
        await interaction.response.edit_message(
            content="⏳ Processando sua compra…", embed=None, view=self
        )
        self.stop()

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        for child in self.children:
            child.disabled = True  # type: ignore[union-attr]
        await interaction.response.edit_message(
            content="🚫 Compra cancelada.", embed=None, view=self
        )
        self.stop()


# ── Custom Role Modal ─────────────────────────────────────────────────────────

class CustomRoleModal(discord.ui.Modal, title="✨ Criar Cargo Personalizado"):
    nome = discord.ui.TextInput(
        label="Nome do cargo",
        placeholder="Ex: VIP Supremo",
        max_length=32,
        required=True,
    )
    cor = discord.ui.TextInput(
        label="Cor do cargo (hex, opcional)",
        placeholder="#99AAB5",
        max_length=7,
        required=False,
        default="#99AAB5",
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        db = self.bot.db
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("Use o modal dentro de um servidor.", ephemeral=True)
            return

        member = interaction.member
        if member is None:
            try:
                member = await guild.fetch_member(interaction.user.id)
            except discord.HTTPException:
                member = None
        if member is None:
            await interaction.followup.send("❌ Não consegui obter seu membro neste servidor.", ephemeral=True)
            return

        shop_config = await db.get_shop_config(guild.id)
        custom_price = shop_config.get("custom_role_price", 5000)

        role_name = self.nome.value.strip()
        if not role_name:
            await interaction.followup.send("❌ Nome do cargo não pode ser vazio.", ephemeral=True)
            return

        raw_cor = (self.cor.value or "#99AAB5").strip()
        if not raw_cor.startswith("#"):
            raw_cor = "#" + raw_cor
        color = _parse_color(raw_cor)
        if color is None:
            await interaction.followup.send(
                "❌ Cor inválida. Use o formato `#RRGGBB`, ex: `#FF5733`.", ephemeral=True
            )
            return

        success = await db.deduct_coins(member.id, guild.id, custom_price)
        if not success:
            user = await db.get_user(member.id, guild.id)
            await interaction.followup.send(
                f"❌ Saldo insuficiente. Você tem `{user['balance']:,}` {SWEET_COIN}, "
                f"mas o cargo personalizado custa `{custom_price:,}` {SWEET_COIN}.",
                ephemeral=True,
            )
            return

        try:
            created_role = await guild.create_role(
                name=role_name,
                color=color,
                mentionable=False,
                reason=f"Cargo personalizado por {member} via loja",
            )
        except discord.Forbidden:
            await db.add_coins(member.id, guild.id, custom_price)
            await interaction.followup.send(
                "❌ Não tenho permissão para criar cargos. Suas moedas foram devolvidas.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            await db.add_coins(member.id, guild.id, custom_price)
            await interaction.followup.send(
                f"❌ Erro ao criar cargo: {exc}. Suas moedas foram devolvidas.", ephemeral=True
            )
            return

        try:
            await member.add_roles(created_role, reason="Cargo personalizado — loja")
        except discord.Forbidden:
            pass

        item_id = await db.add_shop_item(
            guild.id, created_role.id, role_name,
            price=0,
            description=f"Cargo personalizado de {member.display_name}",
            emoji="✨",
            is_custom=True,
            xp_multiplier=1.0,
        )
        ok_own = await db.buy_item(member.id, guild.id, item_id, price=0)
        if not ok_own:
            await db.remove_shop_item(item_id, guild.id)
            try:
                await created_role.delete(reason="Falha ao registrar compra personalizada")
            except (discord.Forbidden, discord.HTTPException):
                pass
            await db.add_coins(member.id, guild.id, custom_price)
            await interaction.followup.send(
                "❌ Não foi possível registrar o cargo. Moedas devolvidas.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="✨ Cargo criado com sucesso!",
            description=(
                f"Seu cargo {created_role.mention} foi criado e concedido!\n\n"
                f"**Nome:** {role_name}\n"
                f"**Cor:** `{raw_cor.upper()}`\n"
                f"**Custo:** `{custom_price:,}` {SWEET_COIN}"
            ),
            color=color,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        cog = self.bot.cogs.get("Shop")
        if cog:
            await cog._refresh_shop_panel(guild)


# ── Shop Panel View ───────────────────────────────────────────────────────────

class ShopPanelView(discord.ui.View):
    """Persistent view attached to the shop panel message."""

    def __init__(
        self,
        bot: commands.Bot,
        guild_id: int,
        items: list[dict],
        shop_config: dict,
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self._build(items, shop_config)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message(
                "Este painel pertence a outro servidor.", ephemeral=True
            )
            return False
        return True

    def _build(self, items: list[dict], shop_config: dict):
        while self.children:
            self.remove_item(self.children[0])

        gid = self.guild_id
        regular = [i for i in items if not i.get("is_custom")]

        for item in regular[:MAX_ITEMS_PER_PAGE - 1]:
            emoji_str = item.get("emoji") or "🎭"
            label = _truncate(f"{emoji_str} {item['name']} — {item['price']:,}{SWEET_COIN}", 80)
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                custom_id=f"sb:{gid}:{item['id']}",
            )
            btn.callback = self._make_item_callback(item["id"])
            self.add_item(btn)

        custom_price = shop_config.get("custom_role_price", 5000)
        create_btn = discord.ui.Button(
            label=f"✨ Criar Cargo — {custom_price:,}{SWEET_COIN}",
            style=discord.ButtonStyle.primary,
            custom_id=f"scr:{gid}",
        )
        create_btn.callback = self._create_role_callback
        self.add_item(create_btn)

    def _make_item_callback(self, item_id: int):
        async def callback(interaction: discord.Interaction):
            await self._handle_buy_item(interaction, item_id)
        return callback

    async def _handle_buy_item(self, interaction: discord.Interaction, item_id: int):
        db = self.bot.db
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Use a loja dentro de um servidor.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            member = interaction.member
            if member is None:
                try:
                    member = await guild.fetch_member(interaction.user.id)
                except discord.HTTPException:
                    member = None
            if member is None:
                await interaction.followup.send(
                    "❌ Não consegui obter seu membro. Tente de novo.", ephemeral=True
                )
                return

            item = await db.get_shop_item(item_id)
            if not item or item["guild_id"] != guild.id:
                await interaction.followup.send(
                    "❌ Este item não está mais disponível.", ephemeral=True
                )
                return

            role = guild.get_role(item["role_id"])
            if not role:
                await interaction.followup.send(
                    "❌ O cargo deste item foi removido do servidor. Avise um administrador.",
                    ephemeral=True,
                )
                return

            if role in member.roles:
                await interaction.followup.send(
                    f"❌ Você já possui o cargo **{item['name']}**.", ephemeral=True
                )
                return

            if await db.has_purchased(member.id, guild.id, item_id):
                await interaction.followup.send(
                    f"❌ Você já comprou **{item['name']}**.", ephemeral=True
                )
                return

            user = await db.get_user(member.id, guild.id)
            price = item["price"]
            if user["balance"] < price:
                await interaction.followup.send(
                    f"❌ Saldo insuficiente! Você tem `{user['balance']:,}` {SWEET_COIN}, "
                    f"mas **{item['name']}** custa `{price:,}` {SWEET_COIN}.",
                    ephemeral=True,
                )
                return

            emoji_str = item.get("emoji") or "🎭"
            confirm_embed = discord.Embed(
                title="🛒 Confirmar compra",
                description=(
                    f"{emoji_str} **{item['name']}**\n"
                    f"Preço: `{price:,}` {SWEET_COIN}\n"
                    f"Saldo após compra: `{user['balance'] - price:,}` {SWEET_COIN}"
                ),
                color=WARNING_COLOR,
            )
            confirm_view = BuyConfirmView(label=item["name"])
            await interaction.followup.send(
                embed=confirm_embed, view=confirm_view, ephemeral=True
            )
            await confirm_view.wait()

            if not confirm_view.confirmed:
                return

            ok_buy = await db.buy_item(member.id, guild.id, item_id, price)
            if not ok_buy:
                await interaction.followup.send(
                    "❌ Não foi possível concluir a compra (saldo insuficiente ou item já comprado).",
                    ephemeral=True,
                )
                return

            try:
                await member.add_roles(role, reason=f"Compra na loja: {item['name']}")
            except discord.Forbidden:
                await db.remove_shop_purchase(member.id, guild.id, item_id)
                await db.add_coins(member.id, guild.id, price)
                await interaction.followup.send(
                    "❌ Não tenho permissão para conceder esse cargo. Suas moedas foram devolvidas.",
                    ephemeral=True,
                )
                return

            bal_now = (await db.get_user(member.id, guild.id))["balance"]
            success_embed = discord.Embed(
                title="✅ Compra realizada!",
                description=(
                    f"Você adquiriu {emoji_str} **{item['name']}** e recebeu {role.mention}!\n"
                    f"Saldo restante: `{bal_now:,}` {SWEET_COIN}"
                ),
                color=SUCCESS_COLOR,
            )
            await interaction.followup.send(embed=success_embed, ephemeral=True)

        except discord.HTTPException as exc:
            log.warning("Erro HTTP na compra da loja: %s", exc)
            try:
                await interaction.followup.send(
                    "❌ Falha ao falar com o Discord. Tente de novo.", ephemeral=True
                )
            except discord.HTTPException:
                pass
        except Exception:
            log.exception("Erro inesperado na compra da loja")
            try:
                await interaction.followup.send(
                    "❌ Erro ao processar. Tente de novo ou avise a staff.", ephemeral=True
                )
            except discord.HTTPException:
                pass

    async def _create_role_callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Use a loja dentro de um servidor.", ephemeral=True
            )
            return
        await interaction.response.send_modal(CustomRoleModal(self.bot))


# ── Market View ───────────────────────────────────────────────────────────────

class MarketView(discord.ui.View):
    """Persistent view for the role market panel."""

    def __init__(self, bot: commands.Bot, guild_id: int, listings: list[dict]):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self._build(listings)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message(
                "Este mercado pertence a outro servidor.", ephemeral=True
            )
            return False
        return True

    def _build(self, listings: list[dict]):
        while self.children:
            self.remove_item(self.children[0])

        gid = self.guild_id
        for listing in listings[:20]:
            lid = listing["id"]
            price = listing["price"]
            label = _truncate(f"Comprar #{lid} — {price:,}{SWEET_COIN}", 80)
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.success,
                custom_id=f"mb:{gid}:{lid}",
            )
            btn.callback = self._make_buy_callback(lid)
            self.add_item(btn)

        if not listings:
            placeholder = discord.ui.Button(
                label="Sem itens no mercado",
                style=discord.ButtonStyle.secondary,
                custom_id=f"me:{gid}",
                disabled=True,
            )
            self.add_item(placeholder)

    def _make_buy_callback(self, listing_id: int):
        async def callback(interaction: discord.Interaction):
            await self._handle_market_buy(interaction, listing_id)
        return callback

    async def _handle_market_buy(self, interaction: discord.Interaction, listing_id: int):
        db = self.bot.db
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Use o mercado dentro de um servidor.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        buyer_id = interaction.user.id

        try:
            listing = await db.get_role_listing(listing_id)
            if not listing or listing["guild_id"] != guild.id:
                await interaction.followup.send("❌ Este anúncio não existe mais.", ephemeral=True)
                return

            if listing["seller_id"] == buyer_id:
                await interaction.followup.send(
                    "❌ Você não pode comprar seu próprio anúncio.", ephemeral=True
                )
                return

            role = guild.get_role(listing["role_id"])
            if not role:
                await interaction.followup.send(
                    "❌ O cargo deste anúncio foi removido do servidor.", ephemeral=True
                )
                return

            price = listing["price"]
            user = await db.get_user(buyer_id, guild.id)
            if user["balance"] < price:
                await interaction.followup.send(
                    f"❌ Saldo insuficiente! Você tem `{user['balance']:,}` {SWEET_COIN}, "
                    f"mas este cargo custa `{price:,}` {SWEET_COIN}.",
                    ephemeral=True,
                )
                return

            seller = guild.get_member(listing["seller_id"])
            seller_str = seller.mention if seller else f"`id:{listing['seller_id']}`"

            confirm_embed = discord.Embed(
                title="🛒 Confirmar compra no mercado",
                description=(
                    f"Cargo: {role.mention}\n"
                    f"Vendedor: {seller_str}\n"
                    f"Preço: `{price:,}` {SWEET_COIN}\n"
                    f"Saldo após compra: `{user['balance'] - price:,}` {SWEET_COIN}"
                ),
                color=WARNING_COLOR,
            )
            confirm_view = BuyConfirmView(label=role.name)
            await interaction.followup.send(
                embed=confirm_embed, view=confirm_view, ephemeral=True
            )
            await confirm_view.wait()

            if not confirm_view.confirmed:
                return

            # Re-fetch to guard race conditions
            listing = await db.get_role_listing(listing_id)
            if not listing:
                await interaction.followup.send(
                    "❌ Este anúncio já foi comprado por outra pessoa.", ephemeral=True
                )
                return

            buyer_member = interaction.member
            if buyer_member is None:
                try:
                    buyer_member = await guild.fetch_member(buyer_id)
                except discord.HTTPException:
                    buyer_member = None
            if buyer_member is None:
                await interaction.followup.send(
                    "❌ Não consegui obter seu membro neste servidor.", ephemeral=True
                )
                return

            seller_member = guild.get_member(listing["seller_id"])
            if seller_member is None:
                try:
                    seller_member = await guild.fetch_member(listing["seller_id"])
                except discord.HTTPException:
                    seller_member = None

            ok = await db.deduct_coins(buyer_id, guild.id, price)
            if not ok:
                await interaction.followup.send(
                    "❌ Saldo insuficiente no momento da confirmação.", ephemeral=True
                )
                return

            seller_removed = False
            if seller_member:
                try:
                    await seller_member.remove_roles(
                        role, reason=f"Venda no mercado para {buyer_member.display_name}"
                    )
                    seller_removed = True
                except (discord.Forbidden, discord.HTTPException):
                    await db.add_coins(buyer_id, guild.id, price)
                    await interaction.followup.send(
                        "❌ Não consegui remover o cargo do vendedor. Verifique a hierarquia do bot.",
                        ephemeral=True,
                    )
                    return

            try:
                await buyer_member.add_roles(
                    role, reason=f"Compra no mercado de {seller_str}"
                )
            except discord.Forbidden:
                await db.add_coins(buyer_id, guild.id, price)
                if seller_member and seller_removed:
                    try:
                        await seller_member.add_roles(role, reason="Revertendo mercado")
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                await interaction.followup.send(
                    "❌ Não tenho permissão para conceder esse cargo. Moedas devolvidas.",
                    ephemeral=True,
                )
                return

            await db.add_coins(listing["seller_id"], guild.id, price)
            await db.remove_role_listing(listing_id)

            success_embed = discord.Embed(
                title="✅ Compra realizada!",
                description=(
                    f"Você adquiriu {role.mention} de {seller_str} "
                    f"por `{price:,}` {SWEET_COIN}!"
                ),
                color=SUCCESS_COLOR,
            )
            await interaction.followup.send(embed=success_embed, ephemeral=True)

            cog = self.bot.cogs.get("Shop")
            if cog:
                await cog._refresh_market_panel(guild)

        except discord.HTTPException as exc:
            log.warning("Erro HTTP na compra do mercado: %s", exc)
            try:
                await interaction.followup.send(
                    "❌ Falha ao falar com o Discord. Tente de novo.", ephemeral=True
                )
            except discord.HTTPException:
                pass
        except Exception:
            log.exception("Erro inesperado na compra do mercado")
            try:
                await interaction.followup.send(
                    "❌ Erro ao processar. Tente de novo ou avise a staff.", ephemeral=True
                )
            except discord.HTTPException:
                pass


# ── Shop Cog ──────────────────────────────────────────────────────────────────

class Shop(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        for guild in self.bot.guilds:
            try:
                await self._register_persistent_views(guild)
            except Exception as exc:
                log.warning("Persistent views failed for guild %s: %s", guild.id, exc)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        """Handle legacy custom_id formats from old panels."""
        if interaction.type != discord.InteractionType.component:
            return

        data = interaction.data
        cid = (
            data.get("custom_id")
            if isinstance(data, dict)
            else getattr(data, "custom_id", None)
        )
        if not cid:
            return

        # New-format ids are handled by the registered persistent views
        if cid.startswith(("sb:", "scr:", "mb:", "me:")):
            return

        if interaction.response.is_done():
            return

        gid = interaction.guild_id
        if gid is None:
            return

        db = self.bot.db
        try:
            if cid.startswith("shop_buy_"):
                try:
                    item_id = int(cid.split("shop_buy_", 1)[1])
                except ValueError:
                    return
                items = await db.get_shop(gid)
                cfg = await db.get_shop_config(gid)
                view = ShopPanelView(self.bot, gid, items, cfg)
                await view._handle_buy_item(interaction, item_id)
                return

            if cid == "shop_create_role":
                await ShopPanelView(self.bot, gid, [], {})._create_role_callback(interaction)
                return

            if cid.startswith("market_buy_"):
                try:
                    listing_id = int(cid.split("market_buy_", 1)[1])
                except ValueError:
                    return
                listings = await db.get_role_listings(gid)
                mv = MarketView(self.bot, gid, listings)
                await mv._handle_market_buy(interaction, listing_id)
                return

            if cid == "market_empty":
                await interaction.response.defer(ephemeral=True)
                return
        except Exception:
            log.exception("Falha no handler legacy da loja")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Erro ao processar. Peça para um admin republicar a loja.",
                        ephemeral=True,
                    )
            except discord.HTTPException:
                pass

    # ── Persistent View Registration ──────────────────────────────────────────

    async def _register_persistent_views(self, guild: discord.Guild):
        db = self.bot.db
        items = await db.get_shop(guild.id)
        shop_config = await db.get_shop_config(guild.id)
        listings = await db.get_role_listings(guild.id)

        shop_view = ShopPanelView(self.bot, guild.id, items, shop_config)
        market_view = MarketView(self.bot, guild.id, listings)

        self.bot.add_view(shop_view)
        self.bot.add_view(market_view)

    # ── Panel helpers ─────────────────────────────────────────────────────────

    async def _post_shop_panel(
        self, channel: discord.TextChannel, guild: discord.Guild,
        items: list[dict], shop_config: dict,
    ) -> discord.Message:
        """Send a brand-new shop panel (image + buttons)."""
        view = ShopPanelView(self.bot, guild.id, items, shop_config)
        self.bot.add_view(view)

        try:
            buf = await _build_shop_image(guild, items, shop_config)
            embed = _shop_embed_for_image()
            file = discord.File(buf, filename="loja.png")
            return await channel.send(file=file, embed=embed, view=view)
        except Exception as exc:
            log.warning("Falha ao gerar imagem da loja, usando embed texto: %s", exc)
            embed = await _build_text_shop_embed(guild, items, shop_config)
            return await channel.send(embed=embed, view=view)

    async def _refresh_shop_panel(self, guild: discord.Guild):
        """Delete old shop panel and post a new one."""
        db = self.bot.db
        shop_config = await db.get_shop_config(guild.id)
        items = await db.get_shop(guild.id)

        channel_id = shop_config.get("channel_id") or 0
        message_id = shop_config.get("message_id") or 0

        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        # Delete old message
        if message_id:
            try:
                old = await channel.fetch_message(message_id)
                await old.delete()
            except (discord.NotFound, discord.HTTPException):
                pass

        try:
            msg = await self._post_shop_panel(channel, guild, items, shop_config)
            await db.set_shop_config(guild.id, message_id=msg.id)
        except discord.Forbidden:
            log.warning("No permission to post shop panel in guild %s", guild.id)

    async def _refresh_market_panel(self, guild: discord.Guild):
        """Edit or re-post market panel."""
        db = self.bot.db
        shop_config = await db.get_shop_config(guild.id)
        listings = await db.get_role_listings(guild.id)

        channel_id = shop_config.get("channel_id") or 0
        market_msg_id = shop_config.get("market_message_id") or 0

        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        embed = await _build_market_embed(guild, listings)
        view = MarketView(self.bot, guild.id, listings)
        self.bot.add_view(view)

        if market_msg_id:
            try:
                msg = await channel.fetch_message(market_msg_id)
                await msg.edit(embed=embed, view=view)
                return
            except (discord.NotFound, discord.HTTPException):
                pass

        try:
            msg = await channel.send(embed=embed, view=view)
            await db.set_shop_config(guild.id, market_message_id=msg.id)
        except discord.Forbidden:
            log.warning("No permission to post market panel in guild %s", guild.id)

    # ════════════════════════════════════════════════════════════════════════
    # /loja-admin group
    # ════════════════════════════════════════════════════════════════════════

    loja_admin = app_commands.Group(
        name="loja-admin",
        description="Gerenciar a loja de cargos",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @loja_admin.command(
        name="configurar-canal",
        description="Configura o canal da loja e publica o painel visual",
    )
    @app_commands.describe(canal="Canal onde o painel da loja será publicado")
    async def admin_set_channel(
        self, interaction: discord.Interaction, canal: discord.TextChannel
    ):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db
        guild = interaction.guild

        shop_config = await db.get_shop_config(guild.id)
        old_channel_id = shop_config.get("channel_id") or 0
        old_msg_id = shop_config.get("message_id") or 0
        old_market_msg_id = shop_config.get("market_message_id") or 0

        if old_channel_id:
            old_ch = guild.get_channel(old_channel_id)
            if isinstance(old_ch, discord.TextChannel):
                for mid in [old_msg_id, old_market_msg_id]:
                    if mid:
                        try:
                            old_m = await old_ch.fetch_message(mid)
                            await old_m.delete()
                        except (discord.NotFound, discord.HTTPException):
                            pass

        await db.set_shop_config(guild.id, channel_id=canal.id, message_id=0, market_message_id=0)

        items = await db.get_shop(guild.id)
        shop_config = await db.get_shop_config(guild.id)

        try:
            shop_msg = await self._post_shop_panel(canal, guild, items, shop_config)
            await db.set_shop_config(guild.id, message_id=shop_msg.id)
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ Não tenho permissão para enviar mensagens em {canal.mention}.",
                ephemeral=True,
            )
            return

        listings = await db.get_role_listings(guild.id)
        market_embed = await _build_market_embed(guild, listings)
        market_view = MarketView(self.bot, guild.id, listings)
        self.bot.add_view(market_view)

        market_msg = await canal.send(embed=market_embed, view=market_view)
        await db.set_shop_config(guild.id, market_message_id=market_msg.id)

        embed = discord.Embed(
            title="✅ Canal configurado",
            description=f"Painel da loja publicado em {canal.mention}.",
            color=SUCCESS_COLOR,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @loja_admin.command(
        name="configurar",
        description="Alias de configurar-canal",
    )
    @app_commands.describe(canal="Canal onde o painel da loja será publicado")
    async def admin_set_channel_alias(
        self, interaction: discord.Interaction, canal: discord.TextChannel
    ):
        await self.admin_set_channel(interaction, canal)

    @loja_admin.command(
        name="adicionar",
        description="Adicionar um cargo à loja",
    )
    @app_commands.describe(
        cargo="Cargo a ser vendido",
        nome="Nome do item na loja",
        preco="Preço em Sweet Coins",
        descricao="Descrição curta do item",
        emoji="Emoji representativo",
        multiplicador_xp="Boost de XP (1.0 = nenhum, máx 3.0)",
    )
    async def admin_add_item(
        self,
        interaction: discord.Interaction,
        cargo: discord.Role,
        nome: str,
        preco: int,
        descricao: str = "",
        emoji: str = "🎭",
        multiplicador_xp: float = 1.0,
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        if preco <= 0:
            await interaction.followup.send("❌ O preço deve ser maior que zero.", ephemeral=True)
            return

        if not (1.0 <= multiplicador_xp <= 3.0):
            await interaction.followup.send(
                "❌ O multiplicador de XP deve estar entre `1.0` e `3.0`.", ephemeral=True
            )
            return

        if cargo.is_default() or cargo.managed:
            await interaction.followup.send(
                "❌ Não é possível vender o @everyone nem cargos gerenciados.", ephemeral=True
            )
            return

        db = self.bot.db
        item_id = await db.add_shop_item(
            guild.id, cargo.id, nome, preco, descricao, emoji,
            is_custom=False, xp_multiplier=multiplicador_xp,
        )

        if multiplicador_xp > 1.0:
            await db.set_xp_boost_role(guild.id, cargo.id, multiplicador_xp)

        embed = discord.Embed(
            title="✅ Item adicionado",
            description=(
                f"{emoji} **{nome}** adicionado à loja.\n"
                f"ID: `{item_id}` | Preço: `{preco:,}` {SWEET_COIN}"
            ),
            color=SUCCESS_COLOR,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        await self._refresh_shop_panel(guild)

    @loja_admin.command(
        name="remover",
        description="Remover um cargo da loja pelo ID",
    )
    @app_commands.describe(id_item="ID do item (veja em /loja)")
    async def admin_remove_item(self, interaction: discord.Interaction, id_item: int):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db
        guild = interaction.guild

        item = await db.get_shop_item(id_item)
        if not item or item["guild_id"] != guild.id:
            await interaction.followup.send("❌ Item não encontrado.", ephemeral=True)
            return

        await db.remove_shop_item(id_item, guild.id)
        await interaction.followup.send(
            f"✅ Item **{item['name']}** (ID `{id_item}`) removido.", ephemeral=True
        )
        await self._refresh_shop_panel(guild)

    @loja_admin.command(name="dar-moedas", description="Dar Sweet Coins a um membro")
    @app_commands.describe(membro="Membro que receberá as moedas", valor="Quantidade de 🍬")
    async def admin_give_coins(
        self, interaction: discord.Interaction, membro: discord.Member, valor: int
    ):
        if valor <= 0:
            await interaction.response.send_message("❌ O valor deve ser positivo.", ephemeral=True)
            return
        await self.bot.db.add_coins(membro.id, interaction.guild_id, valor)
        await interaction.response.send_message(
            f"✅ `+{valor:,}` {SWEET_COIN} adicionados para {membro.mention}.", ephemeral=True
        )

    @loja_admin.command(
        name="criar-cargo-preco",
        description="Define o preço do cargo personalizado",
    )
    @app_commands.describe(valor="Preço em Sweet Coins")
    async def admin_set_custom_price(self, interaction: discord.Interaction, valor: int):
        if valor <= 0:
            await interaction.response.send_message("❌ O preço deve ser positivo.", ephemeral=True)
            return
        await self.bot.db.set_shop_config(interaction.guild_id, custom_role_price=valor)
        await interaction.response.send_message(
            f"✅ Preço do cargo personalizado: `{valor:,}` {SWEET_COIN}.", ephemeral=True
        )
        await self._refresh_shop_panel(interaction.guild)

    @loja_admin.command(name="boost-xp", description="Define o multiplicador de XP de um cargo")
    @app_commands.describe(cargo="Cargo", multiplicador="Multiplicador (1.0–3.0)")
    async def admin_boost_xp(
        self, interaction: discord.Interaction, cargo: discord.Role, multiplicador: float
    ):
        if not (1.0 <= multiplicador <= 3.0):
            await interaction.response.send_message(
                "❌ Multiplicador entre `1.0` e `3.0`.", ephemeral=True
            )
            return
        await self.bot.db.set_xp_boost_role(interaction.guild_id, cargo.id, multiplicador)
        await interaction.response.send_message(
            f"✅ Boost de XP de {cargo.mention}: **{multiplicador:.1f}x**.", ephemeral=True
        )

    @loja_admin.command(name="remover-boost", description="Remove o multiplicador de XP de um cargo")
    @app_commands.describe(cargo="Cargo cujo boost será removido")
    async def admin_remove_boost(self, interaction: discord.Interaction, cargo: discord.Role):
        await self.bot.db.remove_xp_boost_role(interaction.guild_id, cargo.id)
        await interaction.response.send_message(
            f"✅ Boost de XP de {cargo.mention} removido.", ephemeral=True
        )

    @loja_admin.command(
        name="atualizar",
        description="Força a atualização visual do painel da loja",
    )
    async def admin_refresh(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self._refresh_shop_panel(interaction.guild)
        await self._refresh_market_panel(interaction.guild)
        await interaction.followup.send("✅ Painéis atualizados.", ephemeral=True)

    # ════════════════════════════════════════════════════════════════════════
    # /mercado group
    # ════════════════════════════════════════════════════════════════════════

    mercado = app_commands.Group(
        name="mercado",
        description="Mercado de cargos entre membros",
    )

    @mercado.command(name="listar", description="Listar seu cargo no mercado para venda")
    @app_commands.describe(cargo="Cargo que você quer vender", preco="Preço em Sweet Coins")
    async def market_list(
        self, interaction: discord.Interaction, cargo: discord.Role, preco: int
    ):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        member = interaction.user  # type: ignore[assignment]
        db = self.bot.db

        if preco <= 0:
            await interaction.followup.send("❌ O preço deve ser maior que zero.", ephemeral=True)
            return

        if cargo.is_default():
            await interaction.followup.send("❌ Não é possível listar o @everyone.", ephemeral=True)
            return

        if cargo.managed:
            await interaction.followup.send(
                "❌ Não é possível listar cargos gerenciados.", ephemeral=True
            )
            return

        if cargo not in member.roles:
            await interaction.followup.send(
                f"❌ Você não possui o cargo {cargo.mention}.", ephemeral=True
            )
            return

        existing = await db.get_user_listings(guild.id, member.id)
        if len(existing) >= MAX_LISTINGS_PER_USER:
            await interaction.followup.send(
                f"❌ Você já tem `{MAX_LISTINGS_PER_USER}` anúncios ativos.", ephemeral=True
            )
            return

        for lst in existing:
            if lst["role_id"] == cargo.id:
                await interaction.followup.send(
                    f"❌ Você já tem este cargo ({cargo.mention}) anunciado.", ephemeral=True
                )
                return

        listing_id = await db.add_role_listing(guild.id, member.id, cargo.id, preco)

        try:
            await member.remove_roles(cargo, reason="Cargo listado no mercado")
        except discord.Forbidden:
            await db.remove_role_listing(listing_id)
            await interaction.followup.send(
                "❌ Não tenho permissão para remover esse cargo de você.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📢 Cargo anunciado no mercado!",
            description=(
                f"Cargo: {cargo.mention}\n"
                f"Preço: `{preco:,}` {SWEET_COIN}\n"
                f"ID do anúncio: `{listing_id}`\n\n"
                "O cargo foi removido de você até ser comprado ou cancelado."
            ),
            color=SUCCESS_COLOR,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        await self._refresh_market_panel(guild)

    @mercado.command(name="cancelar", description="Cancelar seu anúncio e recuperar o cargo")
    @app_commands.describe(id_anuncio="ID do anúncio (veja em /mercado meus-anuncios)")
    async def market_cancel(self, interaction: discord.Interaction, id_anuncio: int):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db
        guild = interaction.guild
        member = interaction.user  # type: ignore[assignment]

        listing = await db.get_role_listing(id_anuncio)
        if not listing or listing["guild_id"] != guild.id:
            await interaction.followup.send("❌ Anúncio não encontrado.", ephemeral=True)
            return

        if listing["seller_id"] != member.id:
            await interaction.followup.send("❌ Este anúncio não é seu.", ephemeral=True)
            return

        role = guild.get_role(listing["role_id"])
        await db.remove_role_listing(id_anuncio)

        if role:
            try:
                await member.add_roles(role, reason="Anúncio de mercado cancelado")
            except discord.Forbidden:
                pass

        role_str = role.mention if role else "`cargo removido`"
        await interaction.followup.send(
            f"✅ Anúncio `#{id_anuncio}` cancelado. {role_str} devolvido a você.",
            ephemeral=True,
        )
        await self._refresh_market_panel(guild)

    @mercado.command(name="meus-anuncios", description="Ver seus anúncios ativos no mercado")
    async def market_my_listings(self, interaction: discord.Interaction):
        db = self.bot.db
        guild = interaction.guild
        member = interaction.user  # type: ignore[assignment]

        listings = await db.get_user_listings(guild.id, member.id)
        embed = discord.Embed(title="📋 Seus Anúncios no Mercado", color=BOT_COLOR)

        if not listings:
            embed.description = "Você não tem nenhum anúncio ativo."
        else:
            lines = []
            for lst in listings:
                role = guild.get_role(lst["role_id"])
                role_str = role.mention if role else "`cargo removido`"
                lines.append(f"**#{lst['id']}** {role_str} — `{lst['price']:,}` {SWEET_COIN}")
            embed.description = "\n".join(lines)
            embed.set_footer(text="Use /mercado cancelar <id> para cancelar")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @mercado.command(name="lista", description="Ver os cargos disponíveis no mercado")
    async def market_list_cmd(self, interaction: discord.Interaction):
        listings = await self.bot.db.get_role_listings(interaction.guild_id)
        embed = await _build_market_embed(interaction.guild, listings)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ════════════════════════════════════════════════════════════════════════
    # Standalone commands
    # ════════════════════════════════════════════════════════════════════════

    @app_commands.command(name="saldo", description="Ver o saldo de Sweet Coins de um membro")
    @app_commands.describe(membro="Membro (vazio = você mesmo)")
    async def balance(
        self, interaction: discord.Interaction, membro: discord.Member | None = None
    ):
        target = membro or interaction.user
        user = await self.bot.db.get_user(target.id, interaction.guild_id)
        embed = discord.Embed(
            title=f"{SWEET_COIN} Saldo de {target.display_name}",
            description=f"**`{user['balance']:,}`** Sweet Coins",
            color=GOLD_COLOR,
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="inventario", description="Ver os itens comprados na loja")
    @app_commands.describe(membro="Membro (vazio = você mesmo)")
    async def inventory(
        self, interaction: discord.Interaction, membro: discord.Member | None = None
    ):
        target = membro or interaction.user
        purchases = await self.bot.db.get_purchases(target.id, interaction.guild_id)

        embed = discord.Embed(title=f"🎒 Inventário de {target.display_name}", color=BOT_COLOR)
        embed.set_thumbnail(url=target.display_avatar.url)

        if not purchases:
            embed.description = "Nenhum item comprado ainda."
        else:
            lines = []
            for p in purchases:
                emoji_str = p.get("emoji") or "🎭"
                price_str = f"`{p['price']:,}` {SWEET_COIN}" if p["price"] else "*(cargo personalizado)*"
                role = interaction.guild.get_role(p["role_id"])
                role_str = role.mention if role else "*(cargo removido)*"
                lines.append(f"{emoji_str} **{p['name']}** — {role_str} — {price_str}")
            embed.description = "\n".join(lines)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="loja", description="Ver a loja de cargos (versão texto)")
    async def shop_cmd(self, interaction: discord.Interaction):
        db = self.bot.db
        guild = interaction.guild

        shop_config = await db.get_shop_config(guild.id)
        items = await db.get_shop(guild.id)

        embed = await _build_text_shop_embed(guild, items, shop_config)

        channel_id = shop_config.get("channel_id") or 0
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel:
                embed.add_field(
                    name="Canal da Loja",
                    value=f"Compre usando os botões em {channel.mention}!",
                    inline=False,
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)


# ── Text-only fallback embed (used by /loja and on PIL failure) ───────────────

async def _build_text_shop_embed(
    guild: discord.Guild,
    items: list[dict],
    shop_config: dict,
) -> discord.Embed:
    custom_role_price = shop_config.get("custom_role_price", 5000)
    embed = discord.Embed(
        title="🏪 Loja de Cargos",
        description=f"Use os botões no canal da loja para comprar com {SWEET_COIN} Sweet Coins!",
        color=GOLD_COLOR,
    )
    regular = [i for i in items if not i.get("is_custom")]
    if not regular:
        embed.add_field(name="Sem itens", value="Nenhum cargo à venda no momento.", inline=False)
    else:
        for item in regular[:MAX_ITEMS_PER_PAGE]:
            emoji_str = item.get("emoji") or "🎭"
            xp_mult = item.get("xp_multiplier", 1.0) or 1.0
            lines = [f"**Preço:** `{item['price']:,}` {SWEET_COIN}"]
            if item.get("description"):
                lines.append(f"*{_truncate(item['description'])}*")
            if xp_mult > 1.0:
                lines.append(f"⚡ Boost XP: **{xp_mult:.1f}x**")
            embed.add_field(name=f"{emoji_str} {item['name']}", value="\n".join(lines), inline=True)

    embed.add_field(
        name="✨ Criar Cargo Personalizado",
        value=f"**Preço:** `{custom_role_price:,}` {SWEET_COIN}\nCrie seu cargo com nome e cor!",
        inline=True,
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(Shop(bot))
