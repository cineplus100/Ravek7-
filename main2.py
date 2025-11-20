# main.py -- RV7 completo: XP híbrido + Loja Visual + Relatórios + Welcome + Slash commands
import os
import json
import random
import time
import asyncio
from collections import deque, defaultdict
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands, Embed
from discord.ext import commands, tasks

# ---------------- CONFIG ----------------
TOKEN = "SEU_TOKEN_AQUI"  # <- coloque seu token de teste aqui
GUILD_IDS = None  # se quiser registrar os comandos somente em guilds específicas, coloque [ID1, ID2]
CANAL_RELATORIOS_NAME = "relatorios-rv7"
CANAL_BEM_VINDAS_NAME = "🏡│boas-vindas"
CARGO_BOAS_VINDAS = "🧩 Recruta RV7"

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
INICIO_BOT = datetime.now(timezone.utc)

# ---------------- DATABASE (JSON) ----------------
DB_PATH = "database.json"

def ensure_db():
    if not os.path.exists(DB_PATH):
        initial = {"users": {}, "loja": {}, "meta": {}}
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(initial, f, indent=4, ensure_ascii=False)

def load_db():
    ensure_db()
    with open(DB_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {"users": {}, "loja": {}, "meta": {}}

def save_db(db):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

db = load_db()

# Preenche loja padrão se vazio
if not db.get("loja"):
    db["loja"] = {
        "badge_ouro": {"nome": "⭐ Badge de Ouro", "preco": 300},
        "badge_diamante": {"nome": "💎 Badge de Diamante", "preco": 600},
        "badge_fogo": {"nome": "🔥 Badge de Fogo", "preco": 900},
        "badge_real": {"nome": "👑 Badge Real", "preco": 1500},
        "moldura_azul": {"nome": "🟦 Moldura Azul Neon", "preco": 500},
        "moldura_vermelha": {"nome": "🟥 Moldura Vermelha Inferno", "preco": 800},
        "moldura_verde": {"nome": "🟩 Moldura Verde Matrix", "preco": 1200},
        "moldura_roxa": {"nome": "🟪 Moldura Roxa Premium", "preco": 2000},
        "cor_azul": {"nome": "🔵 Nome Azul", "preco": 400},
        "cor_vermelha": {"nome": "🔴 Nome Vermelho", "preco": 400},
        "cor_roxa": {"nome": "🟣 Nome Roxo", "preco": 700}
    }
    save_db(db)

# ---------------- XP / LOJA CONFIG ----------------
XP_MIN = 5
XP_MAX = 15
BONUS_THRESHOLD = 20     # mensagens na última hora para bônus
BONUS_XP = 300
LEVEL_MULT = 120         # xp necessário por nível = level * LEVEL_MULT
COOLDOWN_SECONDS = 10    # cooldown entre ganhos de XP por usuário (segundos)

# runtime memory
messages_window = defaultdict(lambda: defaultdict(lambda: deque()))  # messages_window[guild_id][user_id] -> deque timestamps
_last_xp_time = {}  # (guild_id, user_id) -> last_timestamp_float

# runtime message counters for reports (per-guild)
MESSAGES_COUNTER = defaultdict(lambda: defaultdict(int))  # MESSAGES_COUNTER[guild_id][user_id] = count

# ---------------- HELPERS DB ----------------
def ensure_user(guild_id: int, user_id: int):
    gid = str(guild_id)
    uid = str(user_id)
    if "users" not in db:
        db["users"] = {}
    if uid not in db["users"]:
        db["users"][uid] = {
            "xp": 0,
            "level": 1,
            "mensagens_hora": 0,
            "ultimo_reset": int(time.time()),
            "itens": [],   # badges
            "frame": "",
            "color": "",
            "last_bonus_ts": None
        }
        save_db(db)

def get_user(uid_int: int):
    uid = str(uid_int)
    ensure_user(0, uid_int)
    return db["users"][uid]

def update_user_field(uid_int: int, field: str, value):
    uid = str(uid_int)
    ensure_user(0, uid_int)
    db["users"][uid][field] = value
    save_db(db)

def add_xp_to_user(uid_int: int, amount: int):
    user = get_user(uid_int)
    user["xp"] = user.get("xp", 0) + amount
    # level up loop
    lvl = user.get("level", 1)
    leveled = False
    while user["xp"] >= lvl * LEVEL_MULT:
        user["level"] = lvl + 1
        lvl += 1
        leveled = True
    save_db(db)
    return leveled, lvl

# ---------------- PROGRESS BAR ----------------
def xp_needed_for_level(level: int) -> int:
    return max(1, level * LEVEL_MULT)

def barra_progress(xp: int, level: int, tamanho: int = 20) -> str:
    xp_max = xp_needed_for_level(level)
    p = int((xp / xp_max) * tamanho)
    p = max(0, min(tamanho, p))
    return "█" * p + "░" * (tamanho - p)

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    print(f"{bot.user} online! (RV7 completo)")
    # registra/sincroniza comandos slash
    try:
        if GUILD_IDS:
            for gid in GUILD_IDS:
                await bot.tree.sync(guild=discord.Object(id=gid))
        else:
            await bot.tree.sync()
        print("Slash commands sincronizados.")
    except Exception as e:
        print("Erro ao sincronizar slash commands:", e)
    # start periodic tasks
    if not periodic_relatorio.is_running():
        periodic_relatorio.start()
    print("Tarefas iniciadas.")

@bot.event
async def on_member_join(member: discord.Member):
    # Mensagem de boas-vindas
    try:
        canal = discord.utils.get(member.guild.text_channels, name=CANAL_BEM_VINDAS_NAME)
        cargo = discord.utils.get(member.guild.roles, name=CARGO_BOAS_VINDAS)
        if canal and canal.permissions_for(member.guild.me).send_messages:
            await canal.send(f"👋 Bem-vindo ao clã RV7, {member.mention}! Leia as regras e se apresente 😊")
        if cargo and member.guild.me.top_role > cargo:
            try:
                await member.add_roles(cargo)
            except Exception:
                pass
    except Exception as e:
        print("Erro on_member_join:", e)

# ---------------- XP: on_message (híbrido) ----------------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        await bot.process_commands(message)
        return

    if not message.guild:
        await bot.process_commands(message)
        return

    guild_id = message.guild.id
    user_id = message.author.id

    # contagem para relatório
    MESSAGES_COUNTER[guild_id][user_id] += 1

    # janela de msgs para bônus
    now_ts = int(time.time())
    dq = messages_window[guild_id][user_id]
    dq.append(now_ts)
    # limpa >1h
    cutoff = now_ts - 3600
    while dq and dq[0] < cutoff:
        dq.popleft()

    # cooldown entre XP
    key = (guild_id, user_id)
    last = _last_xp_time.get(key, 0)
    if time.time() - last >= COOLDOWN_SECONDS:
        ganho = random.randint(XP_MIN, XP_MAX)
        leveled, new_level = add_xp_to_user(user_id, ganho)
        _last_xp_time[key] = time.time()
        # tenta avisar level up
        if leveled:
            try:
                await message.channel.send(f"⭐ **{message.author.mention} subiu para o nível {new_level}!**")
            except Exception:
                pass

    # checa bônus de atividade (20 msgs na última hora) - uma vez por hora
    dq_len = len(messages_window[guild_id][user_id])
    if dq_len >= BONUS_THRESHOLD:
        user = get_user(user_id)
        # verifica last_bonus_ts (em epoch)
        last_bonus = user.get("last_bonus_ts")
        allowed = False
        if last_bonus:
            try:
                if time.time() - float(last_bonus) >= 3600:
                    allowed = True
            except Exception:
                allowed = True
        else:
            allowed = True

        if allowed:
            add_xp_to_user(user_id, BONUS_XP)
            update_user_field(user_id, "last_bonus_ts", str(int(time.time())))
            # limpa deque pra evitar retrigger
            messages_window[guild_id][user_id].clear()
            try:
                await message.channel.send(f"💥 **BÔNUS:** {message.author.mention} recebeu +{BONUS_XP} XP por atividade intensa!")
            except Exception:
                pass

    await bot.process_commands(message)

# ---------------- SLASH COMMANDS ----------------
# /perfil
@bot.tree.command(name="perfil", description="Mostra seu perfil (XP, nível, itens visuais)")
@app_commands.describe(membro="Escolha um membro (opcional)")
async def perfil(interaction: discord.Interaction, membro: discord.Member = None):
    membro = membro or interaction.user
    ensure_user(interaction.guild.id, membro.id)
    user = get_user(membro.id)
    xp = user.get("xp", 0)
    level = user.get("level", 1)
    itens = user.get("itens", [])
    frame = user.get("frame", "Nenhuma")
    color = user.get("color", "Padrão")
    barra = barra_progress(xp, level, tamanho=20)

    embed = Embed(title=f"🌐 Perfil — {membro.display_name}", color=0x1E90FF)
    try:
        if membro.avatar:
            embed.set_thumbnail(url=membro.avatar.url)
    except Exception:
        pass
    embed.add_field(name="⭐ Nível", value=str(level), inline=True)
    embed.add_field(name="⚡ XP", value=f"{xp}/{xp_needed_for_level(level)}", inline=True)
    embed.add_field(name="📈 Progresso", value=f"`{barra}`", inline=False)
    embed.add_field(name="🎖 Badges", value=(" ".join(itens) if itens else "Nenhuma"), inline=False)
    embed.add_field(name="🖼 Moldura", value=frame, inline=True)
    embed.add_field(name="🎨 Cor do nome", value=color, inline=True)

    await interaction.response.send_message(embed=embed)

# /top
@bot.tree.command(name="top", description="Top 10 usuários por XP neste servidor")
async def top(interaction: discord.Interaction):
    # pega top por xp no DB (global) e filtra membros do servidor
    rows = []
    for uid_str, data in db.get("users", {}).items():
        rows.append((int(uid_str), data.get("xp", 0), data.get("level", 1)))
    rows.sort(key=lambda x: x[1], reverse=True)
    if not rows:
        await interaction.response.send_message("Nenhum registro encontrado.", ephemeral=True)
        return
    embed = Embed(title="🏆 TOP 10 — XP", color=0xFF8C00)
    text = ""
    medals = ["🥇","🥈","🥉"]
    c = 0
    for i, (uid, xp, lvl) in enumerate(rows):
        if c >= 10:
            break
        member = interaction.guild.get_member(uid)
        if member:
            tag = medals[c] if c < 3 else f"#{c+1}"
            text += f"{tag} **{member.display_name}** — XP `{xp}` | Nível `{lvl}`\n"
            c += 1
    if text == "":
        await interaction.response.send_message("Nenhum usuário ativo do servidor no ranking.", ephemeral=True)
        return
    embed.add_field(name="Ranking:", value=text, inline=False)
    await interaction.response.send_message(embed=embed)

# /loja
@bot.tree.command(name="loja", description="Abre a loja visual (badges, molduras, cores)")
async def loja(interaction: discord.Interaction):
    loja_db = db.get("loja", {})
    embed = Embed(title="🏪 Loja RV7 — Itens Visuais", description="Use /comprar <item_key>", color=0xFFD700)
    for key, info in loja_db.items():
        nome = info.get("nome", key)
        preco = info.get("preco", 0)
        embed.add_field(name=f"{nome}", value=f"Preço: **{preco} XP** — ID: `{key}`", inline=False)
    await interaction.response.send_message(embed=embed)

# /comprar
@bot.tree.command(name="comprar", description="Compre um item da loja usando XP")
@app_commands.describe(item_key="Chave do item (ex: badge_ouro, moldura_azul, cor_azul)")
async def comprar(interaction: discord.Interaction, item_key: str):
    item_key = item_key.strip().lower()
    loja_db = db.get("loja", {})
    if item_key not in loja_db:
        await interaction.response.send_message("❌ Item não encontrado. Use /loja para ver as chaves.", ephemeral=True)
        return
    info = loja_db[item_key]
    nome = info.get("nome")
    preco = info.get("preco", 0)
    ensure_user(interaction.guild.id, interaction.user.id)
    user = get_user(interaction.user.id)
    xp_atual = user.get("xp", 0)
    if xp_atual < preco:
        await interaction.response.send_message(f"❌ Você não tem XP suficiente. Precisa de {preco} XP.", ephemeral=True)
        return
    # deduz XP
    user["xp"] = xp_atual - preco
    # aplicar item conforme tipo pela heurística de nome
    if "Badge" in nome or "badge" in nome or "⭐" in nome or "💎" in nome or "🔥" in nome or "👑" in nome:
        itens = user.get("itens", [])
        if nome in itens:
            await interaction.response.send_message("❌ Você já possui essa badge.", ephemeral=True)
            return
        itens.append(nome)
        user["itens"] = itens
        save_db(db)
        await interaction.response.send_message(f"✅ Comprado: **{nome}** — Badge adicionada ao seu perfil.")
        return
    if "Moldura" in nome or "Moldura" in nome or "moldura" in nome or "🟦" in nome:
        user["frame"] = nome
        save_db(db)
        await interaction.response.send_message(f"✅ Comprado: **{nome}** — Moldura aplicada ao seu perfil.")
        return
    if "Nome" in nome or "Nome" in nome or "🔵" in nome:
        user["color"] = nome
        save_db(db)
        await interaction.response.send_message(f"✅ Comprado: **{nome}** — Cor aplicada ao seu perfil.")
        return
    # fallback
    user.setdefault("itens", []).append(nome)
    save_db(db)
    await interaction.response.send_message(f"✅ Comprado: **{nome}**!")

# /meus-itens
@bot.tree.command(name="meus-itens", description="Mostra seus itens (badges, moldura, cor)")
async def meus_itens(interaction: discord.Interaction):
    ensure_user(interaction.guild.id, interaction.user.id)
    user = get_user(interaction.user.id)
    itens = user.get("itens", [])
    frame = user.get("frame", "Nenhuma")
    color = user.get("color", "Padrão")
    text = f"🎖 Badges: {' '.join(itens) if itens else 'Nenhuma'}\n🖼 Moldura: {frame}\n🎨 Cor: {color}"
    await interaction.response.send_message(text)

# /uptime
@bot.tree.command(name="uptime", description="Mostra tempo online do bot")
async def uptime(interaction: discord.Interaction):
    delta = datetime.now(timezone.utc) - INICIO_BOT
    horas, resto = divmod(int(delta.total_seconds()), 3600)
    minutos, segundos = divmod(resto, 60)
    await interaction.response.send_message(f"⏱️ Online há {horas}h {minutos}m {segundos}s")

# /criado
@bot.tree.command(name="criado", description="Mostra quando o bot foi criado (conta do bot)")
async def criado(interaction: discord.Interaction):
    criado_at = bot.user.created_at if bot.user and bot.user.created_at else None
    if criado_at:
        await interaction.response.send_message(f"📅 Criado em {criado_at.strftime('%d/%m/%Y %H:%M:%S')} (UTC)")
    else:
        await interaction.response.send_message("Não consegui obter a data de criação do bot.")

# ---------------- RELATÓRIO AUTOMÁTICO (EMBED) ----------------
# Horários: list of (hour, minute) in server local time (use UTC if unsure)
REPORT_SCHEDULE = [(0,0),(4,50),(6,0),(15,0),(18,0)]

@tasks.loop(minutes=1)
async def periodic_relatorio():
    agora = datetime.now()
    for h, m in REPORT_SCHEDULE:
        if agora.hour == h and agora.minute == m:
            for guild in bot.guilds:
                try:
                    canal = discord.utils.get(guild.text_channels, name=CANAL_RELATORIOS_NAME)
                    if not canal or not canal.permissions_for(guild.me).send_messages:
                        continue

                    # monta embed do relatório
                    embed = Embed(title="📊 Relatório de Atividade — RV7", description="Resumo de mensagens e ranking (XP)", color=0x1E90FF)
                    # Mensagens no período (usa MESSAGES_COUNTER)
                    msgs = MESSAGES_COUNTER.get(guild.id, {})
                    if msgs:
                        texto_msgs = ""
                        # ordena por contagem
                        ranking_msgs = sorted(msgs.items(), key=lambda x: x[1], reverse=True)
                        for uid, cnt in ranking_msgs[:15]:
                            member = guild.get_member(uid)
                            nome = member.display_name if member else f"Usuário ({uid})"
                            texto_msgs += f"• **{nome}** — `{cnt}` mensagens\n"
                        embed.add_field(name="💬 Mensagens (período)", value=texto_msgs, inline=False)
                    else:
                        embed.add_field(name="💬 Mensagens (período)", value="Nenhuma mensagem registrada.", inline=False)

                    # Ranking por XP (top 10)
                    rows = []
                    for uid_str, data in db.get("users", {}).items():
                        try:
                            uid = int(uid_str)
                            rows.append((uid, data.get("xp", 0), data.get("level", 1)))
                        except Exception:
                            continue
                    rows.sort(key=lambda x: x[1], reverse=True)
                    if rows:
                        texto_xp = ""
                        medals = ["🥇","🥈","🥉"]
                        c = 0
                        for i, (uid, xp, lvl) in enumerate(rows[:10]):
                            member = guild.get_member(uid)
                            nome = member.display_name if member else f"Usuário ({uid})"
                            prefix = medals[i] if i < 3 else f"#{i+1}"
                            barra = barra_progress(xp, lvl, tamanho=10)
                            texto_xp += f"{prefix} **{nome}** — Nível {lvl}\nXP: `{xp}` `{barra}`\n\n"
                        embed.add_field(name="🏆 Ranking Geral (XP)", value=texto_xp, inline=False)
                    else:
                        embed.add_field(name="🏆 Ranking Geral (XP)", value="Nenhum usuário com XP registrado.", inline=False)

                    embed.set_footer(text="RV7 System • Relatório automático")
                    await canal.send(embed=embed)
                except Exception as e:
                    print("Erro enviando relatório:", e)
            # reset counters after sending (per guild)
            MESSAGES_COUNTER.clear()

# ---------------- UTILIDADES ADMIN (ex: reset DB) ----------------
@bot.tree.command(name="reset-db", description="(Dono) Reinicia o database JSON")
async def reset_db(interaction: discord.Interaction):
    # apenas owner do bot (aquele que tem token) pode rodar
    app_owner = await bot.application_info()
    if interaction.user.id != app_owner.owner.id:
        await interaction.response.send_message("Apenas o dono do bot pode usar este comando.", ephemeral=True)
        return
    try:
        os.remove(DB_PATH)
    except Exception:
        pass
    ensure_db()
    global db
    db = load_db()
    await interaction.response.send_message("✅ Database reinicializado.", ephemeral=True)

# ---------------- START ----------------
async def start_bot():
    if TOKEN == "" or TOKEN == "SEU_TOKEN_AQUI":
        print("ERRO: Coloque o token do bot em TOKEN na parte superior do arquivo.")
        return
    try:
        await bot.start(TOKEN)
    except Exception as e:
        print("Erro ao iniciar bot:", e)

if __name__ == "__main__":
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        print("Encerrando...")
