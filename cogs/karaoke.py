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
# ESTRATÉGIA DE EXTRAÇÃO
#
# Problema: SquareCloud usa IPs de datacenter que o YouTube bloqueia.
#   - android_vr/android: não suportam cookiefile → youtube pede "sign in"
#   - web + cookies: precisa de EJS (External JS Solver) para descriptografar DASH
#
# Solução: web client + cookies + Node.js + EJS solver (baixado do GitHub/npm).
#   - remote_components: ['ejs:github'] → yt-dlp baixa e cacheia o solver automaticamente
#   - js_runtimes: {'node': {'path': ...}} → usa o Node.js instalado
#
# Fallback: android_vr sem cookies (funciona em IPs residenciais/locais).
# ─────────────────────────────────────────────────────────────────────────────

def _find_node() -> str | None:
    """Encontra o executável do Node.js no PATH."""
    return shutil.which('node')


def _make_ytdl_web(node_path: str | None) -> yt_dlp.YoutubeDL:
    """
    Estratégia principal: web client + cookies + EJS via Node.js.
    Funciona em IPs de datacenter (SquareCloud) com cookies válidos.
    """
    opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'socket_timeout': 20,
        'extractor_args': {'youtube': {'player_client': ['web']}},
        'remote_components': ['ejs:github'],   # baixa solver automaticamente
    }
    if os.path.isfile('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'
    if node_path:
        opts['js_runtimes'] = {'node': {'path': node_path}}
    return yt_dlp.YoutubeDL(opts)


def _make_ytdl_android_vr() -> yt_dlp.YoutubeDL:
    """
    Fallback: android_vr sem cookies — formato 18 (progressivo, sem DASH, sem JS).
    Funciona em IPs residenciais/locais. Em datacenter pode pedir "sign in".
    """
    return yt_dlp.YoutubeDL({
        'format': '18/best[vcodec!=none][acodec!=none][ext=mp4]/best[vcodec!=none][acodec!=none]/best',
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'socket_timeout': 20,
        'extractor_args': {'youtube': {'player_client': ['android_vr', 'android']}},
        # SEM cookiefile — android_vr não suporta cookies
    })


# Instâncias globais (criadas uma vez, não por requisição)
_NODE_PATH = _find_node()
print(f"[Karaoke] Node.js encontrado em: {_NODE_PATH or 'NÃO ENCONTRADO'}")

YTDL_WEB      = _make_ytdl_web(_NODE_PATH)
YTDL_ANDROID  = _make_ytdl_android_vr()

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
    Extrai URL de stream de áudio para a query dada.
    Retorna (url, titulo). Levanta Exception se tudo falhar.
    """
    estrategias = [
        ("Web+EJS (datacenter)",  YTDL_WEB),
        ("AndroidVR (local/residencial)", YTDL_ANDROID),
    ]

    ultimo_erro = None
    for nome, inst in estrategias:
        try:
            print(f"[Karaoke] Tentando: {nome} | query: {query}")
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
            print(f"[Karaoke] ❌ {nome} falhou: {e}")
            ultimo_erro = e
            continue

    raise Exception(f"Todas as estratégias falharam. Último erro: {ultimo_erro}")


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
        """Conecta ao canal de voz do usuário. Retorna VoiceClient ou None."""
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
            await status_msg.edit(content=f"❌ Não encontrei nenhum áudio disponível para **{musica}**.\n> {e}")
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
            embed.set_footer(text="Use /karaoke parar para encerrar a música.")
            await status_msg.edit(content=None, embed=embed)
        except Exception as e:
            await status_msg.edit(content=f"❌ Erro ao iniciar a reprodução: `{e}`")
            if vc.is_connected():
                await vc.disconnect()

    @karaoke_group.command(name="parar", description="Para a música atual e sai do canal de voz")
    async def parar(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            await vc.disconnect()
            await interaction.response.send_message("Karaokê encerrado. Saindo do canal de voz! 👋")
        else:
            await interaction.response.send_message("Eu não estou em um canal de voz.", ephemeral=True)

    @karaoke_group.command(name="letra", description="Busca a letra de uma música")
    @app_commands.describe(musica="Nome da música (e artista para ser mais específico)")
    async def letra(self, interaction: discord.Interaction, musica: str):
        await interaction.response.defer()
        lyrics = await self.get_lyrics(musica)

        if lyrics:
            if len(lyrics) > 4000:
                lyrics = lyrics[:4000] + "\n...\n*(Letra muito longa, cortada.)*"
            embed = discord.Embed(title=f"🎤 Letra: {musica.title()}", description=lyrics, color=BOT_COLOR)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send("❌ Não encontrei a letra. Tente: `Artista - Música`.")

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

        def check(m: discord.Message):
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
                    await interaction.channel.send(
                        f"🎉 Correto, {msg.author.mention}! A letra era **{song['resposta']}**!\n"
                        f"Você ganhou {SWEET_COIN_EMOJI} **{reward} Sweet Coins**!"
                    )
                    return
            except asyncio.TimeoutError:
                await interaction.channel.send(f"⏳ Tempo esgotado! Ninguém acertou. A resposta era: **{song['resposta']}**.")
                return

    # ─────────────────────────────────────────────────────────────────────────
    # Batalha de Rap
    # ─────────────────────────────────────────────────────────────────────────
    @app_commands.command(name="batalha_rap", description="Desafie alguém para uma Batalha de Rap no canal de voz!")
    @app_commands.describe(adversario="O usuário que você vai desafiar")
    async def batalha_rap(self, interaction: discord.Interaction, adversario: discord.Member):
        if not interaction.user.voice:
            await interaction.response.send_message("Você precisa estar em um canal de voz!", ephemeral=True)
            return

        if adversario.bot or adversario == interaction.user:
            await interaction.response.send_message("Escolha um adversário válido.", ephemeral=True)
            return

        if adversario.voice is None or adversario.voice.channel != interaction.user.voice.channel:
            await interaction.response.send_message("Seu adversário precisa estar no mesmo canal de voz!", ephemeral=True)
            return

        await interaction.response.defer()

        vc = await self._conectar_voz(interaction)
        if vc is None:
            return

        embed = discord.Embed(
            title="🎤🔥 BATALHA DE RAP 🔥🎤",
            description=f"{interaction.user.mention} desafiou {adversario.mention}!\n\nProcurando um Beat Pesado...",
            color=ERROR_COLOR
        )
        msg = await interaction.followup.send(embed=embed, wait=True)

        loop = asyncio.get_event_loop()
        beat_queries = [
            "ytsearch:rap freestyle beat instrumental no copyright",
            "ytsearch:hip hop beat instrumental 2024",
            "ytsearch:trap beat instrumental",
        ]

        stream_url = None
        beat_title = "Beat"
        for q in beat_queries:
            try:
                stream_url, beat_title = await extrair_url_audio(loop, q)
                break
            except Exception as e:
                print(f"[BatalhaRap] Beat falhou '{q}': {e}")
                continue

        if not stream_url:
            await msg.edit(embed=None, content="❌ Não consegui encontrar nenhum beat. Tente novamente mais tarde.")
            if vc.is_connected():
                await vc.disconnect()
            return

        try:
            source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
            vc.play(source)

            embed.description = (
                f"🎵 Beat: **{beat_title}**\n\n"
                f"**ROUND 1** — É a vez de {interaction.user.mention} rimar!\n"
                f"⏳ Você tem **30 segundos**!"
            )
            await msg.edit(embed=embed)
            await asyncio.sleep(30)

            embed.description = (
                f"🎵 Beat: **{beat_title}**\n\n"
                f"**ROUND 2** — Agora é a vez de {adversario.mention} mandar a rima!\n"
                f"⏳ Você tem **30 segundos**!"
            )
            await msg.edit(embed=embed)
            await asyncio.sleep(30)

            if vc.is_connected():
                await vc.disconnect()

            embed.description = (
                "🔥 **FIM DA BATALHA!** 🔥\n\n"
                "O Beat acabou! Quem mandou a melhor rima?\nVotem nas reações abaixo!"
            )
            await msg.edit(embed=embed)

            poll_msg = await interaction.channel.send(
                f"**Votação:** {interaction.user.mention} 🆚 {adversario.mention}\n\n"
                f"1️⃣ → Desafiante | 2️⃣ → Adversário"
            )
            await poll_msg.add_reaction("1️⃣")
            await poll_msg.add_reaction("2️⃣")

        except Exception as e:
            await interaction.channel.send(f"❌ Erro durante a batalha: `{e}`")
            if vc.is_connected():
                await vc.disconnect()


async def setup(bot: commands.Bot):
    await bot.add_cog(Karaoke(bot))
