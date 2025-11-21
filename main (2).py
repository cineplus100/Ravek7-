# main.py -- RV7 completo: XP híbrido + Loja Visual + Relatórios + Welcome + Slash commands + Admin + /doar + Loja interativa
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
TOKEN = "MTQzNjkzMjU2NzQ4Mjg5MjQxMQ.GUjf84.T2SEDDlF9lV3jf4AA6XYruK6RIriCfv_AfXIV0"  # <--- coloque seu token aqui
GUILD_IDS = None  # se quiser registrar os comandos somente em guilds específicas, coloque [ID1, ID2]
CANAL_RELATORIOS_NAME = "relatorios-rv7"
CANAL_BEM_VINDAS_NAME = "🏡│boas-vindas"
CARGO_BOAS_VINDAS = "🧩 Recruta RV7"
CANAL_PROMOCOES_NAME = "promocoes-rv7"

# Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
INICIO_BOT = datetime.now(timezone.utc)

# ---------------- DATABASE (JSON) ----------------
DB_PATH = "database.json"

def ensure_db_file():
    if not os.path.exists(DB_PATH):
        initial = {"users": {}, "loja": {}, "meta": {}}
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(initial, f, indent=4, ensure_ascii=False)

def load_db():
    ensure_db_file()
    with open(DB_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {"users": {}, "loja": {}, "meta": {}}

def save_db(db_obj):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db_obj, f, indent=4, ensure_ascii=False)

db = load_db()

# ---------------- LOJA: itens padrão ----------------
# chave: {nome, preco, tipo}
# tipo: badge, frame, color, effect, special
DEFAULT_LOJA = {
    "brilho_estelar": {"nome": "✨ Brilho Estelar", "preco": 300, "tipo": "effect"},
    "emoji_exclusivo": {"nome": "💬 Emoji Exclusivo", "preco": 30, "tipo": "special"},
    "nick_neon": {"nome": "🌈 Nick Neon Pulsante", "preco": 250, "tipo": "effect"},
    "escudo_guardiao": {"nome": "🛡️ Escudo do Guardião", "preco": 800, "tipo": "badge"},
    "moldura_diamante": {"nome": "🔷 Moldura Diamante Suprema", "preco": 2000, "tipo": "frame"},
    "moldura_fogo": {"nome": "🔶 Moldura Fogo Solar", "preco": 5000, "tipo": "frame"},
    "moldura_sombra": {"nome": "⚫ Moldura Sombra Negra", "preco": 4500, "tipo": "frame"},
    "cor_neon_aqua": {"nome": "💠 Cor Neon Aqua", "preco": 120, "tipo": "color"},
    "cor_neon_roxa": {"nome": "💜 Cor Neon Roxa", "preco": 200, "tipo": "color"},
    "cor_neon_vermelha": {"nome": "❤️ Cor Neon Vermelha", "preco": 300, "tipo": "color"},
    "aura_cosmica": {"nome": "🌌 Aura Cósmica", "preco": 15000, "tipo": "effect"},
    "coroa_dourada": {"nome": "👑 Coroa Dourada Real", "preco": 25000, "tipo": "badge"},
    "diamante_eterno": {"nome": "💎 Diamante Eterno", "preco": 50000, "tipo": "badge"},
    "efeito_entrada_supremo": {"nome": "⚡ Efeito de Entrada Supremo", "preco": 75000, "tipo": "effect"},
    # item que permite o usuário ser mencionado por bot em qualquer canal (uso via comando /mostrar-nome)
    "nome_broadcast": {"nome": "📣 Nome em Qualquer Canal", "preco": 1200, "tipo": "special"},
    "badge_ultra": {"nome": "👑 Badge Ultra Rara", "preco": 3500, "tipo": "badge"},
    "aura_lendaria": {"nome": "🔥 Aura Lendária", "preco": 1200, "tipo": "effect"},
}

if not db.get("loja"):
    db["loja"] = DEFAULT_LOJA.copy()
    save_db(db)

# ---------------- XP / LOJA CONFIG ----------------
XP_MIN = 5
XP_MAX = 15
BONUS_THRESHOLD = 20     # mensagens na última hora para bônus
BONUS_XP = 300
LEVEL_MULT = 120
COOLDOWN_SECONDS = 10

messages_window = defaultdict(lambda: defaultdict(lambda: deque()))  # messages_window[guild_id][user_id] -> deque timestamps
_last_xp_time = {}  # (guild_id, user_id) -> last_timestamp_float
MESSAGES_COUNTER = defaultdict(lambda: defaultdict(int))  # runtime message counters for reports (per-guild)

# ---------------- HELPERS DB / USUÁRIOS ----------------
def ensure_user_in_db(guild_id: int, user_id: int):
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
            "itens": [],   # badges and special items
            "frame": "",
            "color": "",
            "effects": [],  # visual effects
            "last_bonus_ts": None,
            "created_profile": int(time.time())
        }
        save_db(db)

def get_user(uid_int: int):
    uid = str(uid_int)
    ensure_user_in_db(0, uid_int)
    return db["users"][uid]

def update_user_field(uid_int: int, field: str, value):
    uid = str(uid_int)
    ensure_user_in_db(0, uid_int)
    db["users"][uid][field] = value
    save_db(db)

def add_xp_to_user(uid_int: int, amount: int):
    user = get_user(uid_int)
    user["xp"] = user.get("xp", 0) + int(amount)
    leveled = False
    lvl = user.get("level", 1)
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
    p = int((xp / xp_max) * tamanho) if xp_max else 0
    p = max(0, min(tamanho, p))
    return "█" * p + "░" * (tamanho - p)

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    print(f"{bot.user} online! (RV7)")
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
            await canal.send(f"👋 Bem-vindo ao clã RV7,Sua Porra {member.mention}! Leia as regras e se apresente 😊⚕️💜")
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
    if message.author.bot or not message.guild:
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
        if leveled:
            try:
                # anúncio de level up no canal de promoções, se existir
                for g in bot.guilds:
                    if g.id == guild_id:
                        canal = discord.utils.get(g.text_channels, name=CANAL_PROMOCOES_NAME)
                        if canal and canal.permissions_for(g.me).send_messages:
                            await canal.send(f"⭐ **{message.author.mention} subiu para o nível {new_level}!**")
                        break
            except Exception:
                pass

    # checa bônus de atividade (20 msgs na última hora) - uma vez por hora
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
            # limpa deque pra evitar retrigger
            messages_window[guild_id][user_id].clear()
            try:
                await message.channel.send(f"💥 **BÔNUS:** {message.author.mention} recebeu +{BONUS_XP} XP por atividade intensa!")
            except Exception:
                pass

    await bot.process_commands(message)

# ---------------- SLASH COMMANDS ----------------
# /perfil (simples)
@bot.tree.command(name="perfil", description="Mostra seu perfil (XP, nível, id, data de criação)")
@app_commands.describe(membro="Escolha um membro (opcional)")
async def perfil(interaction: discord.Interaction, membro: discord.Member = None):
    membro = membro or interaction.user
    ensure_user_in_db(interaction.guild.id, membro.id)
    user = get_user(membro.id)
    xp = user.get("xp", 0)
    level = user.get("level", 1)
    created = membro.created_at.strftime("%d/%m/%Y")
    barra = barra_progress(xp, level, tamanho=20)

    embed = Embed(title=f"🌐 Perfil — {membro.display_name}", color=0x1E90FF)
    try:
        if membro.avatar:
            embed.set_thumbnail(url=membro.avatar.url)
    except Exception:
        pass
    embed.add_field(name="ID", value=str(membro.id), inline=True)
    embed.add_field(name="⭐ Nível", value=str(level), inline=True)
    embed.add_field(name="⚡ XP", value=f"{xp}/{xp_needed_for_level(level)}", inline=True)
    embed.add_field(name="📅 Conta criada em", value=created, inline=False)
    embed.add_field(name="📈 Progresso", value=f"`{barra}`", inline=False)

    await interaction.response.send_message(embed=embed)

# /top
@bot.tree.command(name="top", description="Top 10 usuários por XP neste servidor")
async def top(interaction: discord.Interaction):
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

# ---------------- LOJA INTERATIVA ----------------
@bot.tree.command(name="loja", description="Loja interativa RV7")
async def loja(interaction: discord.Interaction):
    # construir opções a partir do DB da loja
    loja_db = db.get("loja", {})
    options = []
    for key, info in loja_db.items():
        label = info.get("nome", key)
        preco = info.get("preco", 0)
        options.append(discord.SelectOption(label=f"{label} — {preco} XP", value=key, description=str(preco)))

    class LojaSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="Escolha um item...", min_values=1, max_values=1, options=options)

        async def callback(self, interaction_select: discord.Interaction):
            # armazena seleção no view
            self.view.selected = self.values[0]
            await interaction_select.response.defer()  # apenas reconhece a interação

    class LojaView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=120)
            self.selected = None
            self.add_item(LojaSelect())

        @discord.ui.button(label="Comprar", style=discord.ButtonStyle.green)
        async def buy(self, button: discord.ui.Button, interaction_button: discord.Interaction):
            if not self.selected:
                await interaction_button.response.send_message("Escolha um item antes de comprar.", ephemeral=True)
                return
            key = self.selected
            item = db["loja"].get(key)
            if not item:
                await interaction_button.response.send_message("Item não encontrado.", ephemeral=True)
                return
            uid = str(interaction_button.user.id)
            ensure_user_in_db(interaction_button.guild.id, interaction_button.user.id)
            user = get_user(interaction_button.user.id)
            preco = int(item.get("preco", 0))
            if user.get("xp", 0) < preco:
                await interaction_button.response.send_message(f"❌ Você precisa de {preco} XP para comprar **{item['nome']}**.", ephemeral=True)
                return
            # deduz XP
            user["xp"] = user.get("xp", 0) - preco
            # aplicar item conforme tipo
            tipo = item.get("tipo", "")
            if tipo == "badge":
                itens = user.get("itens", [])
                if item["nome"] in itens:
                    await interaction_button.response.send_message("❌ Você já possui essa badge.", ephemeral=True)
                    save_db(db)
                    return
                itens.append(item["nome"])
                user["itens"] = itens
            elif tipo == "frame":
                user["frame"] = item["nome"]
            elif tipo == "color":
                user["color"] = item["nome"]
            elif tipo == "effect":
                effects = user.get("effects", [])
                if item["nome"] not in effects:
                    effects.append(item["nome"])
                user["effects"] = effects
            elif tipo == "special":
                # marca item especial nos itens para uso posterior
                itens = user.get("itens", [])
                if item["nome"] not in itens:
                    itens.append(item["nome"])
                user["itens"] = itens
            # salva
            save_db(db)
            await interaction_button.response.send_message(f"✅ Comprado: **{item['nome']}** por **{preco} XP**!", ephemeral=True)

    embed = Embed(title="🛒 Loja RV7 — Itens Visuais", description="Selecione um item e clique em **Comprar**", color=0x7B61FF)
    # mostra alguns destaques
    destaque_text = ""
    for k in ["efeito_entrada_supremo", "diamante_eterno", "coroa_dourada", "aura_cosmica", "moldura_diamante"]:
        if k in db["loja"]:
            info = db["loja"][k]
            destaque_text += f"• **{info['nome']}** — {info['preco']} XP\n"
    if destaque_text:
        embed.add_field(name="⛳ Destaques", value=destaque_text, inline=False)
    await interaction.response.send_message(embed=embed, view=LojaView(), ephemeral=False)

# /comprar (fallback - compra direta via comando)
@bot.tree.command(name="comprar", description="Compre um item pelo ID da loja (ex: comprar nome_key)")
@app_commands.describe(item_key="Chave do item da loja")
async def comprar(interaction: discord.Interaction, item_key: str):
    item_key = item_key.strip()
    loja_db = db.get("loja", {})
    if item_key not in loja_db:
        await interaction.response.send_message("❌ Item não encontrado. Use /loja para ver as chaves.", ephemeral=True)
        return
    item = loja_db[item_key]
    uid = str(interaction.user.id)
    ensure_user_in_db(interaction.guild.id, interaction.user.id)
    user = get_user(interaction.user.id)
    preco = int(item.get("preco", 0))
    if user.get("xp", 0) < preco:
        await interaction.response.send_message(f"❌ Você não tem XP suficiente. Precisa de {preco} XP.", ephemeral=True)
        return
    user["xp"] = user.get("xp", 0) - preco
    tipo = item.get("tipo", "")
    if tipo == "badge":
        itens = user.get("itens", [])
        if item["nome"] in itens:
            await interaction.response.send_message("❌ Você já possui essa badge.", ephemeral=True)
            return
        itens.append(item["nome"])
        user["itens"] = itens
    elif tipo == "frame":
        user["frame"] = item["nome"]
    elif tipo == "color":
        user["color"] = item["nome"]
    elif tipo == "effect":
        effects = user.get("effects", [])
        if item["nome"] not in effects:
            effects.append(item["nome"])
        user["effects"] = effects
    elif tipo == "special":
        itens = user.get("itens", [])
        if item["nome"] not in itens:
            itens.append(item["nome"])
        user["itens"] = itens
    save_db(db)
    await interaction.response.send_message(f"✅ Comprado: **{item['nome']}** — gasto {preco} XP.", ephemeral=True)

# /mostrar-nome (usa item especial "Nome em Qualquer Canal")
@bot.tree.command(name="mostrar-nome", description="Mostra seu nome em um canal (requer ter comprado o item correspondente)")
@app_commands.describe(canal="Escolha o canal onde o bot deverá mencionar você")
async def mostrar_nome(interaction: discord.Interaction, canal: discord.TextChannel):
    uid = str(interaction.user.id)
    ensure_user_in_db(interaction.guild.id, interaction.user.id)
    user = get_user(interaction.user.id)
    itens = user.get("itens", [])
    if not any("Nome em Qualquer Canal" in it or "Nome em Qualquer Canal" == it for it in itens):
        await interaction.response.send_message("❌ Você não possui o item necessário. Compre `Nome em Qualquer Canal` na loja.", ephemeral=True)
        return
    # envia mensagem no canal solicitado mencionando o usuário
    try:
        await canal.send(f"📣 {interaction.user.mention} pediu para aparecer aqui! ✨")
        await interaction.response.send_message(f"✅ Nome enviado em {canal.mention}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Não consegui enviar no canal: {e}", ephemeral=True)

# /doar (doa XP)
@bot.tree.command(name="doar", description="Doe XP para outro usuário")
@app_commands.describe(membro="Membro para quem você quer doar", quantidade="Quantidade de XP")
async def doar(interaction: discord.Interaction, membro: discord.Member, quantidade: int):
    if quantidade <= 0:
        await interaction.response.send_message("Quantidade inválida.", ephemeral=True)
        return
    ensure_user_in_db(interaction.guild.id, interaction.user.id)
    ensure_user_in_db(interaction.guild.id, membro.id)
    sender = get_user(interaction.user.id)
    receiver = get_user(membro.id)
    if sender.get("xp", 0) < quantidade:
        await interaction.response.send_message("❌ Você não tem XP suficiente para doar.", ephemeral=True)
        return
    sender["xp"] = sender.get("xp", 0) - quantidade
    receiver["xp"] = receiver.get("xp", 0) + quantidade
    save_db(db)
    await interaction.response.send_message(f"🎁 {interaction.user.mention} doou **{quantidade} XP** para {membro.mention}!")

# ---------------- ADMIN ----------------
# /reset-db
@bot.tree.command(name="reset-db", description="(Dono) Reinicia o database JSON")
async def reset_db(interaction: discord.Interaction):
    app_owner = await bot.application_info()
    #Apenas o dono do bot pode usar
    if interaction.user.id != app_owner.owner.id:
        await interaction.response.send_message(
            "❌ Apenas o dono do bot pode usar este comando.", 
            ephemeral=True
        )
        return
    
    # Tenta excluir database.json
    try:
        os.remove(DB_PATH)
    except Exception:
        pass

    # Recria database vazio
    ensure_db()
    global db
    db = load_db()
    
    await interaction.response.send_message("✅ Database reiniciado com sucesso!", ephemeral=True)
