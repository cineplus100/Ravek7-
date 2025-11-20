# main.py -- RV7 completo: XP híbrido + Loja Visual + Relatórios + Welcome + Slash commands + Admin + /amostrado
import os
import json
import random
import time
from collections import deque, defaultdict
from datetime import datetime, timezone

import discord
from discord import app_commands, Embed
from discord.ext import commands, tasks

# ---------------- CONFIG ----------------
TOKEN = "SEU_TOKEN_AQUI"
GUILD_IDS = None  # coloque [ID1, ID2] se quiser registrar apenas em guilds específicas
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

# ---------------- DATABASE ----------------
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
BONUS_THRESHOLD = 20
BONUS_XP = 300
LEVEL_MULT = 120
COOLDOWN_SECONDS = 10

messages_window = defaultdict(lambda: defaultdict(lambda: deque()))
_last_xp_time = {}
MESSAGES_COUNTER = defaultdict(lambda: defaultdict(int))

# ---------------- HELPERS DB ----------------
def ensure_user(guild_id: int, user_id: int):
    uid = str(user_id)
    if "users" not in db:
        db["users"] = {}
    if uid not in db["users"]:
        db["users"][uid] = {
            "xp": 0,
            "level": 1,
            "mensagens_hora": 0,
            "ultimo_reset": int(time.time()),
            "itens": [],
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
    print(f"{bot.user} online!")
    try:
        if GUILD_IDS:
            for gid in GUILD_IDS:
                await bot.tree.sync(guild=discord.Object(id=gid))
        else:
            await bot.tree.sync()
        print("Slash commands sincronizados.")
    except Exception as e:
        print("Erro ao sincronizar slash commands:", e)
    if not periodic_relatorio.is_running():
        periodic_relatorio.start()
    print("Tarefas iniciadas.")

@bot.event
async def on_member_join(member: discord.Member):
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

# ---------------- XP: on_message ----------------
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return
    guild_id = message.guild.id
    user_id = message.author.id
    MESSAGES_COUNTER[guild_id][user_id] += 1
    now_ts = int(time.time())
    dq = messages_window[guild_id][user_id]
    dq.append(now_ts)
    cutoff = now_ts - 3600
    while dq and dq[0] < cutoff:
        dq.popleft()
    key = (guild_id, user_id)
    last = _last_xp_time.get(key, 0)
    if time.time() - last >= COOLDOWN_SECONDS:
        ganho = random.randint(XP_MIN, XP_MAX)
        leveled, new_level = add_xp_to_user(user_id, ganho)
        _last_xp_time[key] = time.time()
        if leveled:
            try:
                await message.channel.send(f"⭐ **{message.author.mention} subiu para o nível {new_level}!**")
            except Exception:
                pass
    dq_len = len(messages_window[guild_id][user_id])
    if dq_len >= BONUS_THRESHOLD:
        user = get_user(user_id)
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
    rows = [(int(uid), data.get("xp", 0), data.get("level",1)) for uid, data in db.get("users", {}).items()]
    rows.sort(key=lambda x:x[1], reverse=True)
    if not rows:
        await interaction.response.send_message("Nenhum registro encontrado.", ephemeral=True)
        return
    embed = Embed(title="🏆 TOP 10 — XP", color=0xFF8C00)
    text = ""
    medals = ["🥇","🥈","🥉"]
    c = 0
    for i, (uid, xp, lvl) in enumerate(rows):
        if c>=10: break
        member = interaction.guild.get_member(uid)
        if member:
            tag = medals[c] if c<3 else f"#{c+1}"
            text += f"{tag} **{member.display_name}** — XP `{xp}` | Nível `{lvl}`\n"
            c+=1
    if text=="":
        await interaction.response.send_message("Nenhum usuário ativo do servidor no ranking.", ephemeral=True)
        return
    embed.add_field(name="Ranking:", value=text, inline=False)
    await interaction.response.send_message(embed=embed)

# /loja
@bot.tree.command(name="loja", description="Abre a loja visual (badges, molduras, cores)")
async def loja(interaction: discord.Interaction):
    loja_db = db.get("loja",{})
    embed = Embed(title="🏪 Loja RV7 — Itens Visuais", description="Use /comprar <item_key>", color=0xFFD700)
    for key, info in loja_db.items():
        embed.add_field(name=f"{info.get('nome',key)}", value=f"Preço: **{info.get('preco',0)} XP** — ID: `{key}`", inline=False)
    await interaction.response.send_message(embed=embed)

# /comprar
@bot.tree.command(name="comprar", description="Compre um item da loja usando XP")
@app_commands.describe(item_key="Chave do item (ex: badge_ouro, moldura_azul, cor_azul)")
async def comprar(interaction: discord.Interaction, item_key: str):
    item_key = item_key.strip().lower()
    loja_db = db.get("loja",{})
    if item_key not in loja_db:
        await interaction.response.send_message("❌ Item não encontrado. Use /loja para ver as chaves.", ephemeral=True)
        return
    info = loja_db[item_key]
    nome = info.get("nome")
    preco = info.get("preco",0)
    ensure_user(interaction.guild.id, interaction.user.id)
    user = get_user(interaction.user.id)
    xp_atual = user.get("xp",0)
    if xp_atual<preco:
        await interaction.response.send_message(f"❌ Você não tem XP suficiente. Precisa de {preco} XP.", ephemeral=True)
        return
    user["xp"] = xp_atual-preco
    if any(x in nome.lower() for x in ["badge","⭐","💎","🔥","👑"]):
        itens = user.get("itens",[])
        if nome in itens:
            await interaction.response.send_message("❌ Você já possui essa badge.", ephemeral=True)
            return
        itens.append(nome)
        user["itens"]=itens
        save_db(db)
        await interaction.response.send_message(f"✅ Comprado: **{nome}** — Badge adicionada ao seu perfil.")
        return
    if any(x in nome.lower() for x in ["moldura","🟦","🟥","🟩","🟪"]):
        user["frame"]=nome
        save_db(db)
        await interaction.response.send_message(f"✅ Comprado: **{nome}** — Moldura aplicada ao seu perfil.")
        return
    if any(x in nome.lower() for x in ["nome","🔵","🔴","🟣"]):
        user["color"]=nome
        save_db(db)
        await interaction.response.send_message(f"✅ Comprado: **{nome}** — Cor aplicada ao seu perfil.")
        return
    user.setdefault("itens",[]).append(nome)
    save_db(db)
    await interaction.response.send_message(f"✅ Comprado: **{nome}**!")

# /meus-itens
@bot.tree.command(name="meus-itens", description="Mostra seus itens (badges, moldura, cor)")
async def meus_itens(interaction: discord.Interaction):
    ensure_user(interaction.guild.id, interaction.user.id)
    user = get_user(interaction.user.id)
    itens = user.get("itens",[])
    frame = user.get("frame","Nenhuma")
    color = user.get("color","Padrão")
    await interaction.response.send_message(f"🎖 Badges: {' '.join(itens) if itens else 'Nenhuma'}\n🖼 Moldura: {frame}\n🎨 Cor: {color}")

# /uptime
@bot.tree.command(name="uptime", description="Mostra tempo online do bot")
async def uptime(interaction: discord.Interaction):
    delta = datetime.now(timezone.utc) - INICIO_BOT
    horas, resto = divmod(int(delta.total_seconds()),3600)
    minutos, segundos = divmod(resto,60)
    await interaction.response.send_message(f"⏱️ Online há {horas}h {minutos}m {segundos}s")

# /criado
@bot.tree.command(name="criado", description="Mostra quando o bot foi criado")
async def criado(interaction: discord.Interaction):
    criado_at = bot.user.created_at if bot.user and bot.user.created_at else None
    if criado_at:
        await interaction.response.send_message(f"📅 Criado em {criado_at.strftime('%d/%m/%Y %H:%M:%S')} (UTC)")
    else:
        await interaction.response.send_message("Não consegui obter a data de criação do bot.")

# /amostrado
@bot.tree.command(name="amostrado", description="Mostra uma mensagem personalizada que você escolher")
@app_commands.describe(mensagem="Digite a mensagem que deseja mostrar")
async def amostrado(interaction: discord.Interaction, mensagem:str):
    await interaction.response.send_message(f"📢 {mensagem}")

# ---------------- ADMIN ----------------
# /reset-db
@bot.tree.command(name="reset-db", description="(Dono) Reinicia o database JSON")
async def reset_db(interaction: discord.Interaction):
    app_owner = await bot.application_info()
    if interaction.user.id != app_owner.owner.id:
        await interaction.response.send_message("Apenas o dono do bot pode usar este comando.", ephemeral=True)
        return
    try: os.remove(DB_PATH)
    except Exception: pass
    ensure_db()
    global db
    db = load_db()
    await interaction.response.send_message("✅ Database reinicializado.", ephemeral=True)

# /banir
@bot.tree.command(name="banir", description="Bane um membro do servidor (admin)")
@app_commands.describe(membro="Membro a ser banido", motivo="Motivo do ban")
async def banir(interaction: discord.Interaction, membro:discord.Member, motivo:str="Sem motivo"):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ Você não tem permissão para banir.", ephemeral=True)
        return
    try:
        await membro.ban(reason=motivo)
        await interaction.response.send_message(f"✅ {membro.display_name} foi banido! Motivo: {motivo}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Não consegui banir: {e}", ephemeral=True)

# /desban
@bot.tree.command(name="desban", description="Desbane um usuário pelo ID (admin)")
@app_commands.describe(user_id="ID do usuário banido")
async def desban(interaction: discord.Interaction, user_id:int):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ Você não tem permissão para desbanir.", ephemeral=True)
        return
    try:
        bans = await interaction.guild.bans()
        user = discord.utils.get(bans, user__id=user_id)
        if user:
            await interaction.guild.unban(user.user)
            await interaction.response.send_message(f"✅ Usuário {user.user} desbanido com sucesso!")
        else:
            await interaction.response.send_message("❌ Usuário não está banido.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao desbanir: {e}", ephemeral=True)

# ---------------- RELATÓRIOS ----------------
RELATORIO_HORARIOS = [0, 3, 4, 12, 15, 18, 22]

@tasks.loop(minutes=1)
async def periodic_relatorio():
    agora = datetime.now(timezone.utc)
    if agora.hour in RELATORIO_HORARIOS and agora.minute == 0:
        for guild in bot.guilds:
            canal = discord.utils.get(guild.text_channels, name=CANAL_RELATORIOS_NAME)
            if canal:
                embed = Embed(title="📊 Relatório RV7", color=0x00FF00)
                total_users = len(db.get("users",{}))
                top_xp = sorted(db.get("users",{}).items(), key=lambda x:x[1].get("xp",0), reverse=True)[:5]
                text = ""
                for i, (uid,data) in enumerate(top_xp,1):
                    member = guild.get_member(int(uid))
                    if member:
                        text += f"{i}. {member.display_name} — XP {data.get('xp',0)} | Nível {data.get('level',1)}\n"
                embed.add_field(name=f"Top usuários ({len(top_xp)})", value=text if text else "Nenhum ativo", inline=False)
                embed.add_field(name="Total de usuários registrados", value=str(total_users), inline=False)
                await canal.send(embed=embed)

# ---------------- RUN BOT ----------------
ensure_db()
bot.run(TOKEN) 
