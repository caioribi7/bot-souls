import asyncio
import random
import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_COLOR, ERROR_COLOR, SUCCESS_COLOR, WARNING_COLOR, COIN_EMOJI

SWEET_COIN_EMOJI = "🍬"

# GIFs
GIF_PUNCH = "https://media.giphy.com/media/l41Yf1B1gEokI5yXq/giphy.gif"
GIF_KICK = "https://media.giphy.com/media/wLorCd0i4nQ6Y/giphy.gif"
GIF_SPECIAL = "https://media.giphy.com/media/OQ6tzMPyK6ItCPfcGb/giphy.gif"
GIF_HEAL = "https://media.giphy.com/media/xT1R9B7cGalGjF8X1m/giphy.gif"
GIF_IDLE = "https://media.giphy.com/media/3o7TKSjRrfIPjeiVyQ/giphy.gif"
GIF_WIN = "https://media.giphy.com/media/1n8y2XhBAnSg4ZtEAM/giphy.gif"


class FightGame:
    def __init__(self, p1: discord.Member, p2: discord.Member, bet: int):
        self.p1 = p1
        self.p2 = p2
        self.bet = bet
        
        self.p1_hp = 100
        self.p2_hp = 100
        self.p1_special_cd = 0
        self.p2_special_cd = 0
        
        self.turn = p1 # p1 starts
        self.log = f"A batalha começou entre **{p1.display_name}** e **{p2.display_name}**!"
        self.last_gif = GIF_IDLE
        self.winner = None

    def get_hp(self, player):
        if player == self.p1:
            return self.p1_hp
        return self.p2_hp
        
    def reduce_hp(self, player, amount):
        if player == self.p1:
            self.p1_hp = max(0, self.p1_hp - amount)
        else:
            self.p2_hp = max(0, self.p2_hp - amount)
            
    def heal_hp(self, player, amount):
        if player == self.p1:
            self.p1_hp = min(100, self.p1_hp + amount)
        else:
            self.p2_hp = min(100, self.p2_hp + amount)

    def pass_turn(self):
        if self.p1_hp <= 0:
            self.winner = self.p2
            self.last_gif = GIF_WIN
            return
        if self.p2_hp <= 0:
            self.winner = self.p1
            self.last_gif = GIF_WIN
            return
            
        if self.turn == self.p1:
            self.turn = self.p2
            if self.p2_special_cd > 0:
                self.p2_special_cd -= 1
        else:
            self.turn = self.p1
            if self.p1_special_cd > 0:
                self.p1_special_cd -= 1


class FightView(discord.ui.View):
    def __init__(self, cog, game: FightGame):
        super().__init__(timeout=120)
        self.cog = cog
        self.game = game

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.game.turn:
            if interaction.user in (self.game.p1, self.game.p2):
                await interaction.response.send_message("Não é o seu turno!", ephemeral=True)
            else:
                await interaction.response.send_message("Você não está nesta batalha.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        g = self.game
        embed = discord.Embed(
            title="⚔️ Batalha Anime",
            description=g.log,
            color=SUCCESS_COLOR if g.winner else BOT_COLOR
        )
        
        p1_bar = "🟥" * (g.p1_hp // 10) + "⬛" * (10 - g.p1_hp // 10)
        p2_bar = "🟥" * (g.p2_hp // 10) + "⬛" * (10 - g.p2_hp // 10)
        
        embed.add_field(
            name=f"{g.p1.display_name} {'(👑 Vencedor)' if g.winner == g.p1 else ''}",
            value=f"HP: {g.p1_hp}/100\n{p1_bar}",
            inline=True
        )
        embed.add_field(
            name=f"{g.p2.display_name} {'(👑 Vencedor)' if g.winner == g.p2 else ''}",
            value=f"HP: {g.p2_hp}/100\n{p2_bar}",
            inline=True
        )
        
        if g.bet > 0:
            embed.add_field(
                name="Aposta",
                value=f"{SWEET_COIN_EMOJI} **{g.bet * 2:,}** (Pote Total)",
                inline=False
            )
            
        if not g.winner:
            embed.add_field(
                name="Turno",
                value=f"É a vez de **{g.turn.display_name}** agir!",
                inline=False
            )
            
        embed.set_image(url=g.last_gif)
        return embed

    async def update_message(self, interaction: discord.Interaction):
        if self.game.winner:
            self.stop()
            # Disable buttons
            for child in self.children:
                child.disabled = True
                
            # Distribute coins if bet
            if self.game.bet > 0:
                pot = self.game.bet * 2
                await self.cog.bot.db.add_coins(self.game.winner.id, interaction.guild_id, pot)
                self.game.log += f"\n\n🏆 **{self.game.winner.display_name}** venceu a batalha e ganhou {SWEET_COIN_EMOJI} **{pot:,}**!"
            else:
                self.game.log += f"\n\n🏆 **{self.game.winner.display_name}** venceu a batalha!"

        embed = self.build_embed()
        
        # Update button states based on special cooldown
        if not self.game.winner:
            current_cd = self.game.p1_special_cd if self.game.turn == self.game.p1 else self.game.p2_special_cd
            for child in self.children:
                if isinstance(child, discord.ui.Button) and child.custom_id == "special":
                    if current_cd > 0:
                        child.disabled = True
                        child.label = f"✨ Especial ({current_cd})"
                    else:
                        child.disabled = False
                        child.label = "✨ Especial"

        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        g = self.game
        if g.winner:
            return
            
        # The player whose turn it is loses by timeout
        loser = g.turn
        winner = g.p2 if loser == g.p1 else g.p1
        
        g.winner = winner
        g.log = f"⏳ **{loser.display_name}** demorou muito e desistiu da luta!\n**{winner.display_name}** vence por W.O.!"
        g.last_gif = GIF_WIN
        
        for child in self.children:
            child.disabled = True
            
        # Attempt to edit original message
        if hasattr(self, "message") and self.message:
            embed = self.build_embed()
            if g.bet > 0:
                pot = g.bet * 2
                # give back money? or give it all to winner?
                # W.O. gives money to winner
                try:
                    await self.cog.bot.db.add_coins(g.winner.id, self.message.guild.id, pot)
                except:
                    pass
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="👊 Soco", style=discord.ButtonStyle.primary, custom_id="punch")
    async def punch(self, interaction: discord.Interaction, button: discord.ui.Button):
        target = self.game.p2 if self.game.turn == self.game.p1 else self.game.p1
        dmg = random.randint(10, 15)
        
        self.game.reduce_hp(target, dmg)
        self.game.log = f"**{self.game.turn.display_name}** deu um soco em **{target.display_name}** causando **{dmg}** de dano!"
        self.game.last_gif = GIF_PUNCH
        self.game.pass_turn()
        await self.update_message(interaction)

    @discord.ui.button(label="🦵 Chute", style=discord.ButtonStyle.danger, custom_id="kick")
    async def kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        target = self.game.p2 if self.game.turn == self.game.p1 else self.game.p1
        hit_chance = random.random()
        
        if hit_chance <= 0.7: # 70% chance to hit
            dmg = random.randint(20, 30)
            self.game.reduce_hp(target, dmg)
            self.game.log = f"**{self.game.turn.display_name}** acertou um chute em cheio em **{target.display_name}**, causando **{dmg}** de dano!"
        else:
            self.game.log = f"**{self.game.turn.display_name}** tentou um chute em **{target.display_name}**, mas errou!"
            
        self.game.last_gif = GIF_KICK
        self.game.pass_turn()
        await self.update_message(interaction)

    @discord.ui.button(label="✨ Especial", style=discord.ButtonStyle.success, custom_id="special")
    async def special(self, interaction: discord.Interaction, button: discord.ui.Button):
        target = self.game.p2 if self.game.turn == self.game.p1 else self.game.p1
        dmg = random.randint(35, 50)
        
        self.game.reduce_hp(target, dmg)
        self.game.log = f"**{self.game.turn.display_name}** usou seu ATAQUE ESPECIAL em **{target.display_name}** causando um dano massivo de **{dmg}**!"
        self.game.last_gif = GIF_SPECIAL
        
        if self.game.turn == self.game.p1:
            self.game.p1_special_cd = 3
        else:
            self.game.p2_special_cd = 3
            
        self.game.pass_turn()
        await self.update_message(interaction)

    @discord.ui.button(label="🛡️ Curar/Defender", style=discord.ButtonStyle.secondary, custom_id="heal")
    async def heal(self, interaction: discord.Interaction, button: discord.ui.Button):
        heal_amt = random.randint(15, 25)
        self.game.heal_hp(self.game.turn, heal_amt)
        
        self.game.log = f"**{self.game.turn.display_name}** recuou e se curou, recuperando **{heal_amt}** de HP!"
        self.game.last_gif = GIF_HEAL
        self.game.pass_turn()
        await self.update_message(interaction)


class FightInviteView(discord.ui.View):
    def __init__(self, cog, challenger: discord.Member, target: discord.Member, bet: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.challenger = challenger
        self.target = target
        self.bet = bet

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.target:
            await interaction.response.send_message("Este convite não é para você.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Aceitar Luta", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.stop()
        
        db = self.cog.bot.db
        if self.bet > 0:
            # Check balances again to be sure
            challenger_deducted = await db.deduct_coins(self.challenger.id, interaction.guild_id, self.bet)
            if not challenger_deducted:
                await interaction.edit_original_response(
                    content=f"O convite foi cancelado porque {self.challenger.display_name} não tem mais o saldo necessário.",
                    embed=None, view=None
                )
                return
                
            target_deducted = await db.deduct_coins(self.target.id, interaction.guild_id, self.bet)
            if not target_deducted:
                # Refund challenger
                await db.add_coins(self.challenger.id, interaction.guild_id, self.bet)
                await interaction.edit_original_response(
                    content=f"O convite foi cancelado porque {self.target.display_name} não tem o saldo necessário.",
                    embed=None, view=None
                )
                return

        game = FightGame(self.challenger, self.target, self.bet)
        view = FightView(self.cog, game)
        embed = view.build_embed()
        
        msg = await interaction.edit_original_response(content=None, embed=embed, view=view)
        view.message = msg

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            content=f"**{self.target.display_name}** recusou o desafio de **{self.challenger.display_name}**.",
            embed=None, view=None
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if hasattr(self, "message") and self.message:
                await self.message.edit(content=f"O desafio para **{self.target.display_name}** expirou.", view=None)
        except:
            pass


class FightCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="lutar", description="Desafie um membro para uma batalha por turnos!")
    @app_commands.describe(
        membro="Membro que você quer desafiar",
        aposta="Valor em Sweet Coins para apostar na luta (Opcional)"
    )
    async def lutar(self, interaction: discord.Interaction, membro: discord.Member, aposta: int = 0):
        if membro == interaction.user:
            await interaction.response.send_message("Você não pode lutar contra si mesmo!", ephemeral=True)
            return
            
        if membro.bot:
            await interaction.response.send_message("Você não pode lutar contra bots!", ephemeral=True)
            return
            
        if aposta < 0:
            await interaction.response.send_message("A aposta não pode ser negativa.", ephemeral=True)
            return

        db = self.bot.db
        
        if aposta > 0:
            user_data = await db.get_user(interaction.user.id, interaction.guild_id)
            if user_data['balance'] < aposta:
                embed = discord.Embed(
                    description=f"Você não tem {SWEET_COIN_EMOJI} **{aposta:,}** para apostar.",
                    color=ERROR_COLOR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
                
            target_data = await db.get_user(membro.id, interaction.guild_id)
            if target_data['balance'] < aposta:
                embed = discord.Embed(
                    description=f"**{membro.display_name}** não tem {SWEET_COIN_EMOJI} **{aposta:,}** para cobrir a aposta.",
                    color=ERROR_COLOR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

        embed = discord.Embed(
            title="⚔️ Desafio de Luta!",
            description=f"**{interaction.user.display_name}** desafiou **{membro.display_name}** para uma batalha!",
            color=WARNING_COLOR
        )
        if aposta > 0:
            embed.add_field(name="Aposta em jogo", value=f"{SWEET_COIN_EMOJI} **{aposta:,}** de cada lado.")
        embed.set_footer(text="O desafiado tem 60 segundos para aceitar.")

        view = FightInviteView(self, interaction.user, membro, aposta)
        await interaction.response.send_message(content=membro.mention, embed=embed, view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(FightCog(bot))
