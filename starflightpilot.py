import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from typing import Optional, Dict, List
import logging
import random
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')
BACKUP_FILE = 'ship_backup.json'
PLUSHIES_FILE = 'plushies.json'
MISSIONS_FILE = 'missions.json'
ENCOURAGEMENTS_FILE = 'encouragements.json'
STAFF_ROLE_ID = 1454538884682612940

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('StarflightBot')

# --- DATA STORAGE ---

class PlushieManager:
    """Manages plushie collection storage"""
    
    @staticmethod
    def load() -> Dict:
        """Load plushie data from file"""
        if not os.path.exists(PLUSHIES_FILE):
            return {}
        try:
            with open(PLUSHIES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load plushies: {e}")
            return {}
    
    @staticmethod
    def save(data: Dict) -> bool:
        """Save plushie data to file"""
        try:
            with open(PLUSHIES_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save plushies: {e}")
            return False
    
    @staticmethod
    def add_plushie(user_id: int, plushie_data: Dict) -> bool:
        """Add a plushie to a user's collection"""
        data = PlushieManager.load()
        user_key = str(user_id)
        
        if user_key not in data:
            data[user_key] = []
        
        # Check if plushie name already exists
        if any(p.get("name", "").lower() == plushie_data["name"].lower() for p in data[user_key]):
            return False  # Already exists
        
        data[user_key].append(plushie_data)
        return PlushieManager.save(data)
    
    @staticmethod
    def get_plushies(user_id: int) -> List[Dict]:
        """Get all plushies for a user"""
        data = PlushieManager.load()
        return data.get(str(user_id), [])
    
    @staticmethod
    def get_plushie(user_id: int, plushie_name: str) -> Optional[Dict]:
        """Get a specific plushie by name"""
        plushies = PlushieManager.get_plushies(user_id)
        for p in plushies:
            if p.get("name", "").lower() == plushie_name.lower():
                return p
        return None
    
    @staticmethod
    def remove_plushie(user_id: int, plushie_name: str) -> bool:
        """Remove a plushie from a user's collection"""
        data = PlushieManager.load()
        user_key = str(user_id)
        
        if user_key not in data:
            return False
        
        # Case-insensitive removal
        for i, p in enumerate(data[user_key]):
            if p.get("name", "").lower() == plushie_name.lower():
                data[user_key].pop(i)
                return PlushieManager.save(data)
        
        return False


class MissionGenerator:
    """Generates missions for Little Astronauts"""
    
    DEFAULT_MISSIONS = [
        "🎨 Color a picture of a planet and share it in chat!",
        "💧 Drink a glass of moon juice (water) to stay hydrated!",
        "🌟 Count 10 stars (or anything sparkly) around you!",
        "📚 Read a chapter of your favorite space book!",
        "🧸 Give your favorite plushie a big hug!",
        "🎵 Listen to a calming lullaby or space music!",
        "🌙 Take a 10-minute nap to recharge your energy!",
        "🍪 Have a healthy snack from the space galley!",
        "🚀 Do 5 jumping jacks like you're in zero gravity!",
        "✨ Tell someone something nice about them!",
        "🌌 Draw what you think a nebula looks like!",
        "🛌 Make your bed like you're preparing your space pod!",
        "🎮 Play with your favorite toy for 15 minutes!",
        "🌠 Look out the window and find 3 interesting things!",
        "💫 Practice writing your name in 'space letters'!",
        "🧃 Make yourself a special 'astronaut drink'!",
        "🎪 Do a silly dance to make your crewmates smile!",
        "🌍 Learn one new fact about space or planets!",
        "🛸 Build something with blocks or craft supplies!",
        "⭐ Tell someone about your day and how you're feeling!"
    ]
    
    @staticmethod
    def load_missions() -> List[str]:
        """Load missions from file, or return defaults if file doesn't exist"""
        if not os.path.exists(MISSIONS_FILE):
            # Create the file with default missions
            MissionGenerator.save_missions(MissionGenerator.DEFAULT_MISSIONS)
            return MissionGenerator.DEFAULT_MISSIONS
        
        try:
            with open(MISSIONS_FILE, 'r', encoding='utf-8') as f:
                missions = json.load(f)
                # Validate that it's a list
                if isinstance(missions, list) and missions:
                    return missions
                else:
                    logger.warning("Invalid missions.json format, using defaults")
                    return MissionGenerator.DEFAULT_MISSIONS
        except Exception as e:
            logger.error(f"Failed to load missions: {e}, using defaults")
            return MissionGenerator.DEFAULT_MISSIONS
    
    @staticmethod
    def save_missions(missions: List[str]) -> bool:
        """Save missions to file"""
        try:
            with open(MISSIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(missions, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save missions: {e}")
            return False
    
    @staticmethod
    def get_mission() -> str:
        """Get a random mission"""
        missions = MissionGenerator.load_missions()
        return random.choice(missions)


class EncouragementGenerator:
    """Generates encouraging messages for fuel refills"""
    
    DEFAULT_ENCOURAGEMENTS = [
        "is sending you rocket fuel! 🚀✨",
        "is refueling your tank with cosmic energy! ⭐💫",
        "thinks you're doing stellar! 🌟🌙",
        "is beaming positive vibes your way! 🛸💖",
        "says you're out of this world! 🌍🪐",
        "is sending you galaxy-sized hugs! 🌌🤗",
        "believes you can reach the stars! ✨🌠",
        "is your co-pilot cheering you on! 🛰️💪",
        "sent you a care package from Mission Control! 📦💝",
        "thinks you shine brighter than a supernova! 💫⭐"
    ]
    
    @staticmethod
    def load_encouragements() -> List[str]:
        """Load encouragements from file, or return defaults if file doesn't exist"""
        if not os.path.exists(ENCOURAGEMENTS_FILE):
            # Create the file with default encouragements
            EncouragementGenerator.save_encouragements(EncouragementGenerator.DEFAULT_ENCOURAGEMENTS)
            return EncouragementGenerator.DEFAULT_ENCOURAGEMENTS
        
        try:
            with open(ENCOURAGEMENTS_FILE, 'r', encoding='utf-8') as f:
                encouragements = json.load(f)
                # Validate that it's a list
                if isinstance(encouragements, list) and encouragements:
                    return encouragements
                else:
                    logger.warning("Invalid encouragements.json format, using defaults")
                    return EncouragementGenerator.DEFAULT_ENCOURAGEMENTS
        except Exception as e:
            logger.error(f"Failed to load encouragements: {e}, using defaults")
            return EncouragementGenerator.DEFAULT_ENCOURAGEMENTS
    
    @staticmethod
    def save_encouragements(encouragements: List[str]) -> bool:
        """Save encouragements to file"""
        try:
            with open(ENCOURAGEMENTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(encouragements, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save encouragements: {e}")
            return False
    
    @staticmethod
    def get_encouragement() -> str:
        """Get a random encouragement"""
        encouragements = EncouragementGenerator.load_encouragements()
        return random.choice(encouragements)


# --- UTILITIES ---

class BackupManager:
    """Handles all backup-related operations"""
    
    @staticmethod
    def load() -> Optional[Dict]:
        """Load backup data from file"""
        if not os.path.exists(BACKUP_FILE):
            return None
        try:
            with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load backup: {e}")
            return None
    
    @staticmethod
    def save(data: Dict) -> bool:
        """Save backup data to file"""
        try:
            with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save backup: {e}")
            return False
    
    @staticmethod
    async def create_backup(guild: discord.Guild) -> Dict:
        """Create a backup of the guild's roles and channels"""
        backup = {"roles": [], "categories": []}
        
        # Backup roles
        for role in reversed(guild.roles):
            if role.is_default():
                continue
            backup["roles"].append({
                "name": role.name,
                "color": role.color.value,
                "permissions": role.permissions.value,
                "hoist": role.hoist
            })
        
        # Backup categories and channels
        for cat in guild.categories:
            cat_info = {
                "name": cat.name,
                "overwrites": BackupManager._serialize_overwrites(cat.overwrites),
                "channels": []
            }
            
            for chan in cat.channels:
                cat_info["channels"].append({
                    "name": chan.name,
                    "type": str(chan.type),
                    "overwrites": BackupManager._serialize_overwrites(chan.overwrites)
                })
            
            backup["categories"].append(cat_info)
        
        return backup
    
    @staticmethod
    def _serialize_overwrites(overwrites: Dict) -> List[Dict]:
        """Convert channel overwrites to serializable format"""
        result = []
        for target, ovr in overwrites.items():
            allow, deny = ovr.pair()
            result.append({
                "name": target.name,
                "is_role": isinstance(target, discord.Role),
                "allow": allow.value,
                "deny": deny.value
            })
        return result
    
    @staticmethod
    async def apply_overwrites(guild: discord.Guild, item, ovr_data: List[Dict]):
        """Apply permission overwrites to a channel or category"""
        overwrites = {}
        
        for o in ovr_data:
            target_name = o.get("name")
            is_role = o.get("is_role", True)
            
            target = discord.utils.get(
                guild.roles if is_role else guild.members,
                name=target_name
            )
            
            if target:
                overwrites[target] = discord.PermissionOverwrite.from_pair(
                    discord.Permissions(o.get("allow", 0)),
                    discord.Permissions(o.get("deny", 0))
                )
        
        if overwrites:
            try:
                await item.edit(overwrites=overwrites)
            except discord.Forbidden:
                logger.warning(f"Permission denied when editing overwrites for {item.name}")
            except Exception as e:
                logger.error(f"Error editing overwrites for {item.name}: {e}")


class SyncManager:
    """Handles server syncing operations"""
    
    @staticmethod
    async def sync_roles(guild: discord.Guild, backup_roles: List[Dict]):
        """Sync roles with backup, removing extras"""
        backup_role_names = {r.get("name") for r in backup_roles}
        
        # Delete roles not in backup
        for role in guild.roles:
            if (role.is_default() or role.managed or 
                role >= guild.me.top_role or role.name in backup_role_names):
                continue
            
            try:
                await role.delete()
                logger.info(f"Deleted role: {role.name}")
            except Exception as e:
                logger.error(f"Failed to delete role {role.name}: {e}")
        
        # Create or update roles from backup
        for r in backup_roles:
            role = discord.utils.get(guild.roles, name=r.get("name"))
            
            if role and (role >= guild.me.top_role or role.managed):
                continue
            
            try:
                if not role:
                    await guild.create_role(
                        name=r["name"],
                        color=discord.Color(r["color"]),
                        permissions=discord.Permissions(r["permissions"]),
                        hoist=r["hoist"]
                    )
                    logger.info(f"Created role: {r['name']}")
                else:
                    await role.edit(
                        hoist=r["hoist"],
                        color=discord.Color(r["color"]),
                        permissions=discord.Permissions(r["permissions"])
                    )
                    logger.info(f"Updated role: {r['name']}")
            except Exception as e:
                logger.error(f"Failed to process role {r['name']}: {e}")
    
    @staticmethod
    async def sync_categories(guild: discord.Guild, backup_categories: List[Dict]):
        """Sync categories and channels with backup, removing extras"""
        backup_cat_names = {c.get("name") for c in backup_categories}
        
        # Delete categories not in backup
        for cat in guild.categories:
            if cat.name not in backup_cat_names:
                try:
                    for ch in cat.channels:
                        await ch.delete()
                    await cat.delete()
                    logger.info(f"Deleted category: {cat.name}")
                except Exception as e:
                    logger.error(f"Failed to delete category {cat.name}: {e}")
        
        # Process each category from backup
        for c in backup_categories:
            await SyncManager._sync_category(guild, c)
    
    @staticmethod
    async def _sync_category(guild: discord.Guild, cat_data: Dict):
        """Sync a single category and its channels"""
        cat_name = cat_data.get("name")
        cat = discord.utils.get(guild.categories, name=cat_name)
        
        try:
            if not cat:
                cat = await guild.create_category(cat_name)
                logger.info(f"Created category: {cat_name}")
            
            await BackupManager.apply_overwrites(guild, cat, cat_data.get("overwrites", []))
            
            # Sync channels in this category
            backup_channels = cat_data.get("channels", [])
            backup_chan_names = {ch.get("name") for ch in backup_channels}
            
            # Delete extra channels
            for actual_ch in cat.channels:
                if actual_ch.name not in backup_chan_names:
                    try:
                        await actual_ch.delete()
                        logger.info(f"Deleted channel: {actual_ch.name}")
                    except Exception as e:
                        logger.error(f"Failed to delete channel {actual_ch.name}: {e}")
            
            # Create/update channels
            for ch_data in backup_channels:
                await SyncManager._sync_channel(guild, cat, ch_data)
                
        except Exception as e:
            logger.error(f"Failed to sync category {cat_name}: {e}")
    
    @staticmethod
    async def _sync_channel(guild: discord.Guild, cat: discord.CategoryChannel, ch_data: Dict):
        """Sync a single channel"""
        ch_name = ch_data.get("name")
        ch = discord.utils.get(cat.channels, name=ch_name)
        
        try:
            if not ch:
                if ch_data.get("type") == "voice":
                    ch = await guild.create_voice_channel(ch_name, category=cat)
                else:
                    ch = await guild.create_text_channel(ch_name, category=cat)
                logger.info(f"Created channel: {ch_name}")
            
            await BackupManager.apply_overwrites(guild, ch, ch_data.get("overwrites", []))
        except Exception as e:
            logger.error(f"Failed to sync channel {ch_name}: {e}")


# --- BOT SETUP ---

class StarflightBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
    
    async def setup_hook(self):
        logger.info("🛰️ Preparing Starflight command tree...")


bot = StarflightBot()


@bot.event
async def on_ready():
    logger.info(f'🚀 Starflight Pilot online as {bot.user}')


# --- PERMISSION CHECK ---

def is_staff_or_admin():
    """Check if user has admin permissions or staff role"""
    async def predicate(interaction: discord.Interaction):
        is_admin = interaction.user.guild_permissions.administrator
        has_role = discord.utils.get(interaction.user.roles, id=STAFF_ROLE_ID) is not None
        
        if is_admin or has_role:
            return True
        
        await interaction.response.send_message(
            "❌ **Access Denied:** Authorized personnel only.",
            ephemeral=True
        )
        return False
    
    return app_commands.check(predicate)


# --- SLASH COMMANDS ---

@bot.command()
@commands.has_permissions(administrator=True)
async def sync_tree(ctx):
    """Sync slash commands to Discord"""
    await bot.tree.sync()
    await ctx.send("📡 Command tree synced to Discord.")


@bot.tree.command(name="list_roles", description="Get a list of role mention codes")
@is_staff_or_admin()
async def list_roles(interaction: discord.Interaction):
    """Lists roles with their mention codes, split into chunks"""
    await interaction.response.defer(ephemeral=True)
    
    roles = interaction.guild.roles
    full_role_list = [f"`{role.name}: <@&{role.id}>`" for role in reversed(roles)]
    
    # Send in chunks to avoid hitting message limits
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
    """Post embeds from a JSON template file"""
    if not filename.endswith('.json'):
        filename += '.json'
    
    if not os.path.exists(filename):
        return await interaction.response.send_message(
            f"❌ `{filename}` not found.",
            ephemeral=True
        )
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return await interaction.response.send_message(
            f"❌ Error reading file: {e}",
            ephemeral=True
        )
    
    # Build embeds
    embed_list = []
    for e_data in data.get("embeds", []):
        embed = discord.Embed(
            title=e_data.get("title"),
            description=e_data.get("description"),
            color=e_data.get("color", discord.Color.blue().value)
        )
        
        if "image" in e_data:
            embed.set_image(url=e_data["image"]["url"])
        
        if "footer" in e_data:
            footer_text = (e_data["footer"].get("text") 
                          if isinstance(e_data["footer"], dict) 
                          else e_data["footer"])
            embed.set_footer(text=footer_text)
        
        for field in e_data.get("fields", []):
            embed.add_field(
                name=field["name"],
                value=field["value"],
                inline=field.get("inline", False)
            )
        
        embed_list.append(embed)
    
    try:
        await channel.send(content=data.get("content", ""), embeds=embed_list)
        await interaction.response.send_message(
            f"✅ Sent to {channel.mention}",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Error sending message: {e}",
            ephemeral=True
        )


@bot.tree.command(name="backup_ship", description="Saves current server state")
@is_staff_or_admin()
async def backup_ship(interaction: discord.Interaction):
    """Create a backup of the server's current state"""
    await interaction.response.defer(ephemeral=True)
    
    backup = await BackupManager.create_backup(interaction.guild)
    
    if BackupManager.save(backup):
        await interaction.followup.send("💾 Backup Complete.")
    else:
        await interaction.followup.send("❌ Failed to save backup.")


@bot.tree.command(name="sync_ship", description="Restores from backup and REMOVES extras")
@is_staff_or_admin()
async def sync_ship(interaction: discord.Interaction):
    """Sync server with backup, removing anything not in backup"""
    await interaction.response.defer(ephemeral=True)
    
    data = BackupManager.load()
    if not data:
        return await interaction.followup.send("❌ No backup file found.")
    
    guild = interaction.guild
    
    # Sync roles
    await SyncManager.sync_roles(guild, data.get("roles", []))
    
    # Sync categories and channels
    await SyncManager.sync_categories(guild, data.get("categories", []))
    
    await interaction.followup.send("🚀 Sync Complete: Server matches backup exactly.")


# --- NEW FEATURE COMMANDS ---

class IntroModal(discord.ui.Modal, title="✨ Introduce Yourself to the Crew!"):
    """Modal for collecting introduction information"""
    
    age = discord.ui.TextInput(
        label="Age/Age Range",
        placeholder="Your age or age range",
        required=True,
        max_length=50
    )
    
    pronouns = discord.ui.TextInput(
        label="Pronouns",
        placeholder="Your pronouns",
        required=True,
        max_length=100
    )
    
    role = discord.ui.TextInput(
        label="Community Role",
        placeholder="Your role in the community (optional)",
        required=False,
        max_length=200
    )
    
    favorites = discord.ui.TextInput(
        label="Favorites",
        placeholder="Things you love and enjoy!",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )
    
    about = discord.ui.TextInput(
        label="More About You",
        placeholder="Share anything else you'd like the crew to know!",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )
    
    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel
    
    async def on_submit(self, interaction: discord.Interaction):
        # Create embed with user's intro
        embed = discord.Embed(
            title=f"🚀 Welcome Aboard, {interaction.user.display_name}!",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        # Format the introduction in the requested style
        intro_text = f"○ **Age:** {self.age.value}\n"
        intro_text += f"□ **Pronouns:** {self.pronouns.value}\n"
        
        if self.role.value:
            intro_text += f"☆ **Community role:** {self.role.value}\n"
        
        intro_text += f"♡ **Favorites:** {self.favorites.value}"
        
        embed.description = intro_text
        
        if self.about.value:
            embed.add_field(name="◇ More about me", value=self.about.value, inline=False)
        
        embed.set_footer(text=f"New crew member aboard! • {interaction.guild.name}")
        
        try:
            await self.channel.send(embed=embed)
            await interaction.response.send_message(
                "✅ Your introduction has been posted to the crew! Welcome aboard! 🚀",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to post introduction: {e}",
                ephemeral=True
            )


class PlushieScanModal(discord.ui.Modal, title="🧸 Register Your Plushie!"):
    """Modal for collecting plushie information"""
    
    name = discord.ui.TextInput(
        label="Plushie Name",
        placeholder="What's your plushie's name?",
        required=True,
        max_length=100
    )
    
    species = discord.ui.TextInput(
        label="Species/Type",
        placeholder="e.g., Bear, Bunny, Dragon, Alien...",
        required=True,
        max_length=100
    )
    
    color = discord.ui.TextInput(
        label="Color(s)",
        placeholder="e.g., Brown, Pink and Purple, Rainbow...",
        required=False,
        max_length=100
    )
    
    description = discord.ui.TextInput(
        label="Description/Backstory",
        placeholder="Tell us about your plushie! What makes them special?",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500
    )
    
    personality = discord.ui.TextInput(
        label="Personality Traits",
        placeholder="e.g., Loves hugs, shy, adventurous, sleepy...",
        required=False,
        max_length=200
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        plushie_data = {
            "name": self.name.value,
            "species": self.species.value,
            "color": self.color.value if self.color.value else "Unknown",
            "description": self.description.value,
            "personality": self.personality.value if self.personality.value else "Mysterious",
            "registered_date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
        }
        
        if PlushieManager.add_plushie(interaction.user.id, plushie_data):
            embed = discord.Embed(
                title="🧸 Plushie Registered!",
                description=f"**{self.name.value}** has been added to your zero-gravity collection!",
                color=discord.Color.green()
            )
            embed.add_field(name="Species", value=self.species.value, inline=True)
            embed.add_field(name="Color", value=plushie_data["color"], inline=True)
            embed.set_footer(text="Use /plushie_summon to see all your plushies!")
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                f"❌ You already have a plushie named **{self.name.value}** in your collection!",
                ephemeral=True
            )


@bot.tree.command(name="intro", description="Introduce yourself to the crew!")
@app_commands.describe(channel="Channel to post your introduction (optional)")
async def intro(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    """Open an introduction form for new crew members"""
    target_channel = channel or interaction.channel
    
    # Check if user has permission to send messages in the target channel
    if not target_channel.permissions_for(interaction.user).send_messages:
        return await interaction.response.send_message(
            "❌ You don't have permission to post in that channel.",
            ephemeral=True
        )
    
    modal = IntroModal(target_channel)
    await interaction.response.send_modal(modal)


@bot.tree.command(name="plushie_scan", description="Register a plushie to your collection!")
async def plushie_scan(interaction: discord.Interaction):
    """Open a form to scan and register a plushie with full details"""
    modal = PlushieScanModal()
    await interaction.response.send_modal(modal)


@bot.tree.command(name="plushie_summon", description="View your plushie collection!")
async def plushie_summon(interaction: discord.Interaction):
    """Display all registered plushies for the user"""
    plushies = PlushieManager.get_plushies(interaction.user.id)
    
    if not plushies:
        embed = discord.Embed(
            title="🧸 Zero-G Plushie Collection",
            description="Your collection is empty! Use `/plushie_scan` to register your first plushie!",
            color=discord.Color.blue()
        )
    else:
        # Create a summary list
        plushie_list = "\n".join([
            f"🧸 **{p['name']}** - {p['species']}" 
            for p in plushies
        ])
        
        embed = discord.Embed(
            title=f"🧸 {interaction.user.display_name}'s Plushie Collection",
            description=plushie_list,
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Total Plushies: {len(plushies)} • Use /plushie_info [name] for details!")
    
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="plushie_info", description="View detailed info about a specific plushie")
@app_commands.describe(name="Name of the plushie")
async def plushie_info(interaction: discord.Interaction, name: str):
    """Display detailed information about a specific plushie"""
    plushie = PlushieManager.get_plushie(interaction.user.id, name)
    
    if not plushie:
        return await interaction.response.send_message(
            f"❌ Couldn't find a plushie named **{name}** in your collection.\nUse `/plushie_summon` to see all your plushies!",
            ephemeral=True
        )
    
    embed = discord.Embed(
        title=f"🧸 {plushie['name']}'s Profile",
        description=plushie['description'],
        color=discord.Color.purple(),
        timestamp=datetime.now(timezone.utc)
    )
    
    embed.add_field(name="🐾 Species", value=plushie['species'], inline=True)
    embed.add_field(name="🎨 Color", value=plushie['color'], inline=True)
    embed.add_field(name="✨ Personality", value=plushie['personality'], inline=False)
    
    if plushie.get('registered_date'):
        embed.add_field(
            name="📅 Registered", 
            value=plushie['registered_date'], 
            inline=True
        )
    
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text=f"Owned by {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="plushie_release", description="Remove a plushie from your collection")
@app_commands.describe(name="Name of the plushie to remove")
async def plushie_release(interaction: discord.Interaction, name: str):
    """Release a plushie from your collection"""
    if PlushieManager.remove_plushie(interaction.user.id, name):
        embed = discord.Embed(
            title="🧸 Plushie Released",
            description=f"**{name}** has been sent on a solo space mission. Safe travels! 🚀",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(
            f"❌ Couldn't find a plushie named **{name}** in your collection.",
            ephemeral=True
        )


@bot.tree.command(name="mission_report", description="Get a mission assignment!")
async def mission_report(interaction: discord.Interaction):
    """Give Little Astronauts a fun mission to complete"""
    mission = MissionGenerator.get_mission()
    
    embed = discord.Embed(
        title="🚀 Mission Assignment",
        description=f"**Mission Briefing for {interaction.user.display_name}:**\n\n{mission}",
        color=discord.Color.gold(),
        timestamp=datetime.now(timezone.utc)
    )
    
    embed.set_thumbnail(url="https://em-content.zobj.net/source/twitter/348/rocket_1f680.png")
    embed.set_footer(text="Report back when your mission is complete! o7")
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="fuel_refill", description="Send encouraging fuel to a crew member!")
@app_commands.describe(member="The crew member who needs fuel", message="Optional personal message")
async def fuel_refill(interaction: discord.Interaction, member: discord.Member, message: Optional[str] = None):
    """Send encouraging messages to other members"""
    
    encouragement = EncouragementGenerator.get_encouragement()
    
    embed = discord.Embed(
        title="⛽ Fuel Refill Station",
        description=f"**{interaction.user.display_name}** {encouragement}",
        color=discord.Color.green(),
        timestamp=datetime.now(timezone.utc)
    )
    
    if message:
        embed.add_field(name="📝 Personal Message", value=message, inline=False)
    
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="Keep flying, space cadet! 🚀")
    
    try:
        await interaction.channel.send(content=member.mention, embed=embed)
        await interaction.response.send_message(
            f"✅ Fuel sent to {member.display_name}! 🚀",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Failed to send fuel: {e}",
            ephemeral=True
        )


if __name__ == "__main__":
    if not TOKEN:
        logger.error("❌ DISCORD_TOKEN not found in environment variables!")
        logger.error("Please create a .env file with: DISCORD_TOKEN=your_token_here")
        exit(1)
    
    bot.run(TOKEN)