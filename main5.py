import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
from datetime import datetime, timedelta, timezone

# ================= CONFIG =================
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DONOS_IDS = [1236433975233351681]  # seu UID
CANAL_RELATORIOS_ID = 1437677612666454056
CANAL_BEMVINDO_ID = 1436927878066475150

USUARIOS_MENSAGENS = {}
USUARIOS_XP = {}
USUARIOS_COOLDOWN = {}
USUARIOS_NEON = {}  # {user_id: task}

# ================= LOJA =================
LOJA_ITENS = {
    "cor-neon": 150,
    "tag-vip": 300,
    "efeito-futurista": 500,
    "nick-neon": 1000,
    "entrada-neon": 1000,
    "ping-vip": 800,
    "figurinhas-vip": 400,
    "tag-colorida": 600,
    "glow-master": 700
}

INICIO_BOT = datetime.now(timezone.utc)
XP_POR_MENSAGEM = 5
XP_PARA_NIVEL = 100
ENVIADO_HOJE = set()

# ================= FUNÇÕES =================
def is_dono(interaction):
    return interaction.user.id in DONOS_IDS

def calcular_nivel(xp):
    return xp // XP_PARA_NIVEL

async def nick_neon(member, base_name=None):
    if not base_name:
        base_name = member.name
    cores = ["💠", "⚡", "✨", "🔥", "🌌"]
    while True:
        for cor in cores:
            try:
                await member.edit(nick=f"{cor} {base_name} {cor}")
            except Exception:
                return
            await asyncio.sleep(2)

async def glow_master(member, base_name=None):
    if not base_name:
        base_name = member.name
    cores = ["💫", "⚡", "🌟", "✨"]
    while True:
        for cor in cores:
            try:
                await member.edit(nick=f"{cor}{base_name}{cor}")
            except Exception:
                return
            await asyncio.sleep(2)

# ================= EVENTOS =================
@bot.event
async def on_ready():
    print(f"{bot.user} online!")
    periodic_relatorio.start()
    try:
        synced = await bot.tree.sync()
        print(f"✅ Comandos sincronizados ({len(synced)})")
    except Exception as e:
        print(f"Erro ao sincronizar comandos: {e}")

@bot.event
async def on_member_join(member):
    try:
        canal = member.guild.get_channel(CANAL_BEMVINDO_ID)
        cargo = discord.utils.get(member.guild.roles, name="🧩 Recruta RV7")

        if canal:
            await canal.send(f"✨ **Seja bem-vindo ao Clã RV7, {member.mention}!**")

        if cargo and member.guild.me.top_role > cargo:
            await member.add_roles(cargo)

    except Exception as e:
        print(f"Erro on_member_join: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    guild_id = message.guild.id
    user_id = message.author.id
    agora = datetime.now(timezone.utc)

    # CONTADOR DE MENSAGENS (RELATÓRIO)
    if guild_id not in USUARIOS_MENSAGENS:
        USUARIOS_MENSAGENS[guild_id] = {}
    USUARIOS_MENSAGENS[guild_id][user_id] = USUARIOS_MENSAGENS[guild_id].get(user_id, 0) + 1

    # SISTEMA DE XP COM COOLDOWN
    if user_id not in USUARIOS_COOLDOWN or (agora - USUARIOS_COOLDOWN[user_id]).seconds >= 60:
        USUARIOS_XP[user_id] = USUARIOS_XP.get(user_id, 0) + XP_POR_MENSAGEM
        USUARIOS_COOLDOWN[user_id] = agora

    await bot.process_commands(message)

# ================= COMANDOS DE MODERAÇÃO =================
@bot.tree.command(name="banir")
@app_commands.describe(membro="Membro", motivo="Motivo")
async def banir(interaction, membro: discord.Member, motivo: str = None):
    if not is_dono(interaction):
        return await interaction.response.send_message("❌ Apenas dono.", ephemeral=True)
    if membro.id in DONOS_IDS or membro.top_role >= interaction.guild.me.top_role:
        return await interaction.response.send_message("❌ Não posso banir este membro.", ephemeral=True)
    await membro.ban(reason=motivo)
    await interaction.response.send_message(f"🔥 **{membro} banido!**\nMotivo: {motivo or 'Nenhum'}")

@bot.tree.command(name="desbanir")
async def desbanir(interaction, usuario: discord.User):
    if not is_dono(interaction):
        return await interaction.response.send_message("❌ Apenas dono.", ephemeral=True)
    bans = await interaction.guild.bans()
    for b in bans:
        if b.user.id == usuario.id:
            await interaction.guild.unban(usuario)
            return await interaction.response.send_message(f"♻️ **{usuario} desbanido!**")
    await interaction.response.send_message("❌ Usuário não está banido.", ephemeral=True)

@bot.tree.command(name="expulsar")
async def expulsar(interaction, membro: discord.Member, motivo: str = None):
    if not is_dono(interaction):
        return await interaction.response.send_message("❌ Apenas dono.", ephemeral=True)
    if membro.top_role >= interaction.guild.me.top_role:
        return await interaction.response.send_message("❌ Não posso expulsar este membro.", ephemeral=True)
    await membro.kick(reason=motivo)
    await interaction.response.send_message(f"🚪 **{membro} expulso!**")

# ================= COMANDOS SISTEMA =================
@bot.tree.command(name="uptime")
async def uptime(interaction):
    delta = datetime.now(timezone.utc) - INICIO_BOT
    h, r = divmod(delta.total_seconds(), 3600)
    m, s = divmod(r, 60)
    await interaction.response.send_message(f"⏱️ Online há **{int(h)}h {int(m)}m {int(s)}s**")

@bot.tree.command(name="criacao")
async def criacao(interaction):
    await interaction.response.send_message(
        f"📅 Criado em **{bot.user.created_at.strftime('%d/%m/%Y %H:%M:%S')}** (UTC)"
    )

# ================= COMANDOS XP / LOJA =================
@bot.tree.command(name="xp")
async def xp(interaction):
    user = interaction.user.id
    xp_atual = USUARIOS_XP.get(user, 0)
    nivel = calcular_nivel(xp_atual)
    await interaction.response.send_message(f"💠 Você tem **{xp_atual} XP** — **Nível {nivel}**.")

@bot.tree.command(name="loja")
async def loja(interaction):
    msg = "🛒 **LOJA NEON RV7**\n\n"
    for item, preço in LOJA_ITENS.items():
        msg += f"⚡ `{item}` — **{preço} XP**\n"
    await interaction.response.send_message(msg)

@bot.tree.command(name="comprar")
async def comprar(interaction, item: str):
    user = interaction.user.id
    member = interaction.user

    if item not in LOJA_ITENS:
        return await interaction.response.send_message("❌ Item não existe.", ephemeral=True)

    preço = LOJA_ITENS[item]
    xp_user = USUARIOS_XP.get(user, 0)

    if xp_user < preço:
        return await interaction.response.send_message("❌ XP insuficiente.", ephemeral=True)

    USUARIOS_XP[user] -= preço
    await interaction.response.send_message(f"🟦 **Item comprado:** `{item}`\n💠 XP restante: {USUARIOS_XP[user]}")

    # Ações especiais dos itens
    if item == "nick-neon":
        if user in USUARIOS_NEON:
            USUARIOS_NEON[user].cancel()
        task = bot.loop.create_task(nick_neon(member))
        USUARIOS_NEON[user] = task
    elif item == "glow-master":
        if user in USUARIOS_NEON:
            USUARIOS_NEON[user].cancel()
        task = bot.loop.create_task(glow_master(member))
        USUARIOS_NEON[user] = task

@bot.tree.command(name="top")
async def top(interaction):
    ranking = sorted(USUARIOS_XP.items(), key=lambda x: x[1], reverse=True)
    msg = "🏆 **TOP XP RV7**\n\n"
    for i, (uid, xp) in enumerate(ranking[:10], start=1):
        member = interaction.guild.get_member(uid)
        if member:
            nivel = calcular_nivel(xp)
            msg += f"**{i}. {member.name}** — {xp} XP (Nível {nivel})\n"
    await interaction.response.send_message(msg)

@bot.tree.command(name="doar")
async def doar(interaction, membro: discord.Member, quantidade: int):
    doador = interaction.user.id
    if USUARIOS_XP.get(doador, 0) < quantidade:
        return await interaction.response.send_message("❌ XP insuficiente.", ephemeral=True)
    USUARIOS_XP[doador] -= quantidade
    USUARIOS_XP[membro.id] = USUARIOS_XP.get(membro.id, 0) + quantidade
    await interaction.response.send_message(
        f"🔁 **Transferência concluída!**\n{interaction.user.mention} → {membro.mention}\n💠 {quantidade} XP"
    )

@bot.tree.command(name="database-reset")
async def db_reset(interaction):
    if not is_dono(interaction):
        return await interaction.response.send_message("❌ Apenas dono.", ephemeral=True)
    USUARIOS_XP.clear()
    await interaction.response.send_message("💥 Banco de dados XP resetado!")

# ================= RELATÓRIO AUTOMÁTICO =================
@tasks.loop(minutes=1)
async def periodic_relatorio():
    agora = datetime.now(timezone.utc) - timedelta(hours=3)
    horarios = [(0,0),(4,50),(6,0),(15,0),(18,0)]
    for h, m in horarios:
        for guild in bot.guilds:
            key = (guild.id, h, m)
            if agora.hour == h and agora.minute == m and key not in ENVIADO_HOJE:
                canal = guild.get_channel(CANAL_RELATORIOS_ID)
                if not canal:
                    continue
                msgs = USUARIOS_MENSAGENS.get(guild.id, {})
                texto = (
                    "💠 **RELATÓRIO DE ATIVIDADE — RV7** 💠\n"
                    "```ansi\n"
                    "\u001b[38;5;39m═══════════════ NEON REPORT ═══════════════\u001b[0m\n"
                )
                if msgs:
                    for uid, count in msgs.items():
                        member = guild.get_member(uid)
                        if member:
                            texto += f"\u001b[38;5;51m{member.name:<15}\u001b[0m — \u001b[38;5;45m{count} msgs\u001b[0m\n"
                else:
                    texto += "Nenhuma mensagem registrada.\n"
                texto += "══════════════════════════════════════════\n```"
                await canal.send(texto)
                USUARIOS_MENSAGENS[guild.id] = {}
                ENVIADO_HOJE.add(key)
    if agora.hour == 0 and agora.minute == 0:
        ENVIADO_HOJE.clear()

# ================= START =================
async def iniciar_bot():
    token = "SEU_TOKEN_AQUI"  # coloque seu token direto aqui
    while True:
        try:
            await bot.start(token)
        except Exception as e:
            print(f"⚠️ Bot caiu: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(iniciar_bot())
