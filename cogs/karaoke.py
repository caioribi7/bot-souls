import asyncio
import aiohttp
import random
import urllib.parse
from bs4 import BeautifulSoup
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

from config import BOT_COLOR, ERROR_COLOR, SUCCESS_COLOR, WARNING_COLOR, COIN_EMOJI

SWEET_COIN_EMOJI = "🍬"

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': 'True',
    'extractaudio': True,
    'audioformat': 'mp3',
    'restrictfilenames': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto'
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

MINIGAME_SONGS = [
    {"trecho": "E nessa loucura de dizer que não te quero...", "resposta": "vou negando as aparências"},
    {"trecho": "Cheia de manias, toda dengoza...", "resposta": "menina bonita"},
    {"trecho": "Mina, seus cabelo é da hora...", "resposta": "seu corpão violão"},
    {"trecho": "Porque eu te amo, e não consigo me ver sem ser...", "resposta": "o teu amor por anos"},
    {"trecho": "Eu quero tchu, eu quero tcha...", "resposta": "eu quero tchu tcha tcha tchu tchu tcha"},
]


class Karaoke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.rap_battles = {}

    async def get_lyrics(self, artist, title):
        url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if 'lyrics' in data:
                            return data['lyrics'].strip()
        except Exception as e:
            print(f"Erro na letra: {e}")
            pass
        return None

    karaoke_group = app_commands.Group(name="karaoke", description="Sistema de Karaokê")

    @karaoke_group.command(name="vplay", description="Entra no canal de voz e toca uma música/karaokê do YouTube")
    @app_commands.describe(musica="Nome da música que deseja tocar")
    async def tocar(self, interaction: discord.Interaction, musica: str):
        print("KARAOKE COMANDO RECEBIDO LOCALMENTE!!!")
        await interaction.response.defer()
        
        if not interaction.user.voice:
            await interaction.followup.send("Você precisa estar em um canal de voz primeiro!", ephemeral=True)
            return

        channel = interaction.user.voice.channel

        try:
            try:
                voice_client = await channel.connect()
            except discord.ClientException:
                voice_client = interaction.guild.voice_client
                if voice_client and voice_client.channel != channel:
                    await voice_client.move_to(channel)
        except Exception as e:
            import sys
            await interaction.followup.send(f"❌ Erro de voz. Você está usando o Python do VSCode ({sys.executable}) em vez do Python correto! Detalhe: {e}", ephemeral=True)
            return

        if voice_client and voice_client.is_playing():
            voice_client.stop()

        await interaction.followup.send(f"🔍 Procurando por **{musica}**...")

        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{musica}", download=False))
            if 'entries' in data:
                data = data['entries'][0]

            url2 = data['url']
            title = data.get('title', musica)

            source = discord.FFmpegPCMAudio(url2, **FFMPEG_OPTIONS)
            voice_client.play(source, after=lambda e: print(f'Player error: {e}') if e else None)

            embed = discord.Embed(title="🎶 Karaokê Iniciado", description=f"Tocando agora: **{title}**", color=BOT_COLOR)
            await interaction.channel.send(embed=embed)
        except Exception as e:
            await interaction.channel.send(f"❌ Ocorreu um erro ao reproduzir o áudio. (FFmpeg pode estar faltando na máquina: {e})")
            if voice_client.is_connected():
                await voice_client.disconnect()

    @karaoke_group.command(name="parar", description="Para a música atual e sai do canal de voz")
    async def parar(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()
            await interaction.response.send_message("Karaokê encerrado. Saindo do canal de voz! 👋")
        else:
            await interaction.response.send_message("Eu não estou em um canal de voz.", ephemeral=True)

    @karaoke_group.command(name="letra", description="Busca a letra de uma música")
    @app_commands.describe(cantor="Nome do artista/banda", musica="Nome da música")
    async def letra(self, interaction: discord.Interaction, cantor: str, musica: str):
        await interaction.response.defer()
        lyrics = await self.get_lyrics(cantor, musica)
        
        if lyrics:
            # Cut lyrics if too long
            if len(lyrics) > 4000:
                lyrics = lyrics[:4000] + "...\n(Letra muito longa, cortada.)"
                
            embed = discord.Embed(title=f"🎤 Letra: {musica.title()} - {cantor.title()}", description=lyrics, color=BOT_COLOR)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ Não consegui encontrar a letra dessa música. Verifique a grafia ou tente outra.")

    @karaoke_group.command(name="minigame", description="Complete o trecho da música e ganhe Sweet Coins!")
    async def minigame(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        song = random.choice(MINIGAME_SONGS)
        embed = discord.Embed(
            title="🎤 Qual é a música?",
            description=f"Complete o trecho abaixo no chat nos próximos **20 segundos**:\n\n🎵 *\"{song['trecho']}\"*",
            color=WARNING_COLOR
        )
        await interaction.followup.send(embed=embed)

        def check(m):
            return m.channel == interaction.channel and not m.author.bot

        end_time = asyncio.get_event_loop().time() + 20.0
        while True:
            timeout = end_time - asyncio.get_event_loop().time()
            if timeout <= 0:
                await interaction.channel.send(f"⏳ Tempo esgotado! A resposta correta era: **{song['resposta']}**.")
                return
            
            try:
                msg = await self.bot.wait_for('message', timeout=timeout, check=check)
                if song['resposta'].lower() in msg.content.lower():
                    reward = random.randint(30, 80)
                    await self.bot.db.add_coins(msg.author.id, interaction.guild_id, reward)
                    await interaction.channel.send(f"🎉 Correto, {msg.author.mention}! A letra era **{song['resposta']}**!\nVocê ganhou {SWEET_COIN_EMOJI} **{reward} Sweet Coins**!")
                    return
            except asyncio.TimeoutError:
                await interaction.channel.send(f"⏳ Tempo esgotado! Ninguém acertou. A resposta correta era: **{song['resposta']}**.")
                return

    # ── Batalha de Rap ──
    @app_commands.command(name="batalha_rap", description="Desafie alguém para uma Batalha de Rap no canal de voz!")
    @app_commands.describe(adversario="O usuário que você vai desafiar")
    async def batalha_rap(self, interaction: discord.Interaction, adversario: discord.Member):
        if not interaction.user.voice:
            await interaction.response.send_message("Você precisa estar em um canal de voz para começar uma Batalha de Rap!", ephemeral=True)
            return
            
        if adversario.bot or adversario == interaction.user:
            await interaction.response.send_message("Escolha um adversário válido.", ephemeral=True)
            return

        if adversario.voice is None or adversario.voice.channel != interaction.user.voice.channel:
            await interaction.response.send_message("O seu adversário precisa estar no mesmo canal de voz que você!", ephemeral=True)
            return

        await interaction.response.defer()

        channel = interaction.user.voice.channel
        try:
            try:
                voice_client = await channel.connect()
            except discord.ClientException:
                voice_client = interaction.guild.voice_client
                if voice_client and voice_client.channel != channel:
                    await voice_client.move_to(channel)
        except Exception as e:
            await interaction.followup.send(f"❌ Não consegui conectar ao canal de voz. Detalhe do erro: {e}", ephemeral=True)
            return

        if voice_client and voice_client.is_playing():
            voice_client.stop()

        embed = discord.Embed(
            title="🎤🔥 BATALHA DE RAP 🔥🎤",
            description=f"{interaction.user.mention} desafiou {adversario.mention}!\n\nProcurando um Beat Pesado...",
            color=ERROR_COLOR
        )
        msg = await interaction.followup.send(embed=embed, wait=True)

        loop = asyncio.get_event_loop()
        try:
            # Pegando um beat famoso genérico no YouTube
            beat_search = "rap freestyle beat instrumental"
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{beat_search}", download=False))
            if 'entries' in data:
                data = data['entries'][0]

            source = discord.FFmpegPCMAudio(data['url'], **FFMPEG_OPTIONS)
            voice_client.play(source)

            # Round 1
            embed.description = f"**ROUND 1**\n\nÉ a vez de {interaction.user.mention} rimar!\n⏳ Você tem **30 segundos**!"
            await msg.edit(embed=embed)
            await asyncio.sleep(30)

            # Round 2
            embed.description = f"**ROUND 2**\n\nAgora é a vez de {adversario.mention} mandar a rima!\n⏳ Você tem **30 segundos**!"
            await msg.edit(embed=embed)
            await asyncio.sleep(30)

            if voice_client.is_connected():
                await voice_client.disconnect()

            # Poll
            embed.description = "🔥 **FIM DA BATALHA!** 🔥\n\nO Beat acabou! Quem mandou a melhor rima? Votem nas reações abaixo!"
            await msg.edit(embed=embed)
            
            poll_msg = await interaction.channel.send(f"Votação da Batalha de Rap: {interaction.user.mention} 🆚 {adversario.mention}\n\n1️⃣ para votar no Desafiante\n2️⃣ para votar no Adversário")
            await poll_msg.add_reaction("1️⃣")
            await poll_msg.add_reaction("2️⃣")

        except Exception as e:
            await interaction.channel.send(f"❌ Ocorreu um erro ao puxar o beat (FFmpeg/Yt-Dlp). {e}")
            if voice_client.is_connected():
                await voice_client.disconnect()

async def setup(bot: commands.Bot):
    await bot.add_cog(Karaoke(bot))
