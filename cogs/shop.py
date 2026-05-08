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


# ── Confirm Views ─────────────────────────────────────────────────────────────

class BuyConfirmView(discord.ui.View):
    """Shop item purchase confirmation. All logic lives inside the confirm callback."""

    def __init__(self, bot: commands.Bot, member: discord.Member, guild: discord.Guild, item: dict):
        super().__init__(timeout=60)
        self.bot = bot
        self.member = member
        self.guild = guild
        self.item = item
        self._done = False

        uid, iid = member.id, item["id"]
        btn_ok = discord.ui.Button(
            label="✅ Confirmar", style=discord.ButtonStyle.success,
            custom_id=f"bcf:{uid}:{iid}",
        )
        btn_ok.callback = self._do_confirm
        self.add_item(btn_ok)

        btn_no = discord.ui.Button(
            label="❌ Cancelar", style=discord.ButtonStyle.danger,
            custom_id=f"bcc:{uid}:{iid}",
        )
        btn_no.callback = self._do_cancel
        self.add_item(btn_no)

    async def _do_confirm(self, interaction: discord.Interaction):
        if self._done:
            await interaction.response.defer()
            return
        self._done = True
        self.stop()
        for c in self.children:
            c.disabled = True  # type: ignore[union-attr]
        await interaction.response.edit_message(content="⏳ Processando…", embed=None, view=self)

        db = self.bot.db
        item = self.item
        member = self.member
        guild = self.guild
        price = item["price"]

        try:
            ok = await db.buy_item(member.id, guild.id, item["id"], price)
            if not ok:
                await interaction.edit_original_response(
                    content="❌ Compra falhou (saldo insuficiente ou item já comprado).",
                    embed=None, view=None,
                )
                return

            role = guild.get_role(item["role_id"])
            if role:
                try:
                    await member.add_roles(role, reason=f"Compra na loja: {item['name']}")
                except discord.Forbidden:
                    await db.remove_shop_purchase(member.id, guild.id, item["id"])
                    await db.add_coins(member.id, guild.id, price)
                    await interaction.edit_original_response(
                        content="❌ Sem permissão para conceder o cargo. Moedas devolvidas.",
                        embed=None, view=None,
                    )
                    return

            bal_now = (await db.get_user(member.id, guild.id))["balance"]
            emoji_str = item.get("emoji") or "🎭"
            role_mention = role.mention if role else ""
            success_embed = discord.Embed(
                title="✅ Compra realizada!",
                description=(
                    f"Você adquiriu {emoji_str} **{item['name']}**"
                    + (f" e recebeu {role_mention}!" if role_mention else "!")
                    + f"\nSaldo restante: `{bal_now:,}` {SWEET_COIN}"
                ),
                color=SUCCESS_COLOR,
            )
            await interaction.edit_original_response(content=None, embed=success_embed, view=None)

            cog = self.bot.cogs.get("Shop")
            if cog:
                await cog._refresh_shop_panel(guild)  # type: ignore[union-attr]

        except Exception:
            log.exception("Erro na compra da loja")
            try:
                await interaction.edit_original_response(
                    content="❌ Erro ao processar. Tente de novo.", embed=None, view=None,
                )
            except Exception:
                pass

    async def _do_cancel(self, interaction: discord.Interaction):
        if self._done:
            await interaction.response.defer()
            return
        self._done = True
        self.stop()
        for c in self.children:
            c.disabled = True  # type: ignore[union-attr]
        await interaction.response.edit_message(content="🚫 Compra cancelada.", embed=None, view=None)


class MarketBuyConfirmView(discord.ui.View):
    """Market listing purchase confirmation. All logic lives inside the confirm callback."""

    def __init__(
        self, bot: commands.Bot, buyer_member: discord.Member,
        guild: discord.Guild, listing: dict,
    ):
        super().__init__(timeout=60)
        self.bot = bot
        self.buyer_member = buyer_member
        self.guild = guild
        self.listing = listing
        self._done = False

        uid, lid = buyer_member.id, listing["id"]
        btn_ok = discord.ui.Button(
            label="✅ Confirmar", style=discord.ButtonStyle.success,
            custom_id=f"bcmf:{uid}:{lid}",
        )
        btn_ok.callback = self._do_confirm
        self.add_item(btn_ok)

        btn_no = discord.ui.Button(
            label="❌ Cancelar", style=discord.ButtonStyle.danger,
            custom_id=f"bcmc:{uid}:{lid}",
        )
        btn_no.callback = self._do_cancel
        self.add_item(btn_no)

    async def _do_confirm(self, interaction: discord.Interaction):
        if self._done:
            await interaction.response.defer()
            return
        self._done = True
        self.stop()
        for c in self.children:
            c.disabled = True  # type: ignore[union-attr]
        await interaction.response.edit_message(content="⏳ Processando…", embed=None, view=self)

        db = self.bot.db
        buyer = self.buyer_member
        guild = self.guild
        listing_id = self.listing["id"]

        try:
            # Re-fetch to guard race conditions
            listing = await db.get_role_listing(listing_id)
            if not listing:
                await interaction.edit_original_response(
                    content="❌ Este anúncio já foi comprado por outra pessoa.",
                    embed=None, view=None,
                )
                return

            role = guild.get_role(listing["role_id"])
            if not role:
                await interaction.edit_original_response(
                    content="❌ O cargo deste anúncio foi removido do servidor.",
                    embed=None, view=None,
                )
                return

            price = listing["price"]
            ok = await db.deduct_coins(buyer.id, guild.id, price)
            if not ok:
                await interaction.edit_original_response(
                    content="❌ Saldo insuficiente no momento da confirmação.",
                    embed=None, view=None,
                )
                return

            seller_member = guild.get_member(listing["seller_id"])
            if seller_member is None:
                try:
                    seller_member = await guild.fetch_member(listing["seller_id"])
                except discord.HTTPException:
                    seller_member = None

            if seller_member:
                try:
                    await seller_member.remove_roles(
                        role, reason=f"Venda no mercado para {buyer.display_name}"
                    )
                except (discord.Forbidden, discord.HTTPException):
                    await db.add_coins(buyer.id, guild.id, price)
                    await interaction.edit_original_response(
                        content="❌ Não consegui remover o cargo do vendedor. Verifique a hierarquia do bot.",
                        embed=None, view=None,
                    )
                    return

            try:
                await buyer.add_roles(role, reason="Compra no mercado")
            except discord.Forbidden:
                await db.add_coins(buyer.id, guild.id, price)
                if seller_member:
                    try:
                        await seller_member.add_roles(role, reason="Revertendo venda no mercado")
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                await interaction.edit_original_response(
                    content="❌ Sem permissão para conceder o cargo. Moedas devolvidas.",
                    embed=None, view=None,
                )
                return

            await db.add_coins(listing["seller_id"], guild.id, price)
            await db.remove_role_listing(listing_id)

            seller_str = seller_member.mention if seller_member else f"`id:{listing['seller_id']}`"
            success_embed = discord.Embed(
                title="✅ Compra realizada!",
                description=(
                    f"Você adquiriu {role.mention} de {seller_str} "
                    f"por `{price:,}` {SWEET_COIN}!"
                ),
                color=SUCCESS_COLOR,
            )
            await interaction.edit_original_response(content=None, embed=success_embed, view=None)

            cog = self.bot.cogs.get("Shop")
            if cog:
                await cog._refresh_market_panel(guild)  # type: ignore[union-attr]

        except Exception:
            log.exception("Erro na compra do mercado")
            try:
                await interaction.edit_original_response(
                    content="❌ Erro ao processar. Tente de novo.", embed=None, view=None,
                )
            except Exception:
                pass

    async def _do_cancel(self, interaction: discord.Interaction):
        if self._done:
            await interaction.response.defer()
            return
        self._done = True
        self.stop()
        for c in self.children:
            c.disabled = True  # type: ignore[union-attr]
        await interaction.response.edit_message(content="🚫 Compra cancelada.", embed=None, view=None)


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

        member = interaction.user
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


# ── Ephemeral Views ───────────────────────────────────────────────────────────

class EphemeralShopView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, member: discord.Member, items: list[dict], shop_config: dict, page: int = 0):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild = guild
        self.member = member
        self.items = [i for i in items if not i.get("is_custom")]
        self.shop_config = shop_config
        self.page = page
        self._build()

    def _build(self):
        self.clear_items()
        start = self.page * 25
        end = start + 25
        page_items = self.items[start:end]

        if not page_items:
            btn = discord.ui.Button(label="Loja Vazia", disabled=True)
            self.add_item(btn)
            return

        options = []
        for item in page_items:
            emoji_str = item.get("emoji") or "🎭"
            desc = _truncate(f"{item['price']:,}{SWEET_COIN} | {item.get('description', '')}", 95)
            options.append(
                discord.SelectOption(
                    label=item["name"][:100],
                    description=desc,
                    value=str(item["id"]),
                    emoji=emoji_str
                )
            )

        select = discord.ui.Select(placeholder="Selecione um cargo para comprar...", options=options)

        async def select_callback(interaction: discord.Interaction):
            item_id = int(select.values[0])
            await self._handle_buy_item(interaction, item_id)

        select.callback = select_callback
        self.add_item(select)

        if start > 0:
            btn_prev = discord.ui.Button(label="⬅️ Anterior", style=discord.ButtonStyle.secondary)
            async def prev_cb(interaction: discord.Interaction):
                self.page -= 1
                self._build()
                await interaction.response.edit_message(view=self)
            btn_prev.callback = prev_cb
            self.add_item(btn_prev)

        if end < len(self.items):
            btn_next = discord.ui.Button(label="Próxima ➡️", style=discord.ButtonStyle.secondary)
            async def next_cb(interaction: discord.Interaction):
                self.page += 1
                self._build()
                await interaction.response.edit_message(view=self)
            btn_next.callback = next_cb
            self.add_item(btn_next)

    async def _handle_buy_item(self, interaction: discord.Interaction, item_id: int):
        db = self.bot.db
        guild = self.guild
        member = self.member
        
        await interaction.response.defer(ephemeral=True)

        try:
            item = await db.get_shop_item(item_id)
            if not item or item["guild_id"] != guild.id:
                await interaction.followup.send("❌ Este item não está mais disponível.", ephemeral=True)
                return

            role = guild.get_role(item["role_id"])
            if not role:
                await interaction.followup.send("❌ O cargo deste item foi removido do servidor. Avise um administrador.", ephemeral=True)
                return

            if role in member.roles:
                await interaction.followup.send(f"❌ Você já possui o cargo **{item['name']}**.", ephemeral=True)
                return

            if await db.has_purchased(member.id, guild.id, item_id):
                await interaction.followup.send(f"❌ Você já comprou **{item['name']}**.", ephemeral=True)
                return

            user = await db.get_user(member.id, guild.id)
            price = item["price"]
            if user["balance"] < price:
                await interaction.followup.send(
                    f"❌ Saldo insuficiente! Você tem `{user['balance']:,}` {SWEET_COIN}, "
                    f"mas **{item['name']}** custa `{price:,}` {SWEET_COIN}.", ephemeral=True)
                return

            emoji_str = item.get("emoji") or "🎭"
            confirm_embed = discord.Embed(
                title="🛒 Confirmar compra",
                description=(f"{emoji_str} **{item['name']}**\n"
                             f"Preço: `{price:,}` {SWEET_COIN}\n"
                             f"Saldo após compra: `{user['balance'] - price:,}` {SWEET_COIN}"),
                color=WARNING_COLOR,
            )
            confirm_view = BuyConfirmView(self.bot, member, guild, item)
            await interaction.followup.send(embed=confirm_embed, view=confirm_view, ephemeral=True)

        except discord.HTTPException as exc:
            log.warning("Erro HTTP na compra da loja: %s", exc)
        except Exception:
            log.exception("Erro inesperado na compra da loja")

class EphemeralMarketView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, member: discord.Member, listings: list[dict], page: int = 0):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild = guild
        self.member = member
        self.listings = listings
        self.page = page
        self._build()

    def _build(self):
        self.clear_items()
        start = self.page * 25
        end = start + 25
        page_items = self.listings[start:end]

        if not page_items:
            btn = discord.ui.Button(label="Mercado Vazio", disabled=True)
            self.add_item(btn)
            return

        options = []
        for lst in page_items:
            role = self.guild.get_role(lst["role_id"])
            role_name = role.name if role else "Cargo Removido"
            seller = self.guild.get_member(lst["seller_id"])
            seller_name = seller.display_name if seller else f"ID: {lst['seller_id']}"
            options.append(
                discord.SelectOption(
                    label=f"#{lst['id']} {role_name}"[:100],
                    description=f"{lst['price']:,}{SWEET_COIN} | Vendido por {seller_name}"[:100],
                    value=str(lst["id"]),
                    emoji="🏷️"
                )
            )

        select = discord.ui.Select(placeholder="Selecione um anúncio para comprar...", options=options)

        async def select_callback(interaction: discord.Interaction):
            listing_id = int(select.values[0])
            await self._handle_market_buy(interaction, listing_id)

        select.callback = select_callback
        self.add_item(select)

        if start > 0:
            btn_prev = discord.ui.Button(label="⬅️ Anterior", style=discord.ButtonStyle.secondary)
            async def prev_cb(interaction: discord.Interaction):
                self.page -= 1
                self._build()
                await interaction.response.edit_message(view=self)
            btn_prev.callback = prev_cb
            self.add_item(btn_prev)

        if end < len(self.listings):
            btn_next = discord.ui.Button(label="Próxima ➡️", style=discord.ButtonStyle.secondary)
            async def next_cb(interaction: discord.Interaction):
                self.page += 1
                self._build()
                await interaction.response.edit_message(view=self)
            btn_next.callback = next_cb
            self.add_item(btn_next)

    async def _handle_market_buy(self, interaction: discord.Interaction, listing_id: int):
        db = self.bot.db
        guild = self.guild
        buyer_id = interaction.user.id
        await interaction.response.defer(ephemeral=True)

        try:
            listing = await db.get_role_listing(listing_id)
            if not listing or listing["guild_id"] != guild.id:
                await interaction.followup.send("❌ Este anúncio não existe mais.", ephemeral=True)
                return

            if listing["seller_id"] == buyer_id:
                await interaction.followup.send("❌ Você não pode comprar seu próprio anúncio.", ephemeral=True)
                return

            role = guild.get_role(listing["role_id"])
            if not role:
                await interaction.followup.send("❌ O cargo deste anúncio foi removido do servidor.", ephemeral=True)
                return

            price = listing["price"]
            user = await db.get_user(buyer_id, guild.id)
            if user["balance"] < price:
                await interaction.followup.send(
                    f"❌ Saldo insuficiente! Você tem `{user['balance']:,}` {SWEET_COIN}, "
                    f"mas este cargo custa `{price:,}` {SWEET_COIN}.", ephemeral=True)
                return

            seller = guild.get_member(listing["seller_id"])
            seller_str = seller.mention if seller else f"`id:{listing['seller_id']}`"

            confirm_embed = discord.Embed(
                title="🛒 Confirmar compra no mercado",
                description=(f"Cargo: {role.mention}\n"
                             f"Vendedor: {seller_str}\n"
                             f"Preço: `{price:,}` {SWEET_COIN}\n"
                             f"Saldo após compra: `{user['balance'] - price:,}` {SWEET_COIN}"),
                color=WARNING_COLOR,
            )
            confirm_view = MarketBuyConfirmView(self.bot, interaction.user, guild, listing)
            await interaction.followup.send(embed=confirm_embed, view=confirm_view, ephemeral=True)

        except discord.HTTPException as exc:
            log.warning("Erro HTTP na compra do mercado: %s", exc)
        except Exception:
            log.exception("Erro inesperado na compra do mercado")

class EphemeralInventoryView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, member: discord.Member, purchases: list[dict], page: int = 0):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild = guild
        self.member = member
        self.purchases = purchases
        self.page = page
        self._build()

    def _build(self):
        self.clear_items()
        start = self.page * 25
        end = start + 25
        page_items = self.purchases[start:end]

        if not page_items:
            btn = discord.ui.Button(label="Inventário Vazio", disabled=True)
            self.add_item(btn)
            return

        options = []
        for p in page_items:
            role = self.guild.get_role(p["role_id"])
            role_name = role.name if role else "Cargo Removido"
            equipped = role in self.member.roles if role else False
            status = "Equipado" if equipped else "Desequipado"
            emoji_str = "✅" if equipped else "🎒"
            options.append(
                discord.SelectOption(
                    label=role_name[:100],
                    description=f"{p['name'][:50]} | {status}",
                    value=str(p['id']),
                    emoji=emoji_str
                )
            )

        select = discord.ui.Select(placeholder="Selecione um cargo para Equipar/Desequipar...", options=options)

        async def select_callback(interaction: discord.Interaction):
            item_id = int(select.values[0])
            await self._handle_toggle(interaction, item_id)

        select.callback = select_callback
        self.add_item(select)

        if start > 0:
            btn_prev = discord.ui.Button(label="⬅️ Anterior", style=discord.ButtonStyle.secondary)
            async def prev_cb(interaction: discord.Interaction):
                self.page -= 1
                self._build()
                await interaction.response.edit_message(view=self)
            btn_prev.callback = prev_cb
            self.add_item(btn_prev)

        if end < len(self.purchases):
            btn_next = discord.ui.Button(label="Próxima ➡️", style=discord.ButtonStyle.secondary)
            async def next_cb(interaction: discord.Interaction):
                self.page += 1
                self._build()
                await interaction.response.edit_message(view=self)
            btn_next.callback = next_cb
            self.add_item(btn_next)

    async def _handle_toggle(self, interaction: discord.Interaction, item_id: int):
        db = self.bot.db
        guild = self.guild
        member = interaction.user
        
        await interaction.response.defer(ephemeral=True)
        try:
            item = await db.get_shop_item(item_id)
            if not item:
                await interaction.followup.send("❌ Este item não existe mais.", ephemeral=True)
                return

            role = guild.get_role(item["role_id"])
            if not role:
                await interaction.followup.send("❌ O cargo deste item foi removido do servidor.", ephemeral=True)
                return

            if role in member.roles:
                await member.remove_roles(role, reason="Desequipado via Inventário")
                await interaction.followup.send(f"🎒 Você desequipou o cargo **{role.name}**.", ephemeral=True)
            else:
                await member.add_roles(role, reason="Equipado via Inventário")
                await interaction.followup.send(f"✅ Você equipou o cargo **{role.name}**.", ephemeral=True)
                
            self._build()
            await interaction.edit_original_response(view=self)

        except discord.Forbidden:
            await interaction.followup.send("❌ Não tenho permissão para alterar seus cargos.", ephemeral=True)
        except Exception:
            log.exception("Erro no toggle de inventário")

# ── Shop Panel View ───────────────────────────────────────────────────────────

class ShopPanelView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        
        btn_shop = discord.ui.Button(label="🛒 Ver Loja", style=discord.ButtonStyle.primary, custom_id=f"sp_shop:{guild_id}")
        btn_shop.callback = self._open_shop
        self.add_item(btn_shop)
        
        btn_custom = discord.ui.Button(label="✨ Criar Cargo", style=discord.ButtonStyle.success, custom_id=f"sp_custom:{guild_id}")
        btn_custom.callback = self._create_role
        self.add_item(btn_custom)
        
        btn_market = discord.ui.Button(label="🔄 Mercado", style=discord.ButtonStyle.secondary, custom_id=f"sp_market:{guild_id}")
        btn_market.callback = self._open_market
        self.add_item(btn_market)
        
        btn_inv = discord.ui.Button(label="🎒 Meu Inventário", style=discord.ButtonStyle.secondary, custom_id=f"sp_inv:{guild_id}")
        btn_inv.callback = self._open_inventory
        self.add_item(btn_inv)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message("Este painel pertence a outro servidor.", ephemeral=True)
            return False
        return True

    async def _open_shop(self, interaction: discord.Interaction):
        items = await self.bot.db.get_shop(self.guild_id)
        shop_config = await self.bot.db.get_shop_config(self.guild_id)
        view = EphemeralShopView(self.bot, interaction.guild, interaction.user, items, shop_config)
        await interaction.response.send_message("🛒 **Catálogo da Loja**", view=view, ephemeral=True)

    async def _create_role(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CustomRoleModal(self.bot))

    async def _open_market(self, interaction: discord.Interaction):
        listings = await self.bot.db.get_role_listings(self.guild_id)
        view = EphemeralMarketView(self.bot, interaction.guild, interaction.user, listings)
        await interaction.response.send_message("🔄 **Mercado de Cargos**", view=view, ephemeral=True)

    async def _open_inventory(self, interaction: discord.Interaction):
        purchases = await self.bot.db.get_purchases(interaction.user.id, self.guild_id)
        view = EphemeralInventoryView(self.bot, interaction.guild, interaction.user, purchases)
        await interaction.response.send_message("🎒 **Seu Inventário de Cargos**", view=view, ephemeral=True)



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

        try:
            if cid.startswith(("shop_buy_", "shop_create_role", "market_buy_")):
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ Este painel é antigo. Por favor, use o novo painel com o menu suspenso.",
                        ephemeral=True,
                    )
                return
        except Exception:

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
        shop_view = ShopPanelView(self.bot, guild.id)
        self.bot.add_view(shop_view)

    # ── Panel helpers ─────────────────────────────────────────────────────────

    async def _post_shop_panel(
        self, channel: discord.TextChannel, guild: discord.Guild,
        items: list[dict], shop_config: dict,
    ) -> discord.Message:
        """Send a brand-new shop panel (image + buttons)."""
        view = ShopPanelView(self.bot, guild.id)
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
        """Edit or re-post market panel. (Now ephemeral, so this does nothing)"""
        pass

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
