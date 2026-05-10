import asyncio
import aiohttp
import random
import shutil
import urllib.parse
import os
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

from config import BOT_COLOR, ERROR_COLOR, SUCCESS_COLOR, WARNING_COLOR, COIN_EMOJI

SWEET_COIN_EMOJI = "🍬"

# ─────────────────────────────────────────────────────────────────────────────
# SOLUÇÃO DEFINITIVA
#
# Contexto: SquareCloud usa IPs de datacenter bloqueados pelo YouTube.
#
# O que funciona:
#   yt-dlp + web client + cookies.txt + Node.js (js_runtimes) +
#   EJS solver (cache local em yt_cache/ — commitado no repositório)
#
# A chave: cache_dir aponta para ./yt_cache que contém o script EJS
#   pré-baixado. Assim não há download do GitHub em runtime → confiável.
#
# Fallback: android_vr sem cookies (para testes locais em IPs residenciais).
# ─────────────────────────────────────────────────────────────────────────────

# Caminhos
_CACHE_DIR  = os.path.abspath('yt_cache')   # contém challenge-solver/lib.json
_COOKIE_FILE = 'cookies.txt'
_NODE_PATH  = shutil.which('node') or shutil.which('nodejs')

print(f"[Karaoke] Node.js: {_NODE_PATH or 'NÃO ENCONTRADO'}")
print(f"[Karaoke] Cache EJS: {os.path.join(_CACHE_DIR, 'challenge-solver', 'lib.json')} "
      f"→ {'✅' if os.path.isfile(os.path.join(_CACHE_DIR, 'challenge-solver', 'lib.json')) else '❌ AUSENTE'}")


def _make_ytdl_web() -> yt_dlp.YoutubeDL:
    """
    Web client + cookies + Node.js + EJS local — funciona em datacenter.
    """
    opts: dict = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'socket_timeout': 20,
        'cache_dir': _CACHE_DIR,
        'extractor_args': {'youtube': {'player_client': ['web']}},
        'remote_components': ['ejs:github'],    # usa cache se disponível
    }
    if os.path.isfile(_COOKIE_FILE):
        opts['cookiefile'] = _COOKIE_FILE
    if _NODE_PATH:
        opts['js_runtimes'] = {'node': {'path': _NODE_PATH}}
    return yt_dlp.YoutubeDL(opts)


def _make_ytdl_android() -> yt_dlp.YoutubeDL:
    """
    Fallback android_vr sem cookies — funciona em IPs residenciais / locais.
    """
    return yt_dlp.YoutubeDL({
        'format': '18/best[vcodec!=none][acodec!=none][ext=mp4]/best',
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'socket_timeout': 20,
        'extractor_args': {'youtube': {'player_client': ['android_vr', 'android']}},
        # SEM cookiefile — android não suporta cookies
    })


YTDL_WEB     = _make_ytdl_web()
YTDL_ANDROID = _make_ytdl_android()

FFMPEG_OPTIONS = {
    'before_options': (
        '-reconnect 1 '
        '-reconnect_streamed 1 '
        '-reconnect_delay_max 5 '
        '-timeout 20000000'
    ),
    'options': '-vn -bufsize 64k'
}


async def extrair_url_audio(loop: asyncio.AbstractEventLoop, query: str) -> tuple[str, str]:
    """
    Tenta extrair URL de stream de áudio em ordem de prioridade.
    Retorna (url, titulo) ou levanta Exception.
    """
    estrategias = [
        ("Web+EJS+cookies (datacenter)", YTDL_WEB),
        ("AndroidVR sem cookies (local)",  YTDL_ANDROID),
    ]

    erros: list[str] = []
    for nome, inst in estrategias:
        try:
            print(f"[Karaoke] Tentando: {nome}")
            data = await loop.run_in_executor(
                None, lambda i=inst, q=query: i.extract_info(q, download=False)
            )
            if not data:
                raise ValueError("Sem dados retornados")
            if 'entries' in data:
                entries = [e for e in data.get('entries', []) if e]
                if not entries:
                    raise ValueError("Lista de resultados vazia")
                data = entries[0]
            url = data.get('url')
            if not url:
                raise ValueError("URL de stream não encontrada")
            title = data.get('title', query)
            print(f"[Karaoke] ✅ {nome} → '{title}'")
            return url, title
        except Exception as e:
            msg = str(e)
            print(f"[Karaoke] ❌ {nome} falhou: {msg}")
            erros.append(f"**{nome}**: {msg}")

    raise Exception("Todas as estratégias falharam:\n" + "\n".join(erros))


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

    async def get_lyrics(self, query: str) -> str | None:
        url = f"https://lrclib.net/api/search?q={urllib.parse.quote(query)}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data:
                            return data[0].get('plainLyrics') or data[0].get('syncedLyrics')
        except Exception as e:
            print(f"[Karaoke] Erro na letra: {e}")
        return None

    async def _conectar_voz(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        if not interaction.user.voice:
            await interaction.followup.send("❌ Você precisa estar em um canal de voz primeiro!", ephemeral=True)
            return None
        channel = interaction.user.voice.channel
        try:
            try:
                vc = await channel.connect()
            except discord.ClientException:
                vc = interaction.guild.voice_client
                if vc and vc.channel != channel:
                    await vc.move_to(channel)
        except Exception as e:
            await interaction.followup.send(f"❌ Não consegui conectar ao canal de voz: `{e}`", ephemeral=True)
            return None
        if vc and vc.is_playing():
            vc.stop()
        return vc

    # ─────────────────────────────────────────────────────────────────────────
    karaoke_group = app_commands.Group(name="karaoke", description="Sistema de Karaokê")

    @karaoke_group.command(name="vplay", description="Entra no canal de voz e toca uma música/karaokê do YouTube")
    @app_commands.describe(musica="Nome ou URL da música que deseja tocar")
    async def tocar(self, interaction: discord.Interaction, musica: str):
        await interaction.response.defer()
        vc = await self._conectar_voz(interaction)
        if vc is None:
            return

        status_msg = await interaction.followup.send(f"🔍 Procurando por **{musica}**...")
        loop = asyncio.get_event_loop()
        query = musica if musica.startswith("http") else f"ytsearch:{musica}"

        try:
            stream_url, title = await extrair_url_audio(loop, query)
        except Exception as e:
            await status_msg.edit(content=f"❌ Não encontrei áudio para **{musica}**.\n> {e}")
            if vc.is_connected():
                await vc.disconnect()
            return

        try:
            source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
            vc.play(source, after=lambda err: print(f"[Karaoke] Player error: {err}") if err else None)
            embed = discord.Embed(
                title="🎶 Karaokê Iniciado",
                description=f"Tocando agora: **{title}**",
                color=BOT_COLOR
            )
            embed.set_footer(text="Use /karaoke parar para encerrar.")
            await status_msg.edit(content=None, embed=embed)
        except Exception as e:
            await status_msg.edit(content=f"❌ Erro ao iniciar reprodução: `{e}`")
            if vc.is_connected():
                await vc.disconnect()

    @karaoke_group.command(name="parar", description="Para a música e sai do canal de voz")
    async def parar(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            await vc.disconnect()
            await interaction.response.send_message("Karaokê encerrado! 👋")
        else:
            await interaction.response.send_message("Não estou em um canal de voz.", ephemeral=True)

    @karaoke_group.command(name="letra", description="Busca a letra de uma música")
    @app_commands.describe(musica="Nome da música (ex: Artista - Música)")
    async def letra(self, interaction: discord.Interaction, musica: str):
        await interaction.response.defer()
        lyrics = await self.get_lyrics(musica)
        if lyrics:
            if len(lyrics) > 4000:
                lyrics = lyrics[:4000] + "\n...\n*(Cortada por limite de caracteres)*"
            embed = discord.Embed(title=f"🎤 Letra: {musica.title()}", description=lyrics, color=BOT_COLOR)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ Letra não encontrada. Tente: `Artista - Música`.")

    @karaoke_group.command(name="minigame", description="Complete o trecho e ganhe Sweet Coins!")
    async def minigame(self, interaction: discord.Interaction):
        await interaction.response.defer()
        song = random.choice(MINIGAME_SONGS)
        embed = discord.Embed(
            title="🎤 Qual é a música?",
            description=f"Complete nos próximos **20 segundos**:\n\n🎵 *\"{song['trecho']}\"*",
            color=WARNING_COLOR
        )
        await interaction.followup.send(embed=embed)

        def check(m: discord.Message):
            return m.channel == interaction.channel and not m.author.bot

        end_time = asyncio.get_event_loop().time() + 20.0
        while True:
            timeout = end_time - asyncio.get_event_loop().time()
            if timeout <= 0:
                await interaction.channel.send(f"⏳ Tempo esgotado! Resposta: **{song['resposta']}**.")
                return
            try:
                msg = await self.bot.wait_for('message', timeout=timeout, check=check)
                if song['resposta'].lower() in msg.content.lower():
                    reward = random.randint(30, 80)
                    await self.bot.db.add_coins(msg.author.id, interaction.guild_id, reward)
                    await interaction.channel.send(
                        f"🎉 Correto, {msg.author.mention}! Era **{song['resposta']}**!\n"
                        f"Você ganhou {SWEET_COIN_EMOJI} **{reward} Sweet Coins**!"
                    )
                    return
            except asyncio.TimeoutError:
                await interaction.channel.send(f"⏳ Tempo esgotado! Resposta: **{song['resposta']}**.")
                return

    # ─────────────────────────────────────────────────────────────────────────
    @app_commands.command(name="batalha_rap", description="Desafie alguém para uma Batalha de Rap!")
    @app_commands.describe(adversario="O usuário que você vai desafiar")
    async def batalha_rap(self, interaction: discord.Interaction, adversario: discord.Member):
        if not interaction.user.voice:
            await interaction.response.send_message("Você precisa estar em um canal de voz!", ephemeral=True)
            return
        if adversario.bot or adversario == interaction.user:
            await interaction.response.send_message("Escolha um adversário válido.", ephemeral=True)
            return
        if not adversario.voice or adversario.voice.channel != interaction.user.voice.channel:
            await interaction.response.send_message("Seu adversário precisa estar no mesmo canal!", ephemeral=True)
            return

        await interaction.response.defer()
        vc = await self._conectar_voz(interaction)
        if vc is None:
            return

        embed = discord.Embed(
            title="🎤🔥 BATALHA DE RAP 🔥🎤",
            description=f"{interaction.user.mention} desafiou {adversario.mention}!\n\nProcurando Beat...",
            color=ERROR_COLOR
        )
        msg = await interaction.followup.send(embed=embed, wait=True)

        loop = asyncio.get_event_loop()
        stream_url, beat_title = None, "Beat"
        for q in ["ytsearch:rap freestyle beat instrumental", "ytsearch:hip hop beat 2024"]:
            try:
                stream_url, beat_title = await extrair_url_audio(loop, q)
                break
            except Exception:
                continue

        if not stream_url:
            await msg.edit(embed=None, content="❌ Não encontrei nenhum beat. Tente novamente.")
            if vc.is_connected():
                await vc.disconnect()
            return

        try:
            vc.play(discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS))

            embed.description = (f"🎵 **{beat_title}**\n\n**ROUND 1** — {interaction.user.mention} rima!\n⏳ 30s")
            await msg.edit(embed=embed)
            await asyncio.sleep(30)

            embed.description = (f"🎵 **{beat_title}**\n\n**ROUND 2** — {adversario.mention} rima!\n⏳ 30s")
            await msg.edit(embed=embed)
            await asyncio.sleep(30)

            if vc.is_connected():
                await vc.disconnect()

            embed.description = "🔥 **FIM!** Quem mandou melhor? Vote abaixo!"
            await msg.edit(embed=embed)
            poll = await interaction.channel.send(
                f"**{interaction.user.mention} 🆚 {adversario.mention}**\n1️⃣ Desafiante | 2️⃣ Adversário"
            )
            await poll.add_reaction("1️⃣")
            await poll.add_reaction("2️⃣")
        except Exception as e:
            await interaction.channel.send(f"❌ Erro na batalha: `{e}`")
            if vc.is_connected():
                await vc.disconnect()


async def setup(bot: commands.Bot):
    await bot.add_cog(Karaoke(bot))
