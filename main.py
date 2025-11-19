import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
from datetime import datetime, timezone

# ================= CONFIGURAÇÃO =================
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DONOS_IDS = [1437609941107081379] # seu ID
CANAL_RELATORIOS = "relatorios-rv7"
USUARIOS_MENSAGENS = {}  # {guild_id: {user_id: count}}
INICIO_BOT = datetime.now(timezone.utc)

# ================= EVENTOS =================
@bot.event
async def on_ready():
    print(f"{bot.user} online!")
    periodic_relatorio.start()

@bot.event
async def on_member_join(member):
    try:
        canal = discord.utils.get(member.guild.text_channels, name="🏡│boas-vindas")
        cargo = discord.utils.get(member.guild.roles, name="🧩 Recruta RV7")
        if canal and canal.permissions_for(member.guild.me).send_messages:
            await canal.send(f"👋 Bem-vindo ao clã RV7, {member.mention}!")
        if cargo and member.guild.me.top_role > cargo:
            await member.add_roles(cargo)
    except Exception as e:
        print(f"Erro on_member_join: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    guild_id = message.guild.id
    if guild_id not in USUARIOS_MENSAGENS:
        USUARIOS_MENSAGENS[guild_id] = {}
    USUARIOS_MENSAGENS[guild_id][message.author.id] = USUARIOS_MENSAGENS[guild_id].get(message.author.id, 0) + 1
    await bot.process_commands(message)

# ================= FUNÇÃO DONO =================
def is_dono(interaction):
    return interaction.user.id in DONOS_IDS

# ================= COMANDOS ADMIN =================
@bot.tree.command(name="banir", description="Bane um membro (dono)")
@app_commands.describe(membro="Membro", motivo="Motivo")
async def banir(interaction: discord.Interaction, membro: discord.Member, motivo: str = None):
    if not is_dono(interaction):
        await interaction.response.send_message("❌ Apenas dono", ephemeral=True)
        return
    if membro.id in DONOS_IDS:
        await interaction.response.send_message("❌ Não pode mexer no dono!", ephemeral=True)
        return
    if interaction.guild.me.top_role <= membro.top_role:
        await interaction.response.send_message("❌ Não posso banir esse usuário, cargo alto.", ephemeral=True)
        return
    try:
        await membro.ban(reason=motivo)
        await interaction.response.send_message(f"✅ {membro} banido!\nMotivo: {motivo or 'Nenhum'}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

@bot.tree.command(name="desbanir", description="Desbane um usuário (dono)")
@app_commands.describe(usuario="Usuário")
async def desbanir(interaction: discord.Interaction, usuario: discord.User):
    if not is_dono(interaction):
        await interaction.response.send_message("❌ Apenas dono", ephemeral=True)
        return
    bans = await interaction.guild.bans()
    for ban_entry in bans:
        if ban_entry.user.id == usuario.id:
            try:
                await interaction.guild.unban(usuario)
                await interaction.response.send_message(f"✅ {usuario} desbanido!")
            except Exception as e:
                await interaction.response.send_message(f"❌ Erro ao desbanir: {e}", ephemeral=True)
            return
    await interaction.response.send_message("❌ Usuário não está banido", ephemeral=True)

@bot.tree.command(name="expulsar", description="Expulsa um membro (dono)")
@app_commands.describe(membro="Membro", motivo="Motivo")
async def expulsar(interaction: discord.Interaction, membro: discord.Member, motivo: str = None):
    if not is_dono(interaction):
        await interaction.response.send_message("❌ Apenas dono", ephemeral=True)
        return
    if membro.id in DONOS_IDS:
        await interaction.response.send_message("❌ Não pode mexer no dono!", ephemeral=True)
        return
    if interaction.guild.me.top_role <= membro.top_role:
        await interaction.response.send_message("❌ Não posso expulsar esse usuário, cargo alto.", ephemeral=True)
        return
    try:
        await membro.kick(reason=motivo)
        await interaction.response.send_message(f"✅ {membro} expulso!\nMotivo: {motivo or 'Nenhum'}")
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

# ================= TIMER (mute temporário) =================
@bot.tree.command(name="timer", description="Aplica mute temporário (dono)")
@app_commands.describe(membro="Membro", minutos="Duração em minutos")
async def timer(interaction: discord.Interaction, membro: discord.Member, minutos: int):
    if not is_dono(interaction):
        await interaction.response.send_message("❌ Apenas dono", ephemeral=True)
        return
    role = discord.utils.get(interaction.guild.roles, name="⛔ Mutado")
    if not role:
        role = await interaction.guild.create_role(name="⛔ Mutado")
    if interaction.guild.me.top_role <= role:
        await interaction.response.send_message("❌ Não consigo aplicar mute", ephemeral=True)
        return
    await membro.add_roles(role)
    await interaction.response.send_message(f"✅ {membro} mutado por {minutos} min")
    async def remover():
        await asyncio.sleep(minutos * 60)
        await membro.remove_roles(role)
    asyncio.create_task(remover())

# ================= OUTROS COMANDOS =================
@bot.tree.command(name="uptime", description="Mostra tempo online")
async def uptime(interaction: discord.Interaction):
    delta = datetime.now(timezone.utc) - INICIO_BOT
    horas, resto = divmod(int(delta.total_seconds()), 3600)
    minutos, segundos = divmod(resto, 60)
    await interaction.response.send_message(f"⏱️ Online há {horas}h {minutos}m {segundos}s")

@bot.tree.command(name="criado", description="Quando o bot foi criado")
async def criado(interaction: discord.Interaction):
    await interaction.response.send_message(f"📅 Criado em {bot.user.created_at.strftime('%d/%m/%Y %H:%M:%S')} (UTC)")

# ================= RELATÓRIOS AUTOMÁTICOS =================
@tasks.loop(minutes=1)
async def periodic_relatorio():
    agora = datetime.now()
    horarios = [(0,0),(4,50),(6,0),(15,0),(18,0)]  # horários
    for h,m in horarios:
        if agora.hour == h and agora.minute == m:
            for guild in bot.guilds:
                canal = discord.utils.get(guild.text_channels, name=CANAL_RELATORIOS)
                if canal and canal.permissions_for(guild.me).send_messages:
                    mensagens = USUARIOS_MENSAGENS.get(guild.id, {})
                    report = "🤖 **Relatório do RV7** 🤖\n\n"
                    if mensagens:
                        for uid, count in mensagens.items():
                            user = guild.get_member(uid)
                            if user:
                                report += f"• **{user.name}**: {count} mensagens\n"
                    else:
                        report += "Nenhuma mensagem registrada."
                    await canal.send(report)
                    USUARIOS_MENSAGENS[guild.id] = {}
                    print(f"✅ Relatório enviado para {guild.name}")

# ================= START =================
async def iniciar_bot():
    token = "MTQzNjkzMjU2NzQ4Mjg5MjQxMQ.GhRbbT.gbvL5VKn_FHHPd0Y5JTlcSxIwBDJrc0j2WtY0E"  # coloque seu token aqui
    while True:
        try:
            await bot.start(token)
        except Exception as e:
            print(f"⚠️ Bot caiu: {e}")
            await asyncio.sleep(60)

if __name__=="__main__":
    asyncio.run(iniciar_bot())
