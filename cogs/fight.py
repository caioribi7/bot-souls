import asyncio
import random
import discord
from discord import app_commands
from discord.ext import commands

from config import BOT_COLOR, ERROR_COLOR, SUCCESS_COLOR, WARNING_COLOR, COIN_EMOJI
from gifs_config import (
    GIF_PUNCH, GIF_KICK, GIF_BLOCK, GIF_DODGE, GIF_HEAL, GIF_IDLE, GIF_WIN,
    GIF_SPECIAL_1, GIF_SPECIAL_2, GIF_SPECIAL_3, GIF_SPECIAL_4, GIF_SPECIAL_5
)

SWEET_COIN_EMOJI = "🍬"

SPECIALS = {
    1: {"name": "Explosão Estelar", "desc": "Dano muito alto, longo tempo de recarga.", "gif": GIF_SPECIAL_1},
    2: {"name": "Corte Dimensional", "desc": "Ignora bloqueio e esquiva do oponente.", "gif": GIF_SPECIAL_2},
    3: {"name": "Cura Divina", "desc": "Recupera uma grande quantidade de vida.", "gif": GIF_SPECIAL_3},
    4: {"name": "Fúria do Dragão", "desc": "Causa mais dano quanto menor for o seu HP.", "gif": GIF_SPECIAL_4},
    5: {"name": "Roubo de Alma", "desc": "Causa dano e cura o usuário em 50% do dano causado.", "gif": GIF_SPECIAL_5},
}

class BuildModal(discord.ui.Modal, title="Distribuição de Pontos (Máx 10)"):
    soco = discord.ui.TextInput(label="Soco", default="0", max_length=2)
    chute = discord.ui.TextInput(label="Chute", default="0", max_length=2)
    bloqueio = discord.ui.TextInput(label="Bloqueio", default="0", max_length=2)
    esquiva = discord.ui.TextInput(label="Esquiva", default="0", max_length=2)

    def __init__(self, cog, user_id, current_special):
        super().__init__()
        self.cog = cog
        self.user_id = user_id
        self.current_special = current_special

    async def on_submit(self, interaction: discord.Interaction):
        try:
            s = int(self.soco.value)
            c = int(self.chute.value)
            b = int(self.bloqueio.value)
            e = int(self.esquiva.value)
        except ValueError:
            await interaction.response.send_message("Os valores devem ser números inteiros.", ephemeral=True)
            return

        if s < 0 or c < 0 or b < 0 or e < 0:
            await interaction.response.send_message("Os valores não podem ser negativos.", ephemeral=True)
            return

        if s + c + b + e > 10:
            await interaction.response.send_message(f"Você tem apenas 10 pontos! Tentou usar {s+c+b+e}.", ephemeral=True)
            return

        # Next step: Choose special
        view = SpecialSelectView(self.cog, self.user_id, s, c, b, e, self.current_special)
        embed = discord.Embed(
            title="Escolha sua Habilidade Especial",
            description="Selecione abaixo o seu especial para finalizar a build.",
            color=BOT_COLOR
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class SpecialSelect(discord.ui.Select):
    def __init__(self, current_special):
        options = []
        for sid, data in SPECIALS.items():
            options.append(discord.SelectOption(
                label=data["name"],
                description=data["desc"],
                value=str(sid),
                default=(sid == current_special)
            ))
        super().__init__(placeholder="Escolha um Especial...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view: SpecialSelectView = self.view
        special_id = int(self.values[0])
        await view.cog.bot.db.save_fight_build(
            view.user_id, view.s, view.c, view.b, view.e, special_id
        )
        await interaction.response.edit_message(
            content="✅ **Build salva com sucesso!** Você está pronto para a batalha.",
            embed=None, view=None
        )


class SpecialSelectView(discord.ui.View):
    def __init__(self, cog, user_id, s, c, b, e, current_special):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.s = s
        self.c = c
        self.b = b
        self.e = e
        self.add_item(SpecialSelect(current_special))


class FightGame:
    def __init__(self, p1: discord.Member, p2: discord.Member, bet: int, build1: dict, build2: dict):
        self.p1 = p1
        self.p2 = p2
        self.bet = bet
        self.build1 = build1
        self.build2 = build2
        
        self.p1_hp = 100
        self.p2_hp = 100
        self.p1_special_cd = 0
        self.p2_special_cd = 0
        
        self.turn = p1 # p1 starts
        self.log = f"A batalha começou entre **{p1.display_name}** e **{p2.display_name}**!"
        self.last_gif = GIF_IDLE
        self.winner = None

    def get_target(self):
        return self.p2 if self.turn == self.p1 else self.p1

    def get_hp(self, player):
        if player == self.p1:
            return self.p1_hp
        return self.p2_hp

    def get_current_build(self):
        return self.build1 if self.turn == self.p1 else self.build2

    def get_target_build(self):
        return self.build2 if self.turn == self.p1 else self.build1

    def reduce_hp(self, player, amount):
        if player == self.p1:
            self.p1_hp = max(0, int(self.p1_hp - amount))
        else:
            self.p2_hp = max(0, int(self.p2_hp - amount))
            
    def heal_hp(self, player, amount):
        if player == self.p1:
            self.p1_hp = min(100, int(self.p1_hp + amount))
        else:
            self.p2_hp = min(100, int(self.p2_hp + amount))

    def apply_defense(self, damage, ignore_defense=False):
        """Returns (final_damage, log_append, gif_override)"""
        if ignore_defense:
            return damage, "", None
            
        t_build = self.get_target_build()
        
        # Dodge chance: 2% per point
        dodge_chance = t_build["pts_esquiva"] * 0.04  # Increased to 4% per point to be useful
        if random.random() < dodge_chance:
            return 0, f"\n💨 **{self.get_target().display_name}** se ESQUIVOU completamente do ataque!", GIF_DODGE

        # Block chance: 10% + 5% per point
        block_chance = 0.10 + (t_build["pts_bloqueio"] * 0.05)
        if random.random() < block_chance:
            # Block reduction: 10% + 4% per point
            reduction = 0.10 + (t_build["pts_bloqueio"] * 0.04)
            damage = damage * (1.0 - reduction)
            return damage, f"\n🛡️ **{self.get_target().display_name}** bloqueou o ataque, reduzindo o dano recebido!", GIF_BLOCK
            
        return damage, "", None

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
            title="⚔️ Batalha RPG",
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
            for child in self.children:
                child.disabled = True
                
            if self.game.bet > 0:
                pot = self.game.bet * 2
                await self.cog.bot.db.add_coins(self.game.winner.id, interaction.guild_id, pot)
                self.game.log += f"\n\n🏆 **{self.game.winner.display_name}** venceu a batalha e ganhou {SWEET_COIN_EMOJI} **{pot:,}**!"
            else:
                self.game.log += f"\n\n🏆 **{self.game.winner.display_name}** venceu a batalha!"

        embed = self.build_embed()
        
        if not self.game.winner:
            current_cd = self.game.p1_special_cd if self.game.turn == self.game.p1 else self.game.p2_special_cd
            for child in self.children:
                if isinstance(child, discord.ui.Button) and child.custom_id == "special":
                    build = self.game.get_current_build()
                    spec_name = SPECIALS[build["special_id"]]["name"]
                    if current_cd > 0:
                        child.disabled = True
                        child.label = f"✨ {spec_name} ({current_cd})"
                    else:
                        child.disabled = False
                        child.label = f"✨ {spec_name}"

        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        g = self.game
        if g.winner:
            return
            
        loser = g.turn
        winner = g.p2 if loser == g.p1 else g.p1
        
        g.winner = winner
        g.log = f"⏳ **{loser.display_name}** demorou muito e desistiu da luta!\n**{winner.display_name}** vence por W.O.!"
        g.last_gif = GIF_WIN
        
        for child in self.children:
            child.disabled = True
            
        if hasattr(self, "message") and self.message:
            embed = self.build_embed()
            if g.bet > 0:
                pot = g.bet * 2
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
        target = self.game.get_target()
        build = self.game.get_current_build()
        
        base_dmg = random.randint(10, 15) + (build["pts_soco"] * 2)
        final_dmg, def_log, def_gif = self.game.apply_defense(base_dmg)
        final_dmg = int(final_dmg)
        
        self.game.reduce_hp(target, final_dmg)
        self.game.log = f"**{self.game.turn.display_name}** deu um soco em **{target.display_name}** causando **{final_dmg}** de dano!{def_log}"
        self.game.last_gif = def_gif if def_gif else GIF_PUNCH
        self.game.pass_turn()
        await self.update_message(interaction)

    @discord.ui.button(label="🦵 Chute", style=discord.ButtonStyle.danger, custom_id="kick")
    async def kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        target = self.game.get_target()
        build = self.game.get_current_build()
        
        hit_chance = 0.60 + (build["pts_chute"] * 0.05)
        
        if random.random() <= hit_chance: 
            base_dmg = random.randint(20, 30) + (build["pts_chute"] * 3)
            final_dmg, def_log, def_gif = self.game.apply_defense(base_dmg)
            final_dmg = int(final_dmg)
            
            self.game.reduce_hp(target, final_dmg)
            self.game.log = f"**{self.game.turn.display_name}** acertou um chute em cheio causando **{final_dmg}** de dano!{def_log}"
            self.game.last_gif = def_gif if def_gif else GIF_KICK
        else:
            self.game.log = f"**{self.game.turn.display_name}** tentou um chute em **{target.display_name}**, mas errou miseravelmente!"
            self.game.last_gif = GIF_DODGE
            
        self.game.pass_turn()
        await self.update_message(interaction)

    @discord.ui.button(label="✨ Especial", style=discord.ButtonStyle.success, custom_id="special")
    async def special(self, interaction: discord.Interaction, button: discord.ui.Button):
        target = self.game.get_target()
        build = self.game.get_current_build()
        spec_id = build["special_id"]
        
        dmg = 0
        def_log = ""
        def_gif = None
        
        if spec_id == 1: # Explosão Estelar
            base_dmg = random.randint(35, 50)
            dmg, def_log, def_gif = self.game.apply_defense(base_dmg)
            self.game.log = f"🌌 **{self.game.turn.display_name}** usou EXPLOSÃO ESTELAR causando **{int(dmg)}** de dano!{def_log}"
            
        elif spec_id == 2: # Corte Dimensional
            dmg = random.randint(25, 35)
            # Ignora defesa
            dmg, def_log, def_gif = self.game.apply_defense(dmg, ignore_defense=True)
            self.game.log = f"🗡️ **{self.game.turn.display_name}** usou CORTE DIMENSIONAL (Ignora defesa) causando **{int(dmg)}** de dano!"
            
        elif spec_id == 3: # Cura Divina
            heal_amt = random.randint(30, 45)
            self.game.heal_hp(self.game.turn, heal_amt)
            self.game.log = f"💖 **{self.game.turn.display_name}** usou CURA DIVINA e recuperou **{heal_amt}** de HP!"
            
        elif spec_id == 4: # Fúria do Dragão
            my_hp = self.game.get_hp(self.game.turn)
            missing_hp = 100 - my_hp
            base_dmg = random.randint(20, 25) + int(missing_hp * 0.4)
            dmg, def_log, def_gif = self.game.apply_defense(base_dmg)
            self.game.log = f"🐉 **{self.game.turn.display_name}** usou FÚRIA DO DRAGÃO causando **{int(dmg)}** de dano!{def_log}"
            
        elif spec_id == 5: # Roubo de Alma
            base_dmg = random.randint(25, 35)
            dmg, def_log, def_gif = self.game.apply_defense(base_dmg)
            heal_amt = int(dmg * 0.5)
            self.game.heal_hp(self.game.turn, heal_amt)
            self.game.log = f"🦇 **{self.game.turn.display_name}** usou ROUBO DE ALMA causando **{int(dmg)}** de dano e curando **{heal_amt}** de HP!{def_log}"

        dmg = int(dmg)
        if dmg > 0:
            self.game.reduce_hp(target, dmg)
            
        self.game.last_gif = def_gif if def_gif else SPECIALS[spec_id]["gif"]
        
        # Set cooldown
        if self.game.turn == self.game.p1:
            self.game.p1_special_cd = 3
        else:
            self.game.p2_special_cd = 3
            
        self.game.pass_turn()
        await self.update_message(interaction)

    @discord.ui.button(label="🛡️ Descansar", style=discord.ButtonStyle.secondary, custom_id="heal")
    async def heal(self, interaction: discord.Interaction, button: discord.ui.Button):
        heal_amt = random.randint(10, 15)
        self.game.heal_hp(self.game.turn, heal_amt)
        
        self.game.log = f"**{self.game.turn.display_name}** recuou para descansar e recuperou **{heal_amt}** de HP!"
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
            challenger_deducted = await db.deduct_coins(self.challenger.id, interaction.guild_id, self.bet)
            if not challenger_deducted:
                await interaction.edit_original_response(
                    content=f"O convite foi cancelado porque {self.challenger.display_name} não tem mais o saldo necessário.",
                    embed=None, view=None
                )
                return
                
            target_deducted = await db.deduct_coins(self.target.id, interaction.guild_id, self.bet)
            if not target_deducted:
                await db.add_coins(self.challenger.id, interaction.guild_id, self.bet)
                await interaction.edit_original_response(
                    content=f"O convite foi cancelado porque {self.target.display_name} não tem o saldo necessário.",
                    embed=None, view=None
                )
                return

        # Fetch builds
        build1 = await db.get_fight_build(self.challenger.id)
        build2 = await db.get_fight_build(self.target.id)

        game = FightGame(self.challenger, self.target, self.bet, build1, build2)
        view = FightView(self.cog, game)
        
        # Initial button labels for specials
        for child in view.children:
            if isinstance(child, discord.ui.Button) and child.custom_id == "special":
                child.label = f"✨ {SPECIALS[build1['special_id']]['name']}"
                
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

    @app_commands.command(name="batalha_build", description="Crie ou atualize sua build de Batalha RPG")
    async def batalha_build(self, interaction: discord.Interaction):
        build = await self.bot.db.get_fight_build(interaction.user.id)
        modal = BuildModal(self, interaction.user.id, build.get("special_id", 1))
        
        # Set current values as default
        modal.soco.default = str(build["pts_soco"])
        modal.chute.default = str(build["pts_chute"])
        modal.bloqueio.default = str(build["pts_bloqueio"])
        modal.esquiva.default = str(build["pts_esquiva"])
        
        await interaction.response.send_modal(modal)

    @app_commands.command(name="lutar", description="Desafie um membro para uma Batalha RPG!")
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
            description=f"**{interaction.user.display_name}** desafiou **{membro.display_name}** para uma Batalha RPG!",
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
