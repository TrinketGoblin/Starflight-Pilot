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
import io
import psycopg2
from PIL import Image

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')
BACKUP_FILE = 'ship_backup.json'
PLUSHIES_FILE = 'plushies.json'
MISSIONS_FILE = 'missions.json'
ENCOURAGEMENTS_FILE = 'encouragements.json'
EMBEDS_FOLDER = 'saved_embeds'
STAFF_ROLE_ID = 1454538884682612940

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('StarflightBot')

# Ensure folders exist
os.makedirs(EMBEDS_FOLDER, exist_ok=True)

# Global session storage for embed builder
user_embed_sessions = {}

# --- DATA STORAGE ---

DATABASE_URL = os.getenv('DATABASE_URL')

class PlushieManager:
    """Manages plushie collection storage using Railway SQL (PostgreSQL)"""
    
    @staticmethod
    def get_db_connection():
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL environment variable is not set.")
        return psycopg2.connect(DATABASE_URL)

    @staticmethod
    def init_db():
        """Creates the necessary table if it doesn't exist"""
        if not DATABASE_URL:
            logger.error("Cannot initialize DB: DATABASE_URL is not set.")
            return

        try:
            conn = PlushieManager.get_db_connection()
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS plushies (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    name TEXT NOT NULL,
                    species TEXT,
                    color TEXT,
                    description TEXT,
                    personality TEXT,
                    registered_date TEXT,
                    image_blob BYTEA
                )
            ''')
            conn.commit()
        except Exception as e:
            logger.error(f"SQL Database initialization failed: {e}")
        finally:
            if 'conn' in locals() and conn:
                cur.close()
                conn.close()

    @staticmethod
    def add_plushie(user_id: int, p_data: Dict, image_bytes: Optional[bytes] = None) -> bool:
        """Saves a plushie and its compressed image to the SQL database"""
        if not DATABASE_URL:
            logger.error("Cannot add plushie: DATABASE_URL is not set.")
            return False

        try:
            conn = PlushieManager.get_db_connection()
            cur = conn.cursor()
            
            # Check for duplicates
            cur.execute("SELECT id FROM plushies WHERE user_id = %s AND LOWER(name) = LOWER(%s)", (user_id, p_data['name'].lower()))
            if cur.fetchone():
                return False

            cur.execute('''
                INSERT INTO plushies (user_id, name, species, color, description, personality, registered_date, image_blob)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                user_id, p_data['name'], p_data['species'], p_data['color'], 
                p_data['description'], p_data['personality'], p_data['registered_date'],
                psycopg2.Binary(image_bytes) if image_bytes else None
            ))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"SQL Error saving plushie: {e}")
            return False
        finally:
            if 'conn' in locals() and conn:
                cur.close()
                conn.close()

    @staticmethod
    def get_plushies(user_id: int) -> List[Dict]:
        """Retrieves summary for a user"""
        if not DATABASE_URL: return []

        try:
            conn = PlushieManager.get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT name, species FROM plushies WHERE user_id = %s", (user_id,))
            rows = cur.fetchall()
            return [{"name": r[0], "species": r[1]} for r in rows]
        except Exception as e:
            logger.error(f"SQL Error retrieving plushies: {e}")
            return []
        finally:
            if 'conn' in locals() and conn:
                cur.close()
                conn.close()

    @staticmethod
    def get_plushie_full(user_id: int, name: str):
        """Retrieves full details including image blob"""
        if not DATABASE_URL: return None

        try:
            conn = PlushieManager.get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT name, species, color, description, personality, registered_date, image_blob FROM plushies WHERE user_id = %s AND LOWER(name) = LOWER(%s)", (user_id, name.lower()))
            row = cur.fetchone()
            return row
        except Exception as e:
            logger.error(f"SQL Error retrieving full plushie: {e}")
            return None
        finally:
            if 'conn' in locals() and conn:
                cur.close()
                conn.close()
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

class ImageProcessor:
    @staticmethod
    def compress_image(image_bytes: bytes) -> bytes:
        """Resizes image to 800x800 and compresses it to JPEG"""
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.thumbnail((800, 800))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85, optimize=True)
        return buffer.getvalue()

bot = StarflightBot()


@bot.event
async def on_ready():
    # Attempt to initialize DB when the bot is ready
    PlushieManager.init_db() 
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


class PlushieScanModal(discord.ui.Modal, title='Register a New Plushie'):
    """Modal for collecting plushie registration data."""
    
    def __init__(self, image_bytes: Optional[bytes] = None):
        super().__init__()
        self.image_bytes = image_bytes # Store compressed image bytes

    p_name = discord.ui.TextInput(
# ... (rest of the text inputs are unchanged) ...
        label='Plushie Name',
        placeholder='e.g., Captain Fluffybutt',
        max_length=50
    )

    p_species = discord.ui.TextInput(
        label='Species/Type',
        placeholder='e.g., Space Bear, Cuddly Octopus',
        max_length=50
    )

    p_color = discord.ui.TextInput(
        label='Primary Color',
        placeholder='e.g., Nebula Blue, Crimson',
        max_length=30,
        required=False
    )
    
    p_personality = discord.ui.TextInput(
        label='Personality',
        style=discord.TextStyle.paragraph,
        placeholder='e.g., Brave, slightly clumsy, loves long naps.',
        max_length=500
    )
    
    p_description = discord.ui.TextInput(
        label='Description/Origin Story',
        style=discord.TextStyle.paragraph,
        placeholder='e.g., Found floating near a dwarf planet.',
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):
        p_data = {
            "name": str(self.p_name),
            "species": str(self.p_species),
            "color": str(self.p_color) or "N/A",
            "personality": str(self.p_personality),
            "description": str(self.p_description),
            "registered_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        }
        
        # Pass stored image bytes to the database manager
        success = PlushieManager.add_plushie(interaction.user.id, p_data, self.image_bytes)
        
        if success:
            await interaction.response.send_message(
                f"✅ **{p_data['name']}** registered to the Starflight Crew Roster! Image compressed and stored. 🚀",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Failed to register **{p_data['name']}**. A plushie with that name might already exist in your collection.",
                ephemeral=True
            )

class EmbedBuilderModal(discord.ui.Modal, title="📝 Embed Builder"):
    """Modal for creating/editing embeds"""
    
    title_text = discord.ui.TextInput(
        label="Embed Title",
        placeholder="Title of your embed",
        required=False,
        max_length=256
    )
    
    description = discord.ui.TextInput(
        label="Description",
        placeholder="Main content of your embed",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=4000
    )
    
    color = discord.ui.TextInput(
        label="Color (hex code)",
        placeholder="e.g., #FF5733 or blue, red, green",
        required=False,
        max_length=20
    )
    
    footer = discord.ui.TextInput(
        label="Footer Text",
        placeholder="Small text at the bottom",
        required=False,
        max_length=2048
    )
    
    image_url = discord.ui.TextInput(
        label="Image URL",
        placeholder="https://... (optional)",
        required=False,
        max_length=500
    )
    
    def __init__(self, embed_name: str, existing_data: Optional[Dict] = None):
        super().__init__()
        self.embed_name = embed_name
        
        # Pre-fill if editing
        if existing_data:
            self.title_text.default = existing_data.get("title", "")
            self.description.default = existing_data.get("description", "")
            self.color.default = existing_data.get("color", "")
            self.footer.default = existing_data.get("footer", "")
            self.image_url.default = existing_data.get("image", "")
    
    async def on_submit(self, interaction: discord.Interaction):
        # Parse color
        color_value = discord.Color.blue()
        if self.color.value:
            color_str = self.color.value.strip().lower()
            try:
                if color_str.startswith('#'):
                    color_value = discord.Color(int(color_str[1:], 16))
                elif color_str == 'red':
                    color_value = discord.Color.red()
                elif color_str == 'green':
                    color_value = discord.Color.green()
                elif color_str == 'blue':
                    color_value = discord.Color.blue()
                elif color_str == 'purple':
                    color_value = discord.Color.purple()
                elif color_str == 'gold':
                    color_value = discord.Color.gold()
                elif color_str == 'orange':
                    color_value = discord.Color.orange()
            except:
                pass
        
        # Build embed data
        embed_data = {
            "title": self.title_text.value,
            "description": self.description.value,
            "color": self.color.value,
            "footer": self.footer.value,
            "image": self.image_url.value,
            "fields": []
        }
        
        # Save to file
        filepath = os.path.join(EMBEDS_FOLDER, f"{self.embed_name}.json")
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(embed_data, f, indent=4)
        except Exception as e:
            return await interaction.response.send_message(
                f"❌ Failed to save embed: {e}",
                ephemeral=True
            )
        
        # Create preview embed
        preview = discord.Embed(
            title=self.title_text.value or None,
            description=self.description.value or None,
            color=color_value
        )
        
        if self.footer.value:
            preview.set_footer(text=self.footer.value)
        
        if self.image_url.value:
            preview.set_image(url=self.image_url.value)
        
        await interaction.response.send_message(
            f"✅ Embed **{self.embed_name}** saved!\nUse `/embed_post {self.embed_name}` to post it.",
            embed=preview,
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


@bot.tree.command(name="plushie_scan", description="Register a plushie with a photo!")
@app_commands.describe(photo="Upload a photo of your plushie (will be resized to 800x800)")
async def plushie_scan(interaction: discord.Interaction, photo: Optional[discord.Attachment] = None):
    await interaction.response.defer(ephemeral=True, thinking=True) # Defer response for file reading/compression

    image_bytes = None
    if photo:
        if not photo.content_type or not photo.content_type.startswith("image/"):
            return await interaction.followup.send("❌ Please upload a valid image file.", ephemeral=True)
        
        try:
            # 1. Read raw bytes from Discord
            raw_data = await photo.read()
            # 2. Process and compress the image
            image_bytes = ImageProcessor.compress_image(raw_data)
        except Exception as e:
            logger.error(f"Error during file read/compression: {e}")
            return await interaction.followup.send("❌ Failed to read or process the image file.", ephemeral=True)

    # Pass the compressed bytes to the modal
    modal = PlushieScanModal(image_bytes=image_bytes)
    # The modal response must use the original deferred interaction
    await interaction.followup.send_modal(modal)


@bot.tree.command(name="plushie_summon", description="View a plushie collection!")
@app_commands.describe(user="User whose collection to view (leave empty for your own)")
async def plushie_summon(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    """Display all registered plushies for a user"""
    target_user = user or interaction.user
    plushies = PlushieManager.get_plushies(target_user.id)
    
    if not plushies:
        if target_user.id == interaction.user.id:
            embed = discord.Embed(
                title="🧸 Zero-G Plushie Collection",
                description="Your collection is empty! Use `/plushie_scan` to register your first plushie!",
                color=discord.Color.blue()
            )
        else:
            embed = discord.Embed(
                title=f"🧸 {target_user.display_name}'s Plushie Collection",
                description=f"{target_user.display_name} hasn't registered any plushies yet!",
                color=discord.Color.blue()
            )
    else:
        # Create a summary list
        plushie_list = "\n".join([
            f"🧸 **{p['name']}** - {p['species']}" 
            for p in plushies
        ])
        
        embed = discord.Embed(
            title=f"🧸 {target_user.display_name}'s Plushie Collection",
            description=plushie_list,
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Total Plushies: {len(plushies)} • Use /plushie_info [user] [name] for details!")
    
    embed.set_thumbnail(url=target_user.display_avatar.url)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="plushie_info", description="View a plushie's full profile, including photo")
@app_commands.describe(name="Name of the plushie", user="User who owns the plushie")
async def plushie_info(interaction: discord.Interaction, name: str, user: Optional[discord.Member] = None):
    target_user = user or interaction.user
    data = PlushieManager.get_plushie_full(target_user.id, name)
    
    if not data:
        return await interaction.response.send_message(f"❌ Couldn't find **{name}** in the roster.", ephemeral=True)

    p_name, species, color, desc, personality, date, image_blob = data
    
    embed = discord.Embed(title=f"🧸 {p_name}'s Profile", description=desc, color=discord.Color.purple())
    embed.add_field(name="🐾 Species", value=species, inline=True)
    embed.add_field(name="🎨 Color", value=color, inline=True)
    embed.add_field(name="✨ Personality", value=personality, inline=False)
    embed.set_footer(text=f"Registered: {date} | Owner: {target_user.display_name}")
    
    file = None
    if image_blob:
        # Create a discord file object from the binary data in the DB
        file = discord.File(io.BytesIO(image_blob), filename="plushie.jpg")
        # Set the embed image URL to reference the attached file
        embed.set_image(url="attachment://plushie.jpg")
    
    # If a file is attached, send it along with the embed
    await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

@bot.tree.command(name="plushie_edit", description="Edit an existing plushie")
@app_commands.describe(name="Name of the plushie to edit", image_url="Optional: New image URL")
async def plushie_edit(interaction: discord.Interaction, name: str, image_url: Optional[str] = None):
    """Edit an existing plushie"""
    plushie = PlushieManager.get_plushie(interaction.user.id, name)
    
    if not plushie:
        return await interaction.response.send_message(
            f"❌ Couldn't find a plushie named **{name}** in your collection.",
            ephemeral=True
        )
    
    modal = PlushieScanModal(image_url=image_url, existing_plushie=plushie)
    await interaction.response.send_modal(modal)


@bot.tree.command(name="embed_create", description="Create a custom embed")
@app_commands.describe(name="Name to save this embed as")
@is_staff_or_admin()
async def embed_create(interaction: discord.Interaction, name: str):
    """Create a new custom embed"""
    # Sanitize filename
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    modal = EmbedBuilderModal(safe_name)
    await interaction.response.send_modal(modal)


@bot.tree.command(name="embed_edit", description="Edit an existing embed")
@app_commands.describe(name="Name of the embed to edit")
@is_staff_or_admin()
async def embed_edit(interaction: discord.Interaction, name: str):
    """Edit an existing embed"""
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    filepath = os.path.join(EMBEDS_FOLDER, f"{safe_name}.json")
    
    if not os.path.exists(filepath):
        return await interaction.response.send_message(
            f"❌ Embed **{name}** not found. Use `/embed_list` to see saved embeds.",
            ephemeral=True
        )
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
    except Exception as e:
        return await interaction.response.send_message(
            f"❌ Failed to load embed: {e}",
            ephemeral=True
        )
    
    modal = EmbedBuilderModal(safe_name, existing_data)
    await interaction.response.send_modal(modal)


@bot.tree.command(name="embed_post", description="Post a saved embed")
@app_commands.describe(name="Name of the embed", channel="Channel to post in")
@is_staff_or_admin()
async def embed_post(interaction: discord.Interaction, name: str, channel: Optional[discord.TextChannel] = None):
    """Post a saved embed to a channel"""
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    filepath = os.path.join(EMBEDS_FOLDER, f"{safe_name}.json")
    
    if not os.path.exists(filepath):
        return await interaction.response.send_message(
            f"❌ Embed **{name}** not found.",
            ephemeral=True
        )
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            embed_data = json.load(f)
    except Exception as e:
        return await interaction.response.send_message(
            f"❌ Failed to load embed: {e}",
            ephemeral=True
        )
    
    # Parse color
    color_value = discord.Color.blue()
    if embed_data.get("color"):
        color_str = embed_data["color"].strip().lower()
        try:
            if color_str.startswith('#'):
                color_value = discord.Color(int(color_str[1:], 16))
            elif color_str == 'red':
                color_value = discord.Color.red()
            elif color_str == 'green':
                color_value = discord.Color.green()
            elif color_str == 'blue':
                color_value = discord.Color.blue()
            elif color_str == 'purple':
                color_value = discord.Color.purple()
            elif color_str == 'gold':
                color_value = discord.Color.gold()
            elif color_str == 'orange':
                color_value = discord.Color.orange()
        except:
            pass
    
    # Build embed
    embed = discord.Embed(
        title=embed_data.get("title") or None,
        description=embed_data.get("description") or None,
        color=color_value
    )
    
    if embed_data.get("footer"):
        embed.set_footer(text=embed_data["footer"])
    
    if embed_data.get("image"):
        embed.set_image(url=embed_data["image"])
    
    # Add fields if any
    for field in embed_data.get("fields", []):
        embed.add_field(
            name=field.get("name", "Field"),
            value=field.get("value", "Value"),
            inline=field.get("inline", False)
        )
    
    target_channel = channel or interaction.channel
    
    try:
        await target_channel.send(embed=embed)
        await interaction.response.send_message(
            f"✅ Embed posted to {target_channel.mention}",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Failed to post embed: {e}",
            ephemeral=True
        )


@bot.tree.command(name="embed_list", description="List all saved embeds")
@is_staff_or_admin()
async def embed_list(interaction: discord.Interaction):
    """List all saved embeds"""
    try:
        files = [f[:-5] for f in os.listdir(EMBEDS_FOLDER) if f.endswith('.json')]
    except Exception as e:
        return await interaction.response.send_message(
            f"❌ Error reading embeds: {e}",
            ephemeral=True
        )
    
    if not files:
        return await interaction.response.send_message(
            "📋 No saved embeds yet. Use `/embed_create` to make one!",
            ephemeral=True
        )
    
    embed = discord.Embed(
        title="📋 Saved Embeds",
        description="\n".join([f"• `{name}`" for name in sorted(files)]),
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Total: {len(files)} embeds")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="embed_delete", description="Delete a saved embed")
@app_commands.describe(name="Name of the embed to delete")
@is_staff_or_admin()
async def embed_delete(interaction: discord.Interaction, name: str):
    """Delete a saved embed"""
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    filepath = os.path.join(EMBEDS_FOLDER, f"{safe_name}.json")
    
    if not os.path.exists(filepath):
        return await interaction.response.send_message(
            f"❌ Embed **{name}** not found.",
            ephemeral=True
        )
    
    try:
        os.remove(filepath)
        await interaction.response.send_message(
            f"✅ Embed **{name}** deleted.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Failed to delete embed: {e}",
            ephemeral=True
        )
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