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

