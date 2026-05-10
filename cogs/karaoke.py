import asyncio
import aiohttp
import random
import shutil
import urllib.parse
import os
import uuid
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp

from config import BOT_COLOR, ERROR_COLOR, SUCCESS_COLOR, WARNING_COLOR, COIN_EMOJI

SWEET_COIN_EMOJI = "🍬"

_CACHE_DIR  = os.path.abspath('yt_cache')
_COOKIE_FILE = 'cookies.txt'
_NODE_PATH  = shutil.which('node') or shutil.which('nodejs')

def _get_ytdl_opts(is_web: bool, outtmpl: str | None = None) -> dict:
    opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'socket_timeout': 20,
    }
    
    if outtmpl:
        opts['outtmpl'] = outtmpl
    
    if is_web:
        opts.update({
            'cache_dir': _CACHE_DIR,
            'extractor_args': {'youtube': {'player_client': ['web']}},
            'remote_components': ['ejs:github'],
        })
        if os.path.isfile(_COOKIE_FILE):
            opts['cookiefile'] = _COOKIE_FILE
        if _NODE_PATH:
            opts['js_runtimes'] = {'node': {'path': _NODE_PATH}}
    else:
        opts.update({
            'format': '18/best[vcodec!=none][acodec!=none][ext=mp4]/best',
            'extractor_args': {'youtube': {'player_client': ['android_vr', 'android']}},
        })
    
    return opts

async def obter_info_audio(loop: asyncio.AbstractEventLoop, query: str) -> tuple[str, str]:
    """ Busca apenas URL e Titulo (rápido, sem baixar) """
    estrategias = [
        ("Web+EJS+cookies", True),
        ("AndroidVR sem cookies", False),
    ]
    erros = []
    for nome, is_web in estrategias:
        try:
            opts = _get_ytdl_opts(is_web, None)
            def _extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    data = ydl.extract_info(query, download=False)
                    if not data: raise ValueError("Sem dados")
                    if 'entries' in data:
                        entries = [e for e in data.get('entries', []) if e]
                        if not entries: raise ValueError("Vazio")
                        data = entries[0]
                    url = data.get('webpage_url') or data.get('original_url') or data.get('url')
                    return url, data.get('title', query)
            return await loop.run_in_executor(None, _extract)
        except Exception as e:
            erros.append(str(e))
    raise Exception("Falha na busca: " + " | ".join(erros))

async def baixar_audio_local(loop: asyncio.AbstractEventLoop, query: str) -> tuple[str, str]:
    """ Baixa o áudio localmente e retorna filepath e título. """
    file_id = str(uuid.uuid4())[:8]
    outtmpl = f"karaoke_{file_id}_%(id)s.%(ext)s"
    
    estrategias = [
        ("Web+EJS+cookies", True),
        ("AndroidVR sem cookies", False),
    ]

    for nome, is_web in estrategias:
        try:
            opts = _get_ytdl_opts(is_web, outtmpl)
            def _download():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    data = ydl.extract_info(query, download=True)
                    if not data: raise ValueError("Sem dados")
                    if 'entries' in data:
                        entries = [e for e in data.get('entries', []) if e]
                        if not entries: raise ValueError("Vazio")
                        data = entries[0]
                    return ydl.prepare_filename(data), data.get('title', query)

            filepath, title = await loop.run_in_executor(None, _download)
            if filepath and os.path.isfile(filepath):
                return filepath, title
        except Exception:
            continue
    raise Exception("Todas as estratégias de download falharam.")


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
        self.queues = {}      # guild_id -> list of dicts
        self.current = {}     # guild_id -> dict
        self.loop_modes = {}  # guild_id -> 'off', 'track', 'queue'

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
            await interaction.followup.send(f"❌ Não consegui conectar ao canal: `{e}`", ephemeral=True)
            return None
        return vc

    def _after_play(self, err, guild: discord.Guild, text_channel: discord.TextChannel, filepath: str):
        if err:
            print(f"[Karaoke] Erro no player: {err}")
        
        loop_mode = self.loop_modes.get(guild.id, 'off')
        
        # Só deleta o arquivo se NÃO for loop da mesma música
        if loop_mode != 'track':
            if filepath and os.path.isfile(filepath):
                try: os.remove(filepath)
                except: pass
            
            # Se for loop queue, limpa o filepath para forçar download novamente e economizar espaço
            current = self.current.get(guild.id)
            if current:
                current['filepath'] = None

        # Chama a próxima música
        asyncio.run_coroutine_threadsafe(self._play_next(guild, text_channel), self.bot.loop)

    async def _play_next(self, guild: discord.Guild, text_channel: discord.TextChannel):
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            return
            
        queue = self.queues.setdefault(guild.id, [])
        loop_mode = self.loop_modes.setdefault(guild.id, 'off')
        current = self.current.get(guild.id)
        
        next_song = None
        
        if loop_mode == 'track' and current:
            next_song = current
        else:
            if loop_mode == 'queue' and current:
                queue.append(current)
                
            if queue:
                next_song = queue.pop(0)
                
        if not next_song:
            self.current.pop(guild.id, None)
            embed = discord.Embed(title="⏹️ Fila concluída", description="As músicas acabaram. Adicione mais com `/karaoke vplay`!", color=BOT_COLOR)
            await text_channel.send(embed=embed)
            return
            
        self.current[guild.id] = next_song
        
        try:
            # Baixa o áudio apenas quando for tocar (economiza espaço)
            if not next_song.get('filepath') or not os.path.isfile(next_song['filepath']):
                status = await text_channel.send(f"⬇️ Preparando: **{next_song['title']}**...")
                fp, title = await baixar_audio_local(self.bot.loop, next_song['url'])
                next_song['filepath'] = fp
                next_song['title'] = title
                await status.delete()
                
            fp = next_song['filepath']
            source = discord.FFmpegPCMAudio(fp, options="-vn")
            vc.play(source, after=lambda err: self._after_play(err, guild, text_channel, fp))
            
            embed = discord.Embed(
                title="🎶 Tocando Agora",
                description=f"**{next_song['title']}**\nAdicionado por: {next_song['user'].mention}",
                color=BOT_COLOR
            )
            await text_channel.send(embed=embed)
        except Exception as e:
            await text_channel.send(f"❌ Erro ao tocar **{next_song.get('title', 'música')}**: `{e}`")
            # Tenta a próxima se essa falhar
            await self._play_next(guild, text_channel)

    # ─────────────────────────────────────────────────────────────────────────
    karaoke_group = app_commands.Group(name="karaoke", description="Sistema de Karaokê e Música")

    @karaoke_group.command(name="vplay", description="Toca uma música ou adiciona à fila")
    @app_commands.describe(musica="Nome ou URL da música")
    async def tocar(self, interaction: discord.Interaction, musica: str):
        await interaction.response.defer()
        vc = await self._conectar_voz(interaction)
        if vc is None: return

        guild_id = interaction.guild_id
        self.queues.setdefault(guild_id, [])
        self.loop_modes.setdefault(guild_id, 'off')

        status_msg = await interaction.followup.send(f"🔍 Buscando por **{musica}**...")
        try:
            query = musica if musica.startswith("http") else f"ytsearch:{musica}"
            url, title = await obter_info_audio(self.bot.loop, query)
        except Exception as e:
            await status_msg.edit(content=f"❌ Erro ao buscar **{musica}**:\n> {e}")
            return

        item = {
            'url': url,
            'title': title,
            'user': interaction.user,
            'filepath': None
        }

        if vc.is_playing() or vc.is_paused():
            self.queues[guild_id].append(item)
            embed = discord.Embed(
                title="✅ Adicionado à Fila",
                description=f"**{title}**",
                color=SUCCESS_COLOR
            )
            embed.set_footer(text=f"Posição na fila: {len(self.queues[guild_id])}")
            await status_msg.edit(content=None, embed=embed)
        else:
            self.queues[guild_id].append(item)
            await status_msg.delete()
            await self._play_next(interaction.guild, interaction.channel)

    @karaoke_group.command(name="skip", description="Pula a música atual")
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop() # Isso aciona o after_play que toca a próxima
            await interaction.response.send_message("⏭️ Música pulada!", ephemeral=False)
        else:
            await interaction.response.send_message("Não há nada tocando para pular.", ephemeral=True)

    @karaoke_group.command(name="pause", description="Pausa a música atual")
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Música pausada!")
        else:
            await interaction.response.send_message("Não há nada tocando para pausar.", ephemeral=True)

    @karaoke_group.command(name="resume", description="Despausa a música atual")
    async def resume(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Música despausada!")
        else:
            await interaction.response.send_message("A música não está pausada.", ephemeral=True)

    @karaoke_group.command(name="fila", description="Mostra a fila de músicas")
    async def fila(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        queue = self.queues.get(guild_id, [])
        current = self.current.get(guild_id)
        
        if not current and not queue:
            await interaction.response.send_message("A fila está vazia.", ephemeral=True)
            return
            
        desc = ""
        if current:
            desc += f"**Tocando agora:**\n🎶 {current['title']} ({current['user'].mention})\n\n"
            
        if queue:
            desc += "**Próximas:**\n"
            for i, item in enumerate(queue[:10]):
                desc += f"`{i+1}.` {item['title']} ({item['user'].mention})\n"
            if len(queue) > 10:
                desc += f"...e mais {len(queue) - 10} músicas."
                
        embed = discord.Embed(title="📜 Fila de Reprodução", description=desc, color=BOT_COLOR)
        mode = self.loop_modes.get(guild_id, 'off')
        if mode != 'off':
            embed.set_footer(text=f"🔁 Loop ativado: {mode}")
            
        await interaction.response.send_message(embed=embed)

    @karaoke_group.command(name="loop", description="Muda o modo de repetição")
    @app_commands.describe(modo="Qual tipo de loop deseja ativar")
    async def loop(self, interaction: discord.Interaction, modo: Literal['Desativado', 'Música', 'Fila']):
        guild_id = interaction.guild_id
        if modo == 'Desativado':
            self.loop_modes[guild_id] = 'off'
            await interaction.response.send_message("➡️ Loop **desativado**.")
        elif modo == 'Música':
            self.loop_modes[guild_id] = 'track'
            await interaction.response.send_message("🔂 Loop de **Música** ativado!")
        elif modo == 'Fila':
            self.loop_modes[guild_id] = 'queue'
            await interaction.response.send_message("🔁 Loop de **Fila** ativado!")

    @karaoke_group.command(name="parar", description="Para a música, limpa a fila e sai do canal de voz")
    async def parar(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        self.queues[guild_id] = []
        self.loop_modes[guild_id] = 'off'
        self.current.pop(guild_id, None)
        
        vc = interaction.guild.voice_client
        if vc and vc.is_connected():
            vc.stop()
            await vc.disconnect()
            await interaction.response.send_message("👋 Fila limpa e música parada. Saindo do canal!")
        else:
            await interaction.response.send_message("Eu não estou em um canal de voz.", ephemeral=True)

    @karaoke_group.command(name="letra", description="Busca a letra de uma música")
    @app_commands.describe(musica="Nome da música (ex: Artista - Música)")
    async def letra(self, interaction: discord.Interaction, musica: str):
        await interaction.response.defer()
        
        url = f"https://lrclib.net/api/search?q={urllib.parse.quote(musica)}"
        lyrics = None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data: lyrics = data[0].get('plainLyrics') or data[0].get('syncedLyrics')
        except Exception: pass
        
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

    @app_commands.command(name="batalha_rap", description="Desafie alguém para uma Batalha de Rap!")
    @app_commands.describe(adversario="O usuário que você vai desafiar")
    async def batalha_rap(self, interaction: discord.Interaction, adversario: discord.Member):
        if not interaction.user.voice:
            return await interaction.response.send_message("Você precisa estar em um canal de voz!", ephemeral=True)
        if adversario.bot or adversario == interaction.user:
            return await interaction.response.send_message("Escolha um adversário válido.", ephemeral=True)
        if not adversario.voice or adversario.voice.channel != interaction.user.voice.channel:
            return await interaction.response.send_message("Seu adversário precisa estar no mesmo canal!", ephemeral=True)

        await interaction.response.defer()
        vc = await self._conectar_voz(interaction)
        if vc is None: return

        embed = discord.Embed(
            title="🎤🔥 BATALHA DE RAP 🔥🎤",
            description=f"{interaction.user.mention} desafiou {adversario.mention}!\n\nProcurando Beat...",
            color=ERROR_COLOR
        )
        msg = await interaction.followup.send(embed=embed, wait=True)

        filepath = None
        for q in ["ytsearch:rap freestyle beat instrumental", "ytsearch:hip hop beat 2024"]:
            try:
                filepath, beat_title = await baixar_audio_local(self.bot.loop, q)
                break
            except Exception:
                continue

        if not filepath:
            await msg.edit(embed=None, content="❌ Não encontrei nenhum beat. Tente novamente.")
            if vc.is_connected(): await vc.disconnect()
            return

        def _depois_de_tocar_beat(err, fp):
            if os.path.isfile(fp):
                try: os.remove(fp)
                except: pass

        try:
            vc.play(discord.FFmpegPCMAudio(filepath, options="-vn"), after=lambda err: _depois_de_tocar_beat(err, filepath))
            
            embed.description = (f"🎵 **{beat_title}**\n\n**ROUND 1** — {interaction.user.mention} rima!\n⏳ 30s")
            await msg.edit(embed=embed)
            await asyncio.sleep(30)

            embed.description = (f"🎵 **{beat_title}**\n\n**ROUND 2** — {adversario.mention} rima!\n⏳ 30s")
            await msg.edit(embed=embed)
            await asyncio.sleep(30)

            if vc.is_connected(): await vc.disconnect()

            embed.description = "🔥 **FIM!** Quem mandou melhor? Vote abaixo!"
            await msg.edit(embed=embed)
            poll = await interaction.channel.send(f"**{interaction.user.mention} 🆚 {adversario.mention}**\n1️⃣ Desafiante | 2️⃣ Adversário")
            await poll.add_reaction("1️⃣")
            await poll.add_reaction("2️⃣")
        except Exception as e:
            await interaction.channel.send(f"❌ Erro na batalha: `{e}`")
            if vc.is_connected(): await vc.disconnect()

async def setup(bot: commands.Bot):
    await bot.add_cog(Karaoke(bot))
