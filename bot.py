import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from database import Database

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True


class CommunityBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            help_command=None,
        )
        self.db = Database()
        self._guild_synced_once = False

    async def setup_hook(self):
        await self.db.initialize()

        cogs = [
            "cogs.levels",
            "cogs.shop",
            "cogs.giveaway",
            "cogs.anonymous",
            "cogs.profile",
            "cogs.moderation",
            "cogs.economy",
            "cogs.welcome",
            "cogs.tickets",
            "cogs.marriage",
            "cogs.clans",
            "cogs.admin_panel",
            "cogs.guide",
            "cogs.soulsbets",
            "cogs.testes",
            "cogs.fight",
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f"  ✓ {cog}")
            except Exception as exc:
                print(f"  ✗ {cog}: {exc}")

        # Global sync existe, mas pode demorar para propagar.
        await self.tree.sync()
        print("Slash commands sincronizados globalmente.")

    async def on_ready(self):
        if not self._guild_synced_once:
            for guild in self.guilds:
                try:
                    await self.tree.sync(guild=guild)
                    print(f"  → Sincronizado no servidor: {guild.name}")
                except Exception as exc:
                    print(f"  ✗ Falha ao sincronizar {guild.name}: {exc}")
            self._guild_synced_once = True

        print(f"\n{'─'*40}")
        print(f"Bot:        {self.user} ({self.user.id})")
        print(f"Servidores: {len(self.guilds)}")
        print(f"{'─'*40}\n")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{len(self.guilds)} servidores | /perfil",
            )
        )


bot = CommunityBot()


@bot.command(name="sync")
@commands.has_permissions(administrator=True)
async def sync_cmd(ctx: commands.Context):
    """Força a sincronização dos slash commands no servidor atual."""
    if ctx.guild is None:
        await ctx.send("Use este comando dentro de um servidor.")
        return
    await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"✅ Slash commands sincronizados em **{ctx.guild.name}**!")


@sync_cmd.error
async def sync_cmd_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Você precisa de permissão de administrador para usar `!sync`.")
        return
    await ctx.send(f"Erro ao sincronizar: {error}")


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("ERRO: DISCORD_TOKEN não encontrado no arquivo .env")
        raise SystemExit(1)
    bot.run(token, log_handler=None)
