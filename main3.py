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
TOKEN = ""

# IDs PEDIDOS POR VOCÊ
CANAL_RELATORIOS_ID = 1437677612666454056
CANAL_BEM_VINDAS_ID = 1436927878066475150
OWNER_UID = 1236433975233351681

# Timezone Bahia (UTC-3)
BAHIA_TZ = timezone(timedelta(hours=-3))

GUILD_IDS = None  
CANAL_RELATORIOS_NAME = "relatorios-rv7"
CANAL_BEM_VINDAS_NAME = "🏡│boas-vindas"
CARGO_BOAS_VINDAS = "🧩 Recruta RV7"

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
INICIO_BOT = datetime.now(BAHIA_TZ)

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

# ---------------- HELPERS ----------------
def ensure_user(guild_id: int, user_id: int):
    uid = str(user_id)
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
    ensure_user(0, uid_int)
    return db["users"][str(uid_int)]

def add_xp_to_user(uid_int: int, amount: int):
    user = get_user(uid_int)
    user["xp"] += amount
    lvl = user["level"]
    leveled = False
    while user["xp"] >= lvl * LEVEL_MULT:
        lvl += 1
        user["level"] = lvl
        leveled = True
    save_db(db)
    return leveled, lvl

def xp_needed_for_level(level: int):
    return level * LEVEL_MULT

def barra_progress(xp, level, size=20):
    need = xp_needed_for_level(level)
    fill = int((xp / need) * size)
    return "█" * fill + "░" * (size - fill)

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    print(f"{bot.user} online!")
    try:
        await bot.tree.sync()
    except:
        pass

    if not periodic_relatorio.is_running():
        periodic_relatorio.start()

@bot.event
async def on_member_join(member: discord.Member):
    canal = member.guild.get_channel(CANAL_BEM_VINDAS_ID)
    if canal:
        await canal.send(f"👋 Bem-vindo ao clã RV7, {member.mention}!")

# ---------------- XP SYSTEM ----------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return await bot.process_commands(message)

    MESSAGES_COUNTER[message.guild.id][message.author.id] += 1

    now = time.time()
    key = (message.guild.id, message.author.id)
    last = _last_xp_time.get(key, 0)

    if now - last >= COOLDOWN_SECONDS:
        ganho = random.randint(XP_MIN, XP_MAX)
        leveled, lvl = add_xp_to_user(message.author.id, ganho)
        _last_xp_time[key] = now
        if leveled:
            await message.channel.send(f"⭐ {message.author.mention} subiu para o nível {lvl}!")

    await bot.process_commands(message)

# ---------------- SLASH COMMANDS ----------------
@bot.tree.command(name="doar", description="Doe XP para outro usuário.")
@app_commands.describe(usuario="Quem vai receber", quantidade="Quanto XP doar")
async def doar(interaction, usuario: discord.Member, quantidade: int):
    if quantidade <= 0:
        return await interaction.response.send_message("Quantidade inválida.", ephemeral=True)

    user = get_user(interaction.user.id)
    if user["xp"] < quantidade:
        return await interaction.response.send_message("Você não tem XP suficiente.", ephemeral=True)

    # remove do doador
    user["xp"] -= quantidade
    save_db(db)

    # adiciona ao alvo
    add_xp_to_user(usuario.id, quantidade)

    await interaction.response.send_message(
        f"🤝 {interaction.user.mention} doou **{quantidade} XP** para {usuario.mention}!"
    )

# ---------------- RELATÓRIO AUTOMÁTICO ----------------
REPORT_SCHEDULE = [(1,25),(2,16),(4,50),(6,0),(15,0),(18,0)]

@tasks.loop(minutes=1)
async def periodic_relatorio():
    agora = datetime.now(BAHIA_TZ)
    if (agora.hour, agora.minute) in REPORT_SCHEDULE:
        for guild in bot.guilds:
            canal = guild.get_channel(CANAL_RELATORIOS_ID)
            if not canal:
                continue

            embed = Embed(
                title="📊 Relatório de Atividade — RV7",
                color=0x1E90FF,
                timestamp=datetime.now(BAHIA_TZ)
            )

            msgs = MESSAGES_COUNTER[guild.id]
            texto = ""
            for uid, count in sorted(msgs.items(), key=lambda x: x[1], reverse=True):
                member = guild.get_member(uid)
                if member:
                    texto += f"• **{member.display_name}** — `{count}` mensagens\n"

            embed.add_field(name="Atividade recente", value=texto or "Nenhuma mensagem.")

            await canal.send(embed=embed)

        MESSAGES_COUNTER.clear()

# ---------------- START ----------------
async def start_bot():
    await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(start_bot())
    except:
        pass
