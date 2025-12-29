import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import json
import os

# --- CONFIGURATION ---
# IMPORTANT: Reset your token in the Dev Portal and paste the NEW one here.
TOKEN = 'MTQ1MzI5MjMzOTkzNzQxNTE5MQ.GOXADw._mW4PzIW5FbWEBW8pBoAdPZiyZax9viHHDEgF4'
BACKUP_FILE = 'ship_backup.json'

class StarflightBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.message_content = True
        intents.members = True 
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("🛰️ Preparing Starflight command tree...")

bot = StarflightBot()

@bot.event
async def on_ready():
    print(f'🚀 Starflight Pilot online as {bot.user}')

# --- PERMISSION CHECK ---

def is_staff_or_admin():
    """Allows Administrators or users with the specific Staff Role ID to use commands."""
    async def predicate(interaction: discord.Interaction):
        STAFF_ROLE_ID = 1454538884682612940
        is_admin = interaction.user.guild_permissions.administrator
        has_role = discord.utils.get(interaction.user.roles, id=STAFF_ROLE_ID) is not None
        
        if is_admin or has_role:
            return True
        
        await interaction.response.send_message("❌ **Access Denied:** Authorized personnel only.", ephemeral=True)
        return False
    return app_commands.check(predicate)

# --- UTILITIES ---

def load_backup_data():
    if os.path.exists(BACKUP_FILE):
        with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

async def apply_overwrites(guild, item, ovr_data):
    """Applies permissions to a channel or category."""
    overwrites = {}
    for o in ovr_data:
        target_name = o.get("name")
        is_role = o.get("is_role", True)
        target = discord.utils.get(guild.roles if is_role else guild.members, name=target_name)
        
        if target:
            overwrites[target] = discord.PermissionOverwrite.from_pair(
                discord.Permissions(o.get("allow", 0)), 
                discord.Permissions(o.get("deny", 0))
            )
            
    if overwrites:
        try:
            await item.edit(overwrites=overwrites)
        except discord.Forbidden:
            print(f"⚠️ Permission denied for {item.name}")

# --- SLASH COMMANDS ---

@bot.command()
@commands.has_permissions(administrator=True)
async def sync_tree(ctx):
    """Run !sync_tree once to make slash commands appear in Discord."""
    await bot.tree.sync()
    await ctx.send("📡 Command tree synced to Discord.")

@bot.tree.command(name="list_roles", description="Get a list of role mention codes")
@is_staff_or_admin()
async def list_roles(interaction: discord.Interaction):
    """Lists roles as <@&ID> and splits into multiple messages to prevent formatting errors."""
    await interaction.response.defer(ephemeral=True)
    roles = interaction.guild.roles
    full_role_list = [f"`{role.name}: <@&{role.id}>`" for role in reversed(roles)]
    
    current_chunk = "📜 **Role ID Manifest:**\n"
    for role_entry in full_role_list:
        if len(current_chunk) + len(role_entry) > 1800:
            await interaction.followup.send(current_chunk, ephemeral=True)
            current_chunk = "" 
        current_chunk += role_entry + "\n"

    if current_chunk:
        await interaction.followup.send(current_chunk, ephemeral=True)

@bot.tree.command(name="post_embed", description="Post a JSON template with mentions and images")
@app_commands.describe(filename="JSON filename", channel="Target channel")
@is_staff_or_admin()
async def post_embed(interaction: discord.Interaction, filename: str, channel: discord.TextChannel):
    """Processes multi-embed JSON files like announcement templates."""
    if not filename.endswith('.json'): filename += '.json'
    if not os.path.exists(filename):
        return await interaction.response.send_message(f"❌ `{filename}` not found.", ephemeral=True)

    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)

    embed_list = []
    if "embeds" in data:
        for e_data in data["embeds"]:
            embed = discord.Embed(
                title=e_data.get("title"),
                description=e_data.get("description"),
                color=e_data.get("color", discord.Color.blue().value)
            )
            if "image" in e_data:
                embed.set_image(url=e_data["image"]["url"])
            if "footer" in e_data:
                footer_text = e_data["footer"].get("text") if isinstance(e_data["footer"], dict) else e_data["footer"]
                embed.set_footer(text=footer_text)
            for field in e_data.get("fields", []):
                embed.add_field(name=field["name"], value=field["value"], inline=field.get("inline", False))
            embed_list.append(embed)

    try:
        await channel.send(content=data.get("content", ""), embeds=embed_list)
        await interaction.response.send_message(f"✅ Sent to {channel.mention}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="backup_ship", description="Saves current server state")
@is_staff_or_admin()
async def backup_ship(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    backup = {"roles": [], "categories": []}

    for role in reversed(guild.roles):
        if role.is_default(): continue
        backup["roles"].append({
            "name": role.name, "color": role.color.value,
            "permissions": role.permissions.value, "hoist": role.hoist
        })

    for cat in guild.categories:
        cat_info = {"name": cat.name, "overwrites": [], "channels": []}
        for target, ovr in cat.overwrites.items():
            cat_info["overwrites"].append({
                "name": target.name, "is_role": isinstance(target, discord.Role),
                "allow": ovr.pair()[0].value, "deny": ovr.pair()[1].value
            })
        for chan in cat.channels:
            ovrs = []
            for target, ovr in chan.overwrites.items():
                ovrs.append({
                    "name": target.name, "is_role": isinstance(target, discord.Role),
                    "allow": ovr.pair()[0].value, "deny": ovr.pair()[1].value
                })
            cat_info["channels"].append({
                "name": chan.name, "type": str(chan.type), "overwrites": ovrs
            })
        backup["categories"].append(cat_info)

    with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
        json.dump(backup, f, indent=4)
    await interaction.followup.send("💾 Backup Complete.")

@bot.tree.command(name="sync_ship", description="Restores from backup and REMOVES extras")
@is_staff_or_admin()
async def sync_ship(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    data = load_backup_data()
    if not data:
        return await interaction.followup.send("❌ No backup file found.")
        
    guild = interaction.guild

    # --- 1. SYNC ROLES & DELETE EXTRAS ---
    backup_roles = data.get("roles", [])
    backup_role_names = [r.get("name") for r in backup_roles]
    
    for role in guild.roles:
        if role.is_default() or role.managed or role >= guild.me.top_role:
            continue
        if role.name not in backup_role_names:
            try: await role.delete()
            except: pass

    for r in backup_roles:
        role = discord.utils.get(guild.roles, name=r.get("name"))
        if role and (role >= guild.me.top_role or role.managed): continue
        if not role:
            await guild.create_role(name=r["name"], color=discord.Color(r["color"]), permissions=discord.Permissions(r["permissions"]), hoist=r["hoist"])
        else:
            await role.edit(hoist=r["hoist"], color=discord.Color(r["color"]), permissions=discord.Permissions(r["permissions"]))

    # --- 2. SYNC CATEGORIES/CHANNELS & DELETE EXTRAS ---
    backup_categories = data.get("categories", [])
    backup_cat_names = [c.get("name") for c in backup_categories]
    
    # Delete categories not in backup
    for cat in guild.categories:
        if cat.name not in backup_cat_names:
            for ch in cat.channels:
                await ch.delete()
            await cat.delete()

    # Process Categories and Channels
    for c in backup_categories:
        cat_name = c.get("name")
        cat = discord.utils.get(guild.categories, name=cat_name)
        if not cat: 
            cat = await guild.create_category(cat_name)
        
        await apply_overwrites(guild, cat, c.get("overwrites", []))
        
        backup_channels = c.get("channels", [])
        backup_chan_names = [ch.get("name") for ch in backup_channels]
        
        # Delete extra channels inside this category
        for actual_ch in cat.channels:
            if actual_ch.name not in backup_chan_names:
                await actual_ch.delete()

        # Create/Update channels
        for ch_data in backup_channels:
            ch_name = ch_data.get("name")
            ch = discord.utils.get(cat.channels, name=ch_name)
            if not ch:
                if ch_data.get("type") == "voice": 
                    ch = await guild.create_voice_channel(ch_name, category=cat)
                else: 
                    ch = await guild.create_text_channel(ch_name, category=cat)
            
            await apply_overwrites(guild, ch, ch_data.get("overwrites", []))

    await interaction.followup.send("🚀 Sync Complete: Server matches backup exactly.")

bot.run(TOKEN)