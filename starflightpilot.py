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
import psycopg2
from psycopg2.extras import RealDictCursor
import io
from PIL import Image
import base64
import re

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
TOKEN = os.getenv('DISCORD_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')  # PostgreSQL connection string
BACKUP_FILE = 'ship_backup.json'
MISSIONS_FILE = 'missions.json'
ENCOURAGEMENTS_FILE = 'encouragements.json'
EMBEDS_FOLDER = 'saved_embeds'
# NOTE: Replace with your actual Staff Role ID
STAFF_ROLE_ID = 1454538884682612940

# Image settings
MAX_IMAGE_SIZE = (800, 800)  # Max dimensions
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB max upload

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('StarflightBot')

# Ensure folders exist
os.makedirs(EMBEDS_FOLDER, exist_ok=True)

# --- DATABASE CONNECTION ---

class Database:
    """Database connection manager"""
    
    @staticmethod
    def get_connection():
        """Get a database connection"""
        try:
            conn = psycopg2.connect(DATABASE_URL)
            return conn
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return None
    
    @staticmethod
    def init_tables():
        """Initialize database tables"""
        conn = Database.get_connection()
        if not conn:
            logger.error("Failed to initialize database tables")
            return False
        
        try:
            with conn.cursor() as cur:
                # Plushies table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS plushies (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        species VARCHAR(100) NOT NULL,
                        color VARCHAR(100),
                        description TEXT NOT NULL,
                        personality VARCHAR(200),
                        registered_date DATE NOT NULL,
                        image_data TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, name)
                    )
                """)
                
                # Create index for faster lookups
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_plushies_user 
                    ON plushies(user_id)
                """)
                
                conn.commit()
                logger.info("Database tables initialized successfully")
                return True
        except Exception as e:
            logger.error(f"Failed to initialize tables: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()


# --- IMAGE PROCESSING ---

class ImageProcessor:
    """Handles image compression and encoding"""
    
    @staticmethod
    async def process_attachment(attachment: discord.Attachment) -> Optional[str]:
        """Process and compress an image attachment"""
        
        # Check file size
        if attachment.size > MAX_FILE_SIZE:
            return None
        
        # Check if it's an image
        if not attachment.content_type or not attachment.content_type.startswith('image/'):
            return None
        
        try:
            # Download image
            image_data = await attachment.read()
            image = Image.open(io.BytesIO(image_data))
            
            # Convert to RGB if necessary
            if image.mode in ('RGBA', 'P'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'RGBA':
                    background.paste(image, mask=image.split()[3])
                else:
                    background.paste(image)
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Resize if needed
            # Image.Resampling.LANCZOS is the recommended modern approach
            image.thumbnail(MAX_IMAGE_SIZE, Image.LANCZOS)
            
            # Compress to JPEG
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=85, optimize=True)
            output.seek(0)
            
            # Encode to base64
            encoded = base64.b64encode(output.read()).decode('utf-8')
            
            return encoded
            
        except Exception as e:
            logger.error(f"Failed to process image: {e}")
            return None
    
    @staticmethod
    def create_discord_file(encoded_data: str, filename: str = "plushie.jpg") -> Optional[discord.File]:
        """Create a Discord file from base64 encoded data"""
        try:
            image_bytes = base64.b64decode(encoded_data)
            return discord.File(io.BytesIO(image_bytes), filename=filename)
        except Exception as e:
            logger.error(f"Failed to create Discord file: {e}")
            return None


# --- DATA STORAGE ---

class PlushieManager:
    """Manages plushie collection storage in database"""
    
    @staticmethod
    def add_plushie(user_id: int, plushie_data: Dict) -> bool:
        """Add a plushie to a user's collection"""
        conn = Database.get_connection()
        if not conn:
            return False
        
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO plushies 
                    (user_id, name, species, color, description, personality, registered_date, image_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id,
                    plushie_data['name'],
                    plushie_data['species'],
                    plushie_data.get('color', 'Unknown'),
                    plushie_data['description'],
                    plushie_data.get('personality', 'Mysterious'),
                    plushie_data['registered_date'],
                    plushie_data.get('image_data')
                ))
                conn.commit()
                return True
        except psycopg2.IntegrityError:
            conn.rollback()
            return False # Duplicate entry
        except Exception as e:
            logger.error(f"Failed to add plushie: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    @staticmethod
    def update_plushie(user_id: int, old_name: str, plushie_data: Dict) -> bool:
        """Update an existing plushie"""
        conn = Database.get_connection()
        if not conn:
            return False
        
        # Normalize the image_data key lookup to allow it to be optional in the input dict
        image_data = plushie_data.get('image_data', plushie_data.get('existing_image_data'))

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE plushies 
                    SET name = %s, species = %s, color = %s, 
                        description = %s, personality = %s, image_data = %s
                    WHERE user_id = %s AND LOWER(name) = LOWER(%s)
                """, (
                    plushie_data['name'],
                    plushie_data['species'],
                    plushie_data.get('color', 'Unknown'),
                    plushie_data['description'],
                    plushie_data.get('personality', 'Mysterious'),
                    image_data,
                    user_id,
                    old_name
                ))
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update plushie: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    @staticmethod
    def get_plushies(user_id: int) -> List[Dict]:
        """Get all plushies for a user"""
        conn = Database.get_connection()
        if not conn:
            return []
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, user_id, name, species, color, description, 
                            personality, registered_date, image_data, created_at
                    FROM plushies 
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """, (user_id,))
                results = cur.fetchall()
                # Convert date/timestamp objects to strings for clean dict output
                for row in results:
                    if row['registered_date']:
                        row['registered_date'] = row['registered_date'].isoformat()
                    if row['created_at']:
                        row['created_at'] = row['created_at'].isoformat()
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Failed to get plushies: {e}")
            return []
        finally:
            conn.close()
    
    @staticmethod
    def get_plushie(user_id: int, plushie_name: str) -> Optional[Dict]:
        """Get a specific plushie by name"""
        conn = Database.get_connection()
        if not conn:
            return None
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, user_id, name, species, color, description, 
                            personality, registered_date, image_data, created_at
                    FROM plushies 
                    WHERE user_id = %s AND LOWER(name) = LOWER(%s)
                """, (user_id, plushie_name))
                result = cur.fetchone()
                if result:
                    # Convert date/timestamp objects to strings
                    if result.get('registered_date'):
                        result['registered_date'] = result['registered_date'].isoformat()
                    if result.get('created_at'):
                        result['created_at'] = result['created_at'].isoformat()
                    return dict(result)
                return None
        except Exception as e:
            logger.error(f"Failed to get plushie: {e}")
            return None
        finally:
            conn.close()
    
    @staticmethod
    def remove_plushie(user_id: int, plushie_name: str) -> bool:
        """Remove a plushie from a user's collection"""
        conn = Database.get_connection()
        if not conn:
            return False
        
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM plushies 
                    WHERE user_id = %s AND LOWER(name) = LOWER(%s)
                """, (user_id, plushie_name))
                conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to remove plushie: {e}")
            conn.rollback()
            return False
        finally:
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
        if not os.path.exists(MISSIONS_FILE):
            MissionGenerator.save_missions(MissionGenerator.DEFAULT_MISSIONS)
            return MissionGenerator.DEFAULT_MISSIONS
        
        try:
            with open(MISSIONS_FILE, 'r', encoding='utf-8') as f:
                missions = json.load(f)
                if isinstance(missions, list) and missions:
                    return missions
                return MissionGenerator.DEFAULT_MISSIONS
        except Exception as e:
            logger.error(f"Failed to load missions: {e}")
            return MissionGenerator.DEFAULT_MISSIONS
    
    @staticmethod
    def save_missions(missions: List[str]) -> bool:
        try:
            with open(MISSIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(missions, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save missions: {e}")
            return False
    
    @staticmethod
    def get_mission() -> str:
        missions = MissionGenerator.load_missions()
        return random.choice(missions)


class EncouragementGenerator:
    """Generates encouraging messages"""
    
    DEFAULT_ENCOURAGEMENTS = [
        "is sending you rocket fuel! 🚀✨",
        "is refueling your tank with cosmic energy! ⭐💫",
        "thinks you're doing stellar! 🌟🌙",
        "is beaming positive vibes your way! 🛸💖",
        "says you're out of this world! 🌍🪐",
        "is sending you galaxy-sized hugs! 🌌🤗",
        "believes you can reach the stars! ✨🌠",
        "is your co-pilot cheering you on! 🛰️💪",
        "sent you a care package from Mission Control! 📦👍",
        "thinks you shine brighter than a supernova! 💫⭐"
    ]
    
    @staticmethod
    def load_encouragements() -> List[str]:
        if not os.path.exists(ENCOURAGEMENTS_FILE):
            EncouragementGenerator.save_encouragements(EncouragementGenerator.DEFAULT_ENCOURAGEMENTS)
            return EncouragementGenerator.DEFAULT_ENCOURAGEMENTS
        
        try:
            with open(ENCOURAGEMENTS_FILE, 'r', encoding='utf-8') as f:
                encouragements = json.load(f)
                if isinstance(encouragements, list) and encouragements:
                    return encouragements
                return EncouragementGenerator.DEFAULT_ENCOURAGEMENTS
        except Exception as e:
            logger.error(f"Failed to load encouragements: {e}")
            return EncouragementGenerator.DEFAULT_ENCOURAGEMENTS
    
    @staticmethod
    def save_encouragements(encouragements: List[str]) -> bool:
        try:
            with open(ENCOURAGEMENTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(encouragements, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save encouragements: {e}")
            return False
    
    @staticmethod
    def get_encouragement() -> str:
        encouragements = EncouragementGenerator.load_encouragements()
        return random.choice(encouragements)


# --- UTILITIES ---

class BackupManager:
    """Handles all backup-related operations"""
    
    @staticmethod
    def load() -> Optional[Dict]:
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
        try:
            with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to save backup: {e}")
            return False
    
    @staticmethod
    async def create_backup(guild: discord.Guild) -> Dict:
        backup = {"roles": [], "categories": []}
        
        for role in reversed(guild.roles):
            if role.is_default():
                continue
            backup["roles"].append({
                "name": role.name,
                "color": role.color.value,
                "permissions": role.permissions.value,
                "hoist": role.hoist
            })
        
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
                logger.warning(f"Permission denied editing {item.name}")
            except Exception as e:
                logger.error(f"Error editing {item.name}: {e}")


class SyncManager:
    """Handles server syncing operations"""
    
    @staticmethod
    async def sync_roles(guild: discord.Guild, backup_roles: List[Dict]):
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
        
        # Create/Update roles from backup
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
        
        # Create/Update categories and channels
        for c in backup_categories:
            await SyncManager._sync_category(guild, c)
    
    @staticmethod
    async def _sync_category(guild: discord.Guild, cat_data: Dict):
        cat_name = cat_data.get("name")
        cat = discord.utils.get(guild.categories, name=cat_name)
        
        try:
            if not cat:
                cat = await guild.create_category(cat_name)
                logger.info(f"Created category: {cat_name}")
            
            await BackupManager.apply_overwrites(guild, cat, cat_data.get("overwrites", []))
            
            backup_channels = cat_data.get("channels", [])
            backup_chan_names = {ch.get("name") for ch in backup_channels}
            
            # Delete channels not in backup within this category
            for actual_ch in cat.channels:
                if actual_ch.name not in backup_chan_names:
                    try:
                        await actual_ch.delete()
                        logger.info(f"Deleted channel: {actual_ch.name}")
                    except Exception as e:
                        logger.error(f"Failed to delete channel {actual_ch.name}: {e}")
            
            # Create/Update channels in this category
            for ch_data in backup_channels:
                await SyncManager._sync_channel(guild, cat, ch_data)
                
        except Exception as e:
            logger.error(f"Failed to sync category {cat_name}: {e}")
    
    @staticmethod
    async def _sync_channel(guild: discord.Guild, cat: discord.CategoryChannel, ch_data: Dict):
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
        Database.init_tables()
        await self.tree.sync() # Sync commands globally/per-guild as needed


bot = StarflightBot()


@bot.event
async def on_ready():
    logger.info(f'🚀 Starflight Pilot online as {bot.user}')


# --- PERMISSION CHECK ---

def is_staff_or_admin():
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


# --- SLASH COMMANDS (STAFF) ---

@bot.command()
@commands.has_permissions(administrator=True)
async def sync_tree(ctx):
    await bot.tree.sync()
    await ctx.send("📡 Command tree synced to Discord.")


@bot.tree.command(name="list_roles", description="Get a list of role mention codes")
@is_staff_or_admin()
async def list_roles(interaction: discord.Interaction):
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


@bot.tree.command(name="post_embed", description="Post a JSON template")
@app_commands.describe(filename="JSON filename", channel="Target channel")
@is_staff_or_admin()
async def post_embed(interaction: discord.Interaction, filename: str, channel: discord.TextChannel):
    filepath = os.path.join(EMBEDS_FOLDER, filename if filename.endswith('.json') else filename + '.json')
    
    if not os.path.exists(filepath):
        return await interaction.response.send_message(f"❌ `{filepath}` not found. (Must be in '{EMBEDS_FOLDER}')", ephemeral=True)
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        return await interaction.response.send_message(f"❌ Error reading file: {e}", ephemeral=True)
    
    embed_list = []
    for e_data in data.get("embeds", []):
        embed = discord.Embed(
            title=e_data.get("title", ""),
            description=e_data.get("description", ""),
            color=e_data.get("color", discord.Color.blue().value),
            url=e_data.get("url")
        )
        
        if "image" in e_data and isinstance(e_data["image"], dict):
            embed.set_image(url=e_data["image"].get("url"))
        
        if "thumbnail" in e_data and isinstance(e_data["thumbnail"], dict):
            embed.set_thumbnail(url=e_data["thumbnail"].get("url"))

        if "footer" in e_data:
            footer_text = e_data["footer"].get("text") if isinstance(e_data["footer"], dict) else str(e_data["footer"])
            embed.set_footer(text=footer_text)
        
        if "author" in e_data and isinstance(e_data["author"], dict):
            embed.set_author(name=e_data["author"].get("name"), url=e_data["author"].get("url"), icon_url=e_data["author"].get("icon_url"))

        for field in e_data.get("fields", []):
            embed.add_field(name=field.get("name", "\u200b"), value=field.get("value", "\u200b"), inline=field.get("inline", False))
        
        embed_list.append(embed)
    
    try:
        await channel.send(content=data.get("content", ""), embeds=embed_list)
        await interaction.response.send_message(f"✅ Sent `{filename}` to {channel.mention}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error sending message: {e}", ephemeral=True)


@bot.tree.command(name="backup_ship", description="Saves current server state")
@is_staff_or_admin()
async def backup_ship(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    backup = await BackupManager.create_backup(interaction.guild)
    
    if BackupManager.save(backup):
        await interaction.followup.send("💾 Backup Complete. The ship state has been recorded.")
    else:
        await interaction.followup.send("❌ Failed to save backup.")


@bot.tree.command(name="sync_ship", description="Restores from backup and REMOVES extras")
@is_staff_or_admin()
async def sync_ship(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    data = BackupManager.load()
    if not data:
        return await interaction.followup.send("❌ No backup file found. Cannot perform sync.")
    
    guild = interaction.guild
    
    await SyncManager.sync_roles(guild, data.get("roles", []))
    await SyncManager.sync_categories(guild, data.get("categories", []))
    
    await interaction.followup.send("🚀 Sync Complete: Server matches backup exactly. Unmanaged roles/channels were removed.")


# --- MODALS ---

class IntroModal(discord.ui.Modal, title="✨ Introduce Yourself to the Crew!"):
    age = discord.ui.TextInput(label="Age/Age Range", placeholder="Your age or age range", required=True, max_length=50)
    pronouns = discord.ui.TextInput(label="Pronouns", placeholder="Your pronouns", required=True, max_length=100)
    role = discord.ui.TextInput(label="Community Role", placeholder="Your role (optional)", required=False, max_length=200)
    favorites = discord.ui.TextInput(label="Favorites", placeholder="Things you love!", style=discord.TextStyle.paragraph, required=True, max_length=500)
    about = discord.ui.TextInput(label="More About You", placeholder="Share more!", style=discord.TextStyle.paragraph, required=False, max_length=1000)
    
    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel
    
    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"🚀 Welcome Aboard, {interaction.user.display_name}!",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
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
            await interaction.response.send_message("✅ Your introduction has been posted! Welcome aboard! 🚀", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed to post introduction: {e}", ephemeral=True)


class PlushieScanModal(discord.ui.Modal, title="🧸 Register Your Plushie!"):
    name = discord.ui.TextInput(label="Plushie Name", placeholder="What's your plushie's name?", required=True, max_length=100)
    species = discord.ui.TextInput(label="Species/Type", placeholder="E.g., Starfox, Galactic Bear, Alien Slug", required=True, max_length=100)
    color = discord.ui.TextInput(label="Primary Color", placeholder="E.g., Blue, Neon Green, Rainbow", required=False, max_length=100)
    personality = discord.ui.TextInput(label="Personality", placeholder="E.g., Brave explorer, Shy scientist, Sleepy pilot", required=False, max_length=200)
    description = discord.ui.TextInput(label="Description", placeholder="Tell us about their story and why they are special!", style=discord.TextStyle.paragraph, required=True, max_length=1000)

    def __init__(self, image_data: Optional[str] = None):
        super().__init__()
        self.image_data = image_data
    
    async def on_submit(self, interaction: discord.Interaction):
        plushie_data = {
            'name': self.name.value.strip(),
            'species': self.species.value.strip(),
            'color': self.color.value.strip() or 'Unknown',
            'personality': self.personality.value.strip() or 'Mysterious',
            'description': self.description.value.strip(),
            'registered_date': datetime.now(timezone.utc).date().isoformat(),
            'image_data': self.image_data
        }

        if PlushieManager.add_plushie(interaction.user.id, plushie_data):
            msg = f"✅ Plushie **{plushie_data['name']}** successfully registered! Welcome to the crew, little buddy!"
            if not self.image_data:
                msg += "\n\n**Note:** To add an image, use the `/update_plushie` command and attach the picture to the command message."
            
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ Failed to register **{plushie_data['name']}**. You might already have a plushie with that name.", 
                ephemeral=True
            )


class PlushieUpdateModal(discord.ui.Modal, title="✨ Update Plushie Data!"):
    new_name = discord.ui.TextInput(label="New Name (can be same)", required=True, max_length=100)
    species = discord.ui.TextInput(label="Species/Type", required=True, max_length=100)
    color = discord.ui.TextInput(label="Primary Color", required=False, max_length=100)
    personality = discord.ui.TextInput(label="Personality", required=False, max_length=200)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, required=True, max_length=1000)

    def __init__(self, old_plushie: Dict):
        super().__init__()
        self.old_plushie = old_plushie
        self.old_name = old_plushie['name']
        
        # Pre-fill fields
        self.new_name.default = old_plushie['name']
        self.species.default = old_plushie['species']
        self.color.default = old_plushie.get('color', '')
        self.personality.default = old_plushie.get('personality', '')
        self.description.default = old_plushie['description']

    async def on_submit(self, interaction: discord.Interaction):
        plushie_data = {
            'name': self.new_name.value.strip(),
            'species': self.species.value.strip(),
            'color': self.color.value.strip() or 'Unknown',
            'personality': self.personality.value.strip() or 'Mysterious',
            'description': self.description.value.strip(),
            'existing_image_data': self.old_plushie.get('image_data') # Preserve existing image if no new one is uploaded
        }

        if PlushieManager.update_plushie(interaction.user.id, self.old_name, plushie_data):
            await interaction.response.send_message(
                f"✅ Plushie **{self.old_name}** successfully updated to **{plushie_data['name']}**!", 
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ Failed to update **{self.old_name}**. The new name might already be taken by another of your plushies.", 
                ephemeral=True
            )


# --- SLASH COMMANDS (GENERAL) ---

@bot.tree.command(name="intro", description="Post an introduction about yourself in the current channel.")
@app_commands.describe(channel="The channel to post the introduction in")
async def intro_command(interaction: discord.Interaction, channel: discord.TextChannel):
    """Triggers the IntroModal"""
    if not channel.permissions_for(interaction.user).send_messages:
        return await interaction.response.send_message("❌ You do not have permission to post in that channel.", ephemeral=True)
    
    await interaction.response.send_modal(IntroModal(channel=channel))


# --- SLASH COMMANDS (PLUSHIES) ---

@bot.tree.command(name="register_plushie", description="Register a new plushie companion!")
@app_commands.describe(image="Optional image attachment for your plushie")
async def register_plushie(interaction: discord.Interaction, image: Optional[discord.Attachment] = None):
    await interaction.response.defer(ephemeral=True, thinking=True)

    image_data = None
    if image:
        image_data = await ImageProcessor.process_attachment(image)
        if not image_data:
            await interaction.followup.send(
                "⚠️ Image upload failed. Please ensure the file is under 5MB and is a valid image type. You can still register the plushie without a picture.", 
                ephemeral=True
            )

    await interaction.followup.send_modal(PlushieScanModal(image_data=image_data))


@bot.tree.command(name="view_plushie", description="View the details of a plushie in your collection.")
@app_commands.describe(name="The name of the plushie to view")
async def view_plushie(interaction: discord.Interaction, name: str):
    await interaction.response.defer(thinking=True)
    
    plushie = PlushieManager.get_plushie(interaction.user.id, name)
    
    if not plushie:
        return await interaction.followup.send(f"❌ Plushie **{name}** not found in your collection.", ephemeral=True)

    embed = discord.Embed(
        title=f"🧸 {plushie['name']} - The {plushie['species']}",
        color=discord.Color.from_rgb(173, 216, 230), # Light blue
        timestamp=datetime.now(timezone.utc)
    )

    embed.set_author(name=f"{interaction.user.display_name}'s Companion")
    
    embed.add_field(name="🎨 Color", value=plushie.get('color', 'N/A'), inline=True)
    embed.add_field(name="🎭 Personality", value=plushie.get('personality', 'N/A'), inline=True)
    embed.add_field(name="🗓️ Registered", value=plushie.get('registered_date', 'N/A'), inline=True)
    embed.add_field(name="📖 Story/Description", value=plushie['description'], inline=False)
    
    file = None
    if plushie.get('image_data'):
        file = ImageProcessor.create_discord_file(plushie['image_data'])
        if file:
            embed.set_image(url=f"attachment://{file.filename}")
    
    await interaction.followup.send(embed=embed, file=file or discord.utils.MISSING)


@bot.tree.command(name="list_plushies", description="See all the plushies you have registered.")
async def list_plushies(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True, thinking=True)
    
    plushies = PlushieManager.get_plushies(interaction.user.id)
    
    if not plushies:
        return await interaction.followup.send("You haven't registered any plushies yet! Use `/register_plushie` to scan your first companion. 🌟", ephemeral=True)

    plushie_list = [f"• **{p['name']}** ({p['species']})" for p in plushies]
    
    embed = discord.Embed(
        title=f"🔭 {interaction.user.display_name}'s Plushie Fleet ({len(plushies)})",
        description="\n".join(plushie_list),
        color=discord.Color.purple(),
        timestamp=datetime.now(timezone.utc)
    )
    
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="update_plushie", description="Update the details of an existing plushie.")
@app_commands.describe(name="The name of the plushie to update", image="Optional new image attachment for your plushie")
async def update_plushie(interaction: discord.Interaction, name: str, image: Optional[discord.Attachment] = None):
    await interaction.response.defer(ephemeral=True, thinking=True)
    
    plushie = PlushieManager.get_plushie(interaction.user.id, name)
    
    if not plushie:
        return await interaction.followup.send(f"❌ Plushie **{name}** not found in your collection.", ephemeral=True)

    # Handle optional image update
    image_data = plushie.get('image_data') # Default to existing image
    if image:
        new_image_data = await ImageProcessor.process_attachment(image)
        if new_image_data:
            image_data = new_image_data
        else:
            await interaction.followup.send(
                "⚠️ New image upload failed. Keeping the old picture (if any). File size must be under 5MB.", 
                ephemeral=True
            )

    # Use the existing plushie data to pre-fill the modal
    modal = PlushieUpdateModal(plushie)
    
    # Store the potential new image data in the modal for on_submit handling
    # We directly update the plushie dict before passing it to the manager
    plushie['image_data'] = image_data

    # Send modal for text updates (name, species, etc.)
    await interaction.followup.send_modal(PlushieUpdateModal(plushie))


@bot.tree.command(name="remove_plushie", description="Remove a plushie from your collection.")
@app_commands.describe(name="The name of the plushie to remove")
async def remove_plushie(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True, thinking=True)
    
    if PlushieManager.remove_plushie(interaction.user.id, name):
        await interaction.followup.send(f"✅ Plushie **{name}** has been safely beamed off the ship. Goodbye, little friend! 😢", ephemeral=True)
    else:
        await interaction.followup.send(f"❌ Plushie **{name}** not found in your collection. Can't remove what isn't there.", ephemeral=True)


# --- SLASH COMMANDS (FUN) ---

@bot.tree.command(name="mission", description="Get a fun, simple mission for little astronauts!")
async def mission_command(interaction: discord.Interaction):
    mission = MissionGenerator.get_mission()
    
    embed = discord.Embed(
        title="🛰️ Daily Mission Briefing",
        description=f"**Your mission, Space Cadet {interaction.user.display_name}, is to...**\n\n**{mission}**",
        color=discord.Color.gold(),
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text="Good luck, and happy exploring!")
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="fuel_refill", description="Sending fuel to a crew member!")
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
        logger.error("DISCORD_TOKEN environment variable not set.")
    elif not DATABASE_URL:
        logger.error("DATABASE_URL environment variable not set. Plushie features will fail.")
    else:
        # Initialize tables before running the bot
        Database.init_tables() 
        bot.run(TOKEN)