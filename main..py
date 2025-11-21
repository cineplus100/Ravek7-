# main.py -- RV7 Profissional
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
GUILD_IDS = None  # colocar [ID1, ID2] se quiser registrar só em guilds específicas
CANAL_RELATORIOS_NAME = "relatorios-rv7"
CANAL_BEM_VINDAS_NAME = "🏡│boas-vindas"
CANAL_PROMOCOES_NAME = "promocoes-rv7"
CARGO_BOAS_VINDAS = "🧩 Recruta RV7"

# ---------------- INTENTS ----------------
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

# ---------------- LOJA PADRÃO ----------------
if not db.get("loja"):
    db["loja"] = {
        "badge_ouro": {"nome": "🏆 Badge de Ouro", "preco": 300, "tipo":"badge"},
        "badge_diamante": {"nome": "💎 Badge de Diamante", "preco": 60000, "tipo":"badge"},
        "badge_fogo": {"nome": "🔥 Badge de Fogo", "preco": 900, "tipo":"badge"},
        "moldura_azul": {"nome": "🖼️ Moldura Azul Neon", "preco": 500, "tipo":"frame"},
        "moldura_vermelha": {"nome": "🖼️ Moldura Vermelha Inferno", "preco": 800, "tipo":"frame"},
        "cor_azul": {"nome": "🎨 Nome Azul", "preco": 400, "tipo":"color"},
        "cor_vermelha": {"nome": "🎨 Nome Vermelho", "preco": 400, "tipo":"color"}
    }
    save_db(db)

# ---------------- XP / LOJA CONFIG ----------------
XP_MIN = 2
XP_MAX = 7
BONUS_THRESHOLD = 20
BONUS_XP = 170
LEVEL_MULT = 120
COOLDOWN_SECONDS = 10

messages_window = defaultdict(lambda: defaultdict(lambda: deque()))
_last_xp_time = {}
MESSAGES_COUNTER = defaultdict(lambda: defaultdict(int))

# ---------------- HELPERS DB ----------------
def ensure_user(user_id: int):
    uid = str(user_id)
    if "users" not in db:
        db["users"] = {}
    if uid not in db["users"]:
        db["users"][uid] = {
            "xp": 0,
            "level": 1,
            "itens": [],
            "frame": "",
            "color": "",
            "last_bonus_ts": None
        }
        save_db(db)

def get_user(user_id: int):
    ensure_user(user_id)
    return db["users"][str(user_id)]

def add_xp_to_user(user_id: int, amount: int):
    user = get_user(user_id)
    user["xp"] += amount
    leveled = False
    while user["xp"] >= user["level"] * LEVEL_MULT:
        user["level"] += 1
        leveled = True
    save_db(db)
    return leveled, user["level"]

def barra_progress(xp: int, level: int, tamanho: int = 20) -> str:
    xp_max = max(1, level * LEVEL_MULT)
    p = int((xp / xp_max) * tamanho)
    p = max(0, min(tamanho, p))
    return "█" * p + "░" * (tamanho - p)

# ---------------- EVENTOS ----------------
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

# Boas-vindas
@bot.event
async def on_member_join(member: discord.Member):
    canal = discord.utils.get(member.guild.text_channels, name=CANAL_BEM_VINDAS_NAME)
    cargo = discord.utils.get(member.guild.roles, name=CARGO_BOAS_VINDAS)
    if canal and canal.permissions_for(member.guild.me).send_messages:
        await canal.send(f"👋 Bem-vindo ao clã RV7, Sua porrra {member.mention}! Leia as regras e se apresente 😎⚕️💜")
    if cargo and member.guild.me.top_role > cargo:
        try:
            await member.add_roles(cargo)
        except:
            pass

# Promoção de cargo
@bot.event
async def on_member_update(before, after):
    if before.roles == after.roles:
        return
    gained_roles = set(after.roles) - set(before.roles)
    if gained_roles:
        new_role = gained_roles.pop()
        canal = discord.utils.get(after.guild.text_channels, name=CANAL_PROMOCOES_NAME)
        if canal:
            embed = Embed(
                title="🎉 Parabéns!",
                description=f"{after.mention} você subiu de cargo!\nVocê merece! Continue assim 👏🏽💜⚕️",
                color=0x9B59B6,
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Cargo antigo", value=str(before.top_role), inline=True)
            embed.add_field(name="Cargo novo", value=str(new_role), inline=True)
            await canal.send(embed=embed)

# XP em mensagens
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return
    guild_id = message.guild.id
    user_id = message.author.id
    dq = messages_window[guild_id][user_id]
    dq.append(int(time.time()))
    cutoff = int(time.time()) - 3600
    while dq and dq[0] < cutoff:
        dq.popleft()
    key = (guild_id, user_id)
    last = _last_xp_time.get(key, 0)
    if time.time() - last >= COOLDOWN_SECONDS:
        ganho = random.randint(XP_MIN, XP_MAX)
        leveled, new_level = add_xp_to_user(user_id, ganho)
        _last_xp_time[key] = time.time()
        if leveled:
            await message.channel.send(f"🎉 {message.author.mention} subiu para o nível {new_level}!")
    await bot.process_commands(message)

# ---------------- SLASH COMMANDS ----------------
# /perfil profissional
@bot.tree.command(name="perfil", description="Mostra seu perfil completo")
@app_commands.describe(membro="Escolha um membro (opcional)")
async def perfil(interaction: discord.Interaction, membro: discord.Member = None):
    membro = membro or interaction.user
    ensure_user(membro.id)
    user = get_user(membro.id)
    barra = barra_progress(user["xp"], user["level"])

    # Rank global
    rows = [(int(uid), data.get("xp",0)) for uid,data in db.get("users",{}).items()]
    rows.sort(key=lambda x:x[1], reverse=True)
    rank = next((i+1 for i,(uid,xp) in enumerate(rows) if uid == membro.id), "N/A")

    embed = Embed(title=f"📋 Perfil — {membro.display_name}", color=0x1E90FF, timestamp=datetime.utcnow())
    if membro.avatar:
        embed.set_thumbnail(url=membro.avatar.url)

    embed.add_field(name="🏷️ UID", value=str(membro.id), inline=True)
    embed.add_field(name="🗓️ Conta criada", value=membro.created_at.strftime("%d/%m/%Y %H:%M:%S"), inline=True)
    embed.add_field(name="🥇 Rank global", value=str(rank), inline=True)

    embed.add_field(name="🏅 Nível", value=str(user["level"]), inline=True)
    embed.add_field(name="⚡ XP", value=f"{user['xp']}/{user['level']*LEVEL_MULT}", inline=True)
    embed.add_field(name="📈 Progresso", value=f"`{barra}`", inline=False)

    embed.add_field(name="🎖️ Badges", value=(" ".join(user["itens"]) if user["itens"] else "Nenhuma"), inline=False)
    embed.add_field(name="🖼️ Moldura", value=user.get("frame","Nenhuma"), inline=True)
    embed.add_field(name="🎨 Cor do nome", value=user.get("color","Padrão"), inline=True)

    embed.set_footer(text=f"Perfil de {membro.display_name}")
    await interaction.response.send_message(embed=embed)

# /doar XP
@bot.tree.command(name="doar", description="Doe XP para outro membro")
@app_commands.describe(membro="Membro que receberá XP", quantidade="Quantidade de XP")
async def doar(interaction: discord.Interaction, membro: discord.Member, quantidade:int):
    if membro.bot:
        await interaction.response.send_message("❌ Bots não podem receber XP.", ephemeral=True)
        return
    if quantidade <= 0:
        await interaction.response.send_message("❌ Quantidade inválida.", ephemeral=True)
        return
    ensure_user(interaction.user.id)
    ensure_user(membro.id)
    user_doador = get_user(interaction.user.id)
    if user_doador["xp"] < quantidade:
        await interaction.response.send_message(f"❌ Você não tem XP suficiente. Possui {user_doador['xp']} XP.", ephemeral=True)
        return
    user_doador["xp"] -= quantidade
    get_user(membro.id)["xp"] += quantidade
    save_db(db)
    await interaction.response.send_message(f"✅ {interaction.user.mention} doou {quantidade} XP para {membro.mention}!")

# /loja interativa
from discord.ui import View, Button

class LojaView(View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        for key, item in db["loja"].items():
            self.add_item(Button(label=f"{item['nome']} ({item['preco']} XP)", style=discord.ButtonStyle.primary, custom_id=f"loja_{key}"))

@bot.tree.command(name="loja", description="Abre a loja visual interativa")
async def loja(interaction: discord.Interaction):
    view = LojaView(interaction.user.id)
    await interaction.response.send_message("🛒 Escolha o item que deseja comprar:", view=view)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return
    custom_id = interaction.data["custom_id"]
    if custom_id.startswith("loja_"):
        item_key = custom_id.split("_",1)[1]
        item = db["loja"].get(item_key)
        if not item:
            await interaction.response.send_message("❌ Item não encontrado.", ephemeral=True)
            return
        user = get_user(interaction.user.id)
        if user["xp"] < item["preco"]:
            await interaction.response.send_message(f"❌ XP insuficiente. Precisa de {item['preco']} XP.", ephemeral=True)
            return
        user["xp"] -= item["preco"]
        if item["tipo"] == "badge":
            if item["nome"] not in user["itens"]:
                user["itens"].append(item["nome"])
        elif item["tipo"] == "frame":
            user["frame"] = item["nome"]
        elif item["tipo"] == "color":
            user["color"] = item["nome"]
        save_db(db)
        await interaction.response.send_message(f"✅ Você comprou {item['nome']}!", ephemeral=True)

# ---------------- RELATÓRIOS ----------------
RELATORIO_HORARIOS = [0, 3, 4, 12, 15, 17, 18, 22]

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
                for i,(uid,data) in enumerate(top_xp,1):
                    member = guild.get_member(int(uid))
                    if member:
                        text += f"{i}. {member.display_name} — XP {data.get('xp',0)} | Nível {data.get('level',1)}\n"
                embed.add_field(name=f"Top usuários ({len(top_xp)})", value=text if text else "Nenhum ativo", inline=False)
                embed.add_field(name="Total de usuários registrados", value=str(total_users), inline=False)
                await canal.send(embed=embed)

# ---------------- RUN BOT ----------------
ensure_db()
bot.run(TOKEN)
