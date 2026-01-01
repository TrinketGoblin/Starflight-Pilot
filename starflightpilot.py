import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import logging
import random
import io
import re
import asyncio
from typing import Optional, Dict, List
from datetime import datetime, timezone
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from dotenv import load_dotenv
from PIL import Image
import aiohttp

# =========================
# CONFIGURATION
# =========================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "1454538884682612940"))

# Data files
MISSIONS_FILE = "missions.json"
ENCOURAGEMENTS_FILE = "encouragements.json"
SPACE_FACTS_FILE = "space_facts.json"

# Space-themed announcement styling
ANNOUNCEMENT_CONFIG = {
    "header": {
        "color": 0x7395cc,
        "description": "🎛️ **Announcement**",
        "image_url": "https://64.media.tumblr.com/fb4527b4d5ba87d89b66a9c7ce471836/01cb3d1ba106fa8c-2e/s1280x1920/e393f5a5a2d9275d944befbe0c0a14f051176874.pnj"
    },
    "footer": {
        "color": 0xf0f4ff,
        "description": "🚀 **pls invite ppl to join our discord server and help us grow!**\n\n[Click here](https://discord.gg/4QzQYeuApB) to join!",
        "image_url": "https://64.media.tumblr.com/b1087d6d3803689dd69ed77055e45141/01cb3d1ba106fa8c-7a/s1280x1920/b8342d92c350abeee78d7c8b0636625679dfc8ae.pnj"
    }
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("StarflightPilot")

# =========================
# DATABASE CONNECTION POOL
# =========================

class DatabasePool:
    """Manages PostgreSQL connection pooling"""
    _pool: Optional[SimpleConnectionPool] = None
    
    @classmethod
    def initialize(cls):
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL environment variable not configured")
        cls._pool = SimpleConnectionPool(1, 10, DATABASE_URL)
        logger.info("Database connection pool initialized")
    
    @classmethod
    @contextmanager
    def get_conn(cls):
        if cls._pool is None:
            cls.initialize()
        conn = cls._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cls._pool.putconn(conn)

# =========================
# DATABASE INITIALIZATION
# =========================
def migrate_db():
    """Run database migrations"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor() as cur:
            # Add image_data column if it doesn't exist
            cur.execute("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='plushies' AND column_name='image_data'
                    ) THEN
                        ALTER TABLE plushies ADD COLUMN image_data BYTEA;
                    END IF;
                END $$;
            """)
    logger.info("Database migrations completed")

def init_db():
    """Initialize all database tables"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor() as cur:
            # Plushies table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS plushies (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    name TEXT NOT NULL,
                    species TEXT,
                    color TEXT,
                    personality TEXT,
                    description TEXT,
                    registered_date TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    image_data BYTEA
                )
            """)
            cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_plushie_user_name
                ON plushies (user_id, LOWER(name))
            """)
            
            # Saved embeds table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS saved_embeds (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    title TEXT,
                    description TEXT,
                    color TEXT,
                    image_url TEXT,
                    footer TEXT,
                    fields JSONB DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Server backups table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS server_backups (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    backup_data JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_backups_guild_created 
                ON server_backups (guild_id, created_at DESC)
            """)
    
    migrate_db()  # Add this line
    logger.info("Database tables initialized")

# =========================
# PLUSHIE MANAGER
# =========================

class PlushieManager:
    """Manages plushie collection operations"""
    
    @staticmethod
    def create(user_id: int, data: Dict, image: Optional[bytes]) -> bool:
        try:
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO plushies (user_id, name, species, color, personality, description, image_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        user_id, data["name"], data["species"], data["color"],
                        data["personality"], data["description"],
                        psycopg2.Binary(image) if image else None
                    ))
            return True
        except Exception as e:
            logger.error(f"Failed to create plushie: {e}")
            return False

    @staticmethod
    def update(user_id: int, name: str, data: Dict, image: Optional[bytes] = None) -> bool:
        try:
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    updates = []
                    params = []
                    
                    for field in ["species", "color", "personality", "description"]:
                        if field in data:
                            updates.append(f"{field} = %s")
                            params.append(data[field])
                    
                    if image is not None:
                        updates.append("image_data = %s")
                        params.append(psycopg2.Binary(image))
                    
                    if not updates:
                        return False
                    
                    params.extend([user_id, name])
                    query = f"UPDATE plushies SET {', '.join(updates)} WHERE user_id = %s AND LOWER(name) = LOWER(%s)"
                    cur.execute(query, params)
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update plushie: {e}")
            return False

    @staticmethod
    def get_all(user_id: int) -> List[Dict]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT name, species FROM plushies 
                    WHERE user_id = %s ORDER BY name
                """, (user_id,))
                return cur.fetchall()

    @staticmethod
    def get_one(user_id: int, name: str) -> Optional[Dict]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM plushies 
                    WHERE user_id = %s AND LOWER(name) = LOWER(%s)
                """, (user_id, name))
                return cur.fetchone()

    @staticmethod
    def delete(user_id: int, name: str) -> bool:
        with DatabasePool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM plushies 
                    WHERE user_id = %s AND LOWER(name) = LOWER(%s)
                """, (user_id, name))
                return cur.rowcount > 0

# =========================
# EMBED MANAGER
# =========================

class EmbedManager:
    """Manages saved embed templates"""
    
    @staticmethod
    def save(name: str, data: Dict) -> bool:
        try:
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO saved_embeds (name, title, description, color, image_url, footer, fields)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (name) DO UPDATE SET 
                            title = EXCLUDED.title, description = EXCLUDED.description,
                            color = EXCLUDED.color, image_url = EXCLUDED.image_url,
                            footer = EXCLUDED.footer, fields = EXCLUDED.fields,
                            updated_at = CURRENT_TIMESTAMP
                    """, (
                        name, data.get("title"), data.get("description"), data.get("color"),
                        data.get("image"), data.get("footer"), json.dumps(data.get("fields", []))
                    ))
            return True
        except Exception as e:
            logger.error(f"Failed to save embed: {e}")
            return False

    @staticmethod
    def get(name: str) -> Optional[Dict]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM saved_embeds WHERE name = %s", (name,))
                result = cur.fetchone()
                if result:
                    result["image"] = result.pop("image_url")
                return result

    @staticmethod
    def list_all() -> List[str]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT name FROM saved_embeds ORDER BY name")
                return [r[0] for r in cur.fetchall()]

    @staticmethod
    def delete(name: str) -> bool:
        with DatabasePool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM saved_embeds WHERE name = %s", (name,))
                return cur.rowcount > 0

# =========================
# BACKUP MANAGER
# =========================

class BackupManager:
    """Manages server backup and restore operations"""
    
    @staticmethod
    async def create_backup(guild: discord.Guild) -> Dict:
        data = {"roles": [], "categories": []}
        
        for role in reversed(guild.roles):
            if role.is_default() or role.managed:
                continue
            data["roles"].append({
                "id": role.id,
                "name": role.name,
                "color": role.color.value,
                "permissions": role.permissions.value,
                "hoist": role.hoist
            })
        
        for cat in guild.categories:
            cat_data = {
                "id": cat.id,
                "name": cat.name,
                "overwrites": BackupManager._serialize_overwrites(cat.overwrites),
                "channels": []
            }
            for ch in cat.channels:
                cat_data["channels"].append({
                    "id": ch.id,
                    "name": ch.name,
                    "type": str(ch.type),
                    "overwrites": BackupManager._serialize_overwrites(ch.overwrites)
                })
            data["categories"].append(cat_data)
        
        return data

    @staticmethod
    def save_to_db(guild_id: int, data: Dict) -> bool:
        try:
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO server_backups (guild_id, backup_data) 
                        VALUES (%s, %s)
                    """, (guild_id, json.dumps(data)))
            return True
        except Exception as e:
            logger.error(f"Backup save failed: {e}")
            return False

    @staticmethod
    def load_from_db(guild_id: int) -> Optional[Dict]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT backup_data FROM server_backups 
                    WHERE guild_id = %s ORDER BY created_at DESC LIMIT 1
                """, (guild_id,))
                result = cur.fetchone()
                return result["backup_data"] if result else None

    @staticmethod
    async def restore(guild: discord.Guild, data: Dict):
        role_map = {}
        seen_role_ids = set()
        seen_role_names = set()
        
        # Restore roles with deduplication
        for r_data in data.get("roles", []):
            try:
                role_id = r_data.get("id")
                role_name = r_data["name"]
                
                if role_id and role_id in seen_role_ids:
                    logger.warning(f"Skipping duplicate role ID: {role_name} ({role_id})")
                    continue
                if role_name in seen_role_names:
                    logger.warning(f"Skipping duplicate role name: {role_name}")
                    continue
                
                if role_id:
                    seen_role_ids.add(role_id)
                seen_role_names.add(role_name)
                
                existing_role = guild.get_role(role_id) if role_id else None
                if not existing_role:
                    existing_role = discord.utils.get(guild.roles, name=role_name)
                
                if existing_role:
                    await existing_role.edit(
                        name=role_name,
                        color=discord.Color(r_data["color"]),
                        permissions=discord.Permissions(r_data["permissions"]),
                        hoist=r_data["hoist"]
                    )
                    role_map[role_name] = existing_role
                    logger.info(f"Updated existing role: {role_name}")
                else:
                    new_role = await guild.create_role(
                        name=role_name,
                        color=discord.Color(r_data["color"]),
                        permissions=discord.Permissions(r_data["permissions"]),
                        hoist=r_data["hoist"]
                    )
                    role_map[role_name] = new_role
                    logger.info(f"Created new role: {role_name}")
            except Exception as e:
                logger.error(f"Failed to restore role {r_data['name']}: {e}")

        seen_cat_ids = set()
        seen_cat_names = set()
        
        # Restore categories with deduplication
        for cat_data in data.get("categories", []):
            try:
                cat_id = cat_data.get("id")
                cat_name = cat_data["name"]
                
                if cat_id and cat_id in seen_cat_ids:
                    logger.warning(f"Skipping duplicate category ID: {cat_name}")
                    continue
                if cat_name in seen_cat_names:
                    logger.warning(f"Skipping duplicate category name: {cat_name}")
                    continue
                
                if cat_id:
                    seen_cat_ids.add(cat_id)
                seen_cat_names.add(cat_name)
                
                existing_cat = guild.get_channel(cat_id) if cat_id else None
                if not existing_cat:
                    existing_cat = discord.utils.get(guild.categories, name=cat_name)
                
                overwrites = BackupManager._deserialize_overwrites(guild, cat_data["overwrites"], role_map)
                
                if existing_cat and isinstance(existing_cat, discord.CategoryChannel):
                    await existing_cat.edit(name=cat_name, overwrites=overwrites)
                    new_cat = existing_cat
                    logger.info(f"Updated existing category: {cat_name}")
                else:
                    new_cat = await guild.create_category(name=cat_name, overwrites=overwrites)
                    logger.info(f"Created new category: {cat_name}")

                seen_ch_ids = set()
                seen_ch_names = set()
                
                for ch_data in cat_data.get("channels", []):
                    try:
                        ch_id = ch_data.get("id")
                        ch_name = ch_data["name"]
                        
                        if ch_id and ch_id in seen_ch_ids:
                            logger.warning(f"Skipping duplicate channel ID: {ch_name}")
                            continue
                        if ch_name in seen_ch_names:
                            logger.warning(f"Skipping duplicate channel name: {ch_name}")
                            continue
                        
                        if ch_id:
                            seen_ch_ids.add(ch_id)
                        seen_ch_names.add(ch_name)
                        
                        existing_ch = guild.get_channel(ch_id) if ch_id else None
                        if not existing_ch:
                            existing_ch = discord.utils.get(guild.channels, name=ch_name)
                        
                        ch_overwrites = BackupManager._deserialize_overwrites(guild, ch_data["overwrites"], role_map)
                        
                        if existing_ch:
                            await existing_ch.edit(name=ch_name, category=new_cat, overwrites=ch_overwrites)
                            logger.info(f"Updated existing channel: {ch_name}")
                        else:
                            if ch_data["type"] == "text":
                                await new_cat.create_text_channel(name=ch_name, overwrites=ch_overwrites)
                            elif ch_data["type"] == "voice":
                                await new_cat.create_voice_channel(name=ch_name, overwrites=ch_overwrites)
                            logger.info(f"Created new channel: {ch_name}")
                    except Exception as e:
                        logger.error(f"Failed to restore channel {ch_data['name']}: {e}")
            except Exception as e:
                logger.error(f"Failed to restore category {cat_data['name']}: {e}")

    @staticmethod
    def _serialize_overwrites(overwrites):
        return [{
            "id": target.id,
            "name": target.name,
            "is_role": isinstance(target, discord.Role),
            "allow": ovr.pair()[0].value,
            "deny": ovr.pair()[1].value
        } for target, ovr in overwrites.items()]

    @staticmethod
    def _deserialize_overwrites(guild, overwrites_data, role_map):
        overwrites = {}
        for ovr in overwrites_data:
            target = None
            
            if ovr["is_role"]:
                target = guild.get_role(ovr.get("id"))
                if not target:
                    target = role_map.get(ovr["name"])
            else:
                target = guild.get_member(ovr.get("id"))
                if not target:
                    target = discord.utils.get(guild.members, name=ovr["name"])
            
            if target:
                overwrites[target] = discord.PermissionOverwrite.from_pair(
                    discord.Permissions(ovr["allow"]),
                    discord.Permissions(ovr["deny"])
                )
        return overwrites

# =========================
# UTILITY FUNCTIONS
# =========================

class ImageUtil:
    """Image processing utilities"""
    
    @staticmethod
    def compress(data: bytes, max_size: tuple = (800, 800), quality: int = 85) -> bytes:
        img = Image.open(io.BytesIO(data))
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail(max_size)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        return buf.getvalue()

def load_json_file(filename: str, default: List) -> List:
    """Load JSON data from file with fallback"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {filename}: {e}")
        return default

def build_announcement_embed(position: str) -> discord.Embed:
    """Build header or footer announcement embed"""
    config = ANNOUNCEMENT_CONFIG.get(position, {})
    embed = discord.Embed(
        description=config.get("description", ""),
        color=discord.Color(config.get("color", 0xb1c3f9))
    )
    if config.get("image_url"):
        embed.set_image(url=config["image_url"])
    return embed

def build_embed_from_data(data: Dict) -> discord.Embed:
    """Build Discord embed from saved data"""
    color = discord.Color.blue()
    if data.get("color"):
        try:
            color = discord.Color(int(data["color"].replace("#", ""), 16))
        except:
            pass
    
    embed = discord.Embed(
        title=data.get("title"),
        description=data.get("description"),
        color=color
    )
    
    if data.get("image"):
        embed.set_image(url=data["image"])
    if data.get("footer"):
        embed.set_footer(text=data["footer"])
    
    if data.get("fields"):
        fields = data["fields"] if isinstance(data["fields"], list) else json.loads(data["fields"])
        for field in fields:
            embed.add_field(
                name=field.get("name", ""),
                value=field.get("value", ""),
                inline=field.get("inline", False)
            )
    
    return embed

def is_staff():
    """Permission check decorator for staff-only commands"""
    async def predicate(interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator:
            return True
        if STAFF_ROLE_ID and discord.utils.get(interaction.user.roles, id=STAFF_ROLE_ID):
            return True
        await interaction.response.send_message("⛔ Staff only.", ephemeral=True)
        return False
    return app_commands.check(predicate)

# =========================
# BOT SETUP
# =========================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class StarflightBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()

bot = StarflightBot()

@bot.event
async def on_ready():
    init_db()
    logger.info(f"🚀 Starflight Pilot online as {bot.user}")

# =========================
# MODAL CLASSES
# =========================

class EmbedBuilderModal(discord.ui.Modal, title="Create Embed"):
    embed_title = discord.ui.TextInput(label="Title", required=False)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph)
    color = discord.ui.TextInput(label="Color (hex)", required=False)
    image_url = discord.ui.TextInput(label="Image URL", required=False)
    footer = discord.ui.TextInput(label="Footer", required=False)

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    async def on_submit(self, interaction: discord.Interaction):
        data = {
            "title": self.embed_title.value,
            "description": self.description.value,
            "color": self.color.value,
            "image": self.image_url.value,
            "footer": self.footer.value,
            "fields": []
        }
        if EmbedManager.save(self.name, data):
            await interaction.response.send_message(f"✅ Embed **{self.name}** saved.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Failed to save embed.", ephemeral=True)

class PlushieModal(discord.ui.Modal, title="Register Plushie"):
    name = discord.ui.TextInput(label="Name")
    species = discord.ui.TextInput(label="Species")
    color = discord.ui.TextInput(label="Color", required=False)
    personality = discord.ui.TextInput(label="Personality", style=discord.TextStyle.paragraph)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph)

    def __init__(self, image_url: Optional[str]):
        super().__init__()
        self.image_url = image_url

    async def on_submit(self, interaction: discord.Interaction):
        image = None
        if self.image_url:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.image_url) as resp:
                    image = ImageUtil.compress(await resp.read())
        
        data = {
            "name": self.name.value,
            "species": self.species.value,
            "color": self.color.value or "N/A",
            "personality": self.personality.value,
            "description": self.description.value
        }
        
        if PlushieManager.create(interaction.user.id, data, image):
            await interaction.response.send_message("🧸 Plushie registered!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Failed to register plushie.", ephemeral=True)

class PlushieEditModal(discord.ui.Modal, title="Edit Plushie"):
    species = discord.ui.TextInput(label="Species", required=False)
    color = discord.ui.TextInput(label="Color", required=False)
    personality = discord.ui.TextInput(label="Personality", style=discord.TextStyle.paragraph, required=False)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, required=False)

    def __init__(self, user_id: int, name: str, image_url: Optional[str], current: Dict):
        super().__init__()
        self.user_id = user_id
        self.name = name
        self.image_url = image_url
        
        if current.get("species"):
            self.species.default = current["species"]
        if current.get("color"):
            self.color.default = current["color"]
        if current.get("personality"):
            self.personality.default = current["personality"]
        if current.get("description"):
            self.description.default = current["description"]

    async def on_submit(self, interaction: discord.Interaction):
        updates = {}
        if self.species.value:
            updates["species"] = self.species.value
        if self.color.value:
            updates["color"] = self.color.value
        if self.personality.value:
            updates["personality"] = self.personality.value
        if self.description.value:
            updates["description"] = self.description.value
        
        image = None
        if self.image_url:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.image_url) as resp:
                    image = ImageUtil.compress(await resp.read())
        
        if PlushieManager.update(self.user_id, self.name, updates, image):
            await interaction.response.send_message("✅ Plushie updated!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Update failed.", ephemeral=True)

# =========================
# EMBED COMMANDS
# =========================

@bot.tree.command(name="embed_create")
@is_staff()
async def embed_create(interaction: discord.Interaction, name: str):
    """Create a new embed template"""
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    await interaction.response.send_modal(EmbedBuilderModal(safe_name))

@bot.tree.command(name="embed_post")
@is_staff()
async def embed_post(interaction: discord.Interaction, name: str, channel: Optional[discord.TextChannel] = None):
    """Post a saved embed with header and footer"""
    embed_data = EmbedManager.get(name)
    if not embed_data:
        return await interaction.response.send_message("❌ Embed not found.", ephemeral=True)
    
    target = channel or interaction.channel
    await target.send(embed=build_announcement_embed("header"))
    await target.send(embed=build_embed_from_data(embed_data))
    await target.send(embed=build_announcement_embed("footer"))
    await interaction.response.send_message("✅ Posted with header and footer.", ephemeral=True)

@bot.tree.command(name="embed_list")
@is_staff()
async def embed_list(interaction: discord.Interaction):
    """List all saved embed templates"""
    embeds = EmbedManager.list_all()
    if not embeds:
        return await interaction.response.send_message("🔭 No embeds saved.", ephemeral=True)
    
    embed = discord.Embed(
        title="📋 Saved Embeds",
        description="\n".join(f"• {name}" for name in embeds),
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="embed_delete")
@is_staff()
async def embed_delete(interaction: discord.Interaction, name: str):
    """Delete an embed template"""
    if EmbedManager.delete(name):
        await interaction.response.send_message(f"✅ Deleted embed **{name}**.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Embed not found.", ephemeral=True)

# =========================
# SERVER BACKUP COMMANDS
# =========================

@bot.tree.command(name="backup_ship")
@is_staff()
async def backup_ship(interaction: discord.Interaction):
    """Create a backup and save it to the database"""
    await interaction.response.defer(ephemeral=True)
    data = await BackupManager.create_backup(interaction.guild)
    if BackupManager.save_to_db(interaction.guild.id, data):
        await interaction.followup.send("💾 Ship backed up to database.", ephemeral=True)
    else:
        await interaction.followup.send("❌ Backup failed.", ephemeral=True)

@bot.tree.command(name="restore_ship")
@is_staff()
async def restore_ship(interaction: discord.Interaction):
    """Restore the latest backup from the database"""
    await interaction.response.defer(ephemeral=True)
    data = BackupManager.load_from_db(interaction.guild.id)
    
    if not data:
        return await interaction.followup.send("⚠️ No ship backup found.", ephemeral=True)
    
    try:
        await BackupManager.restore(interaction.guild, data)
        await interaction.followup.send("🛠️ Restoration complete! Roles and channels recreated.", ephemeral=True)
    except Exception as e:
        logger.error(f"Restore error: {e}")
        await interaction.followup.send(f"❌ Restore failed: {e}", ephemeral=True)

@bot.tree.command(name="sync_tree")
@is_staff()
async def sync_tree(interaction: discord.Interaction):
    """Sync slash commands to Discord"""
    await interaction.response.defer(ephemeral=True)
    await bot.tree.sync()
    await interaction.followup.send("📡 Slash commands synced.", ephemeral=True)

# =========================
# PLUSHIE COMMANDS
# =========================

@bot.tree.command(name="plushie_scan")
async def plushie_scan(interaction: discord.Interaction, photo: Optional[discord.Attachment] = None):
    """Register a new plushie to your collection"""
    await interaction.response.send_modal(PlushieModal(photo.url if photo else None))

@bot.tree.command(name="plushie_edit")
async def plushie_edit(interaction: discord.Interaction, name: str, photo: Optional[discord.Attachment] = None):
    """Edit an existing plushie in your collection"""
    plushie = PlushieManager.get_one(interaction.user.id, name)
    if not plushie:
        return await interaction.response.send_message("❌ You don't have a plushie with that name.", ephemeral=True)
    await interaction.response.send_modal(PlushieEditModal(interaction.user.id, name, photo.url if photo else None, plushie))

@bot.tree.command(name="plushie_info")
async def plushie_info(interaction: discord.Interaction, owner: discord.Member, name: str):
    """View detailed information about a plushie"""
    plushie = PlushieManager.get_one(owner.id, name)
    if not plushie:
        return await interaction.response.send_message("❌ Not found.", ephemeral=True)

    embed = discord.Embed(
        title=plushie["name"],
        description=plushie["description"],
        color=discord.Color.pink()
    )
    embed.add_field(name="Species", value=plushie["species"])
    embed.add_field(name="Color", value=plushie["color"])
    embed.add_field(name="Personality", value=plushie["personality"], inline=False)
    embed.set_footer(text=f"Owner: {owner.display_name}")

    file = None
    if plushie["image_data"]:
        file = discord.File(io.BytesIO(plushie["image_data"]), "plushie.jpg")
        embed.set_image(url="attachment://plushie.jpg")

    await interaction.response.send_message(embed=embed, file=file)

@bot.tree.command(name="plushie_list")
async def plushie_list(interaction: discord.Interaction, owner: Optional[discord.Member] = None):
    """View a list of plushies in your or another user's collection"""
    target = owner or interaction.user
    plushies = PlushieManager.get_all(target.id)
    
    if not plushies:
        return await interaction.response.send_message(
            f"{'You have' if target == interaction.user else f'{target.display_name} has'} no registered plushies.",
            ephemeral=True
        )
    
    embed = discord.Embed(
        title=f"🧸 {target.display_name}'s Plushies",
        description="\n".join(f"• **{p['name']}** - {p['species']}" for p in plushies),
        color=discord.Color.pink()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="plushie_remove")
async def plushie_remove(interaction: discord.Interaction, name: str):
    """Remove a plushie from your collection"""
    if PlushieManager.delete(interaction.user.id, name):
        await interaction.response.send_message(f"✅ Removed **{name}**.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Plushie not found.", ephemeral=True)

# =========================
# MISSION & ENCOURAGEMENT
# =========================

@bot.tree.command(name="mission")
async def mission(interaction: discord.Interaction):
    """Get a random space mission to complete!"""
    missions = load_json_file(MISSIONS_FILE, ["🚀 Take a break and stretch for 30 seconds!"])
    mission_text = random.choice(missions)
    
    embed = discord.Embed(
        title="🎯 New Mission Assigned!",
        description=mission_text,
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Mission Control • {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="encourage")
async def encourage(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    """Send cosmic encouragement to yourself or another crew member!"""
    target = member or interaction.user
    encouragements = load_json_file(ENCOURAGEMENTS_FILE, ["is sending you positive vibes! ✨"])
    encouragement = random.choice(encouragements)
    
    embed = discord.Embed(
        title="✨ Cosmic Encouragement",
        description=f"**{interaction.user.display_name}** {encouragement}",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.set_footer(text=f"To: {target.display_name}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="space_fact")
async def space_fact(interaction: discord.Interaction):
    """Learn a random space fact!"""
    facts = load_json_file(SPACE_FACTS_FILE, ["Space is really big!"])
    fact_text = random.choice(facts)
    
    embed = discord.Embed(
        title="🔭 Space Fact",
        description=fact_text,
        color=discord.Color.purple()
    )
    embed.set_footer(text="Mission Control Educational Program")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="daily_mission")
@is_staff()
async def daily_mission(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    """Post a daily mission with header and footer (Staff only)"""
    target = channel or interaction.channel
    missions = load_json_file(MISSIONS_FILE, ["Complete a task today!"])
    mission_text = random.choice(missions)
    
    await target.send(embed=build_announcement_embed("header"))
    
    mission_embed = discord.Embed(
        title="🎯 Daily Mission",
        description=mission_text,
        color=discord.Color.blue()
    )
    mission_embed.set_footer(text=f"Posted by {interaction.user.display_name} • Complete this mission today!")
    await target.send(embed=mission_embed)
    
    await target.send(embed=build_announcement_embed("footer"))
    await interaction.response.send_message("✅ Daily mission posted!", ephemeral=True)

@bot.tree.command(name="encourage_post")
@is_staff()
async def encourage_post(interaction: discord.Interaction, member: discord.Member, channel: Optional[discord.TextChannel] = None):
    """Post an encouragement announcement with header and footer (Staff only)"""
    target = channel or interaction.channel
    encouragements = load_json_file(ENCOURAGEMENTS_FILE, ["is being appreciated! ✨"])
    encouragement = random.choice(encouragements)
    
    await target.send(embed=build_announcement_embed("header"))
    
    encourage_embed = discord.Embed(
        title="✨ Crew Encouragement",
        description=f"**Mission Control** {encouragement}",
        color=discord.Color.gold()
    )
    encourage_embed.set_thumbnail(url=member.display_avatar.url)
    encourage_embed.set_footer(text=f"To: {member.display_name}")
    await target.send(embed=encourage_embed)
    
    await target.send(embed=build_announcement_embed("footer"))
    await interaction.response.send_message("✅ Encouragement posted!", ephemeral=True)

# =========================
# FUN SPACE COMMANDS
# =========================

@bot.tree.command(name="launch")
async def launch(interaction: discord.Interaction):
    """Launch a rocket with a countdown!"""
    embed = discord.Embed(
        title="🚀 Rocket Launch Sequence",
        description="Preparing for liftoff...",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()
    
    for i in range(10, 0, -1):
        embed.description = f"**T-minus {i}...**"
        await message.edit(embed=embed)
        await asyncio.sleep(1)
    
    embed.description = "🚀💥 **LIFTOFF!**\n\nYou're heading to the stars!"
    embed.color = discord.Color.green()
    await message.edit(embed=embed)

@bot.tree.command(name="orbit")
async def orbit(interaction: discord.Interaction):
    """See who's currently orbiting the space station!"""
    members = [m for m in interaction.guild.members if not m.bot and m.status != discord.Status.offline]
    
    embed = discord.Embed(
        title="🛰️ Current Orbit Status",
        description=f"**{len(members)}** crew members are currently in orbit!",
        color=discord.Color.blue()
    )
    
    if len(members) <= 10:
        crew_list = "\n".join(f"• {m.display_name}" for m in members[:10])
        embed.add_field(name="Active Crew", value=crew_list, inline=False)
    
    embed.set_footer(text=f"Space Station Population • {interaction.guild.name}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="planet")
async def planet(interaction: discord.Interaction):
    """Discover a random planet!"""
    planets = [
        {"name": "Kepler-442b", "desc": "A super-Earth in the habitable zone!", "color": 0x4a9eff, "emoji": "🌍"},
        {"name": "HD 189733 b", "desc": "A scorching hot Jupiter with glass rain!", "color": 0x0047ab, "emoji": "🔵"},
        {"name": "TrES-2b", "desc": "The darkest known exoplanet - blacker than coal!", "color": 0x1a1a1a, "emoji": "⚫"},
        {"name": "WASP-12b", "desc": "Being devoured by its own star!", "color": 0xff4500, "emoji": "🔴"},
        {"name": "55 Cancri e", "desc": "A diamond planet worth 26.9 nonillion dollars!", "color": 0xe0e0e0, "emoji": "💎"},
        {"name": "PSR B1257+12 A", "desc": "Orbits a dead star - a pulsar!", "color": 0x800080, "emoji": "🟣"},
        {"name": "Gliese 1214 b", "desc": "A water world covered in oceans!", "color": 0x00bfff, "emoji": "🌊"},
        {"name": "KELT-9b", "desc": "Hotter than most stars at 4,300°C!", "color": 0xffa500, "emoji": "🔥"},
    ]
    
    planet = random.choice(planets)
    embed = discord.Embed(
        title=f"{planet['emoji']} Discovered: {planet['name']}",
        description=planet['desc'],
        color=discord.Color(planet['color'])
    )
    embed.set_footer(text=f"Discovered by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="spacewalk")
async def spacewalk(interaction: discord.Interaction):
    """Take a virtual spacewalk and see what you find!"""
    discoveries = [
        "You spotted a distant nebula glowing in purple and pink! 🌌",
        "A piece of space debris from an old satellite drifted past you! 🛰️",
        "You see Earth rotating peacefully below - it's beautiful! 🌍",
        "A meteor shower is happening in the distance! ☄️",
        "You found a piece of moon rock floating nearby! 🌙",
        "The International Space Station waves as it passes by! 👋",
        "You can see the Aurora Borealis dancing over the North Pole! 💚",
        "A communications satellite reflects sunlight like a star! ✨",
        "You witness a solar flare erupting from the sun! ☀️",
        "Jupiter and its great red spot are visible in the distance! 🪐",
    ]
    
    discovery = random.choice(discoveries)
    embed = discord.Embed(
        title="🧑‍🚀 Spacewalk Report",
        description=discovery,
        color=discord.Color.dark_blue()
    )
    embed.set_footer(text=f"Astronaut: {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="stardate")
async def stardate(interaction: discord.Interaction):
    """Get the current stardate!"""
    now = datetime.now(timezone.utc)
    stardate = (now.year - 2323) * 1000 + now.timetuple().tm_yday
    
    embed = discord.Embed(
        title="📅 Current Stardate",
        description=f"**Stardate {stardate}.{now.hour:02d}**\n\nEarth Date: {now.strftime('%B %d, %Y')}",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Starfleet Chronometer")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="crew_manifest")
async def crew_manifest(interaction: discord.Interaction):
    """View the current crew statistics"""
    guild = interaction.guild
    total = guild.member_count
    humans = len([m for m in guild.members if not m.bot])
    bots = len([m for m in guild.members if m.bot])
    online = len([m for m in guild.members if m.status != discord.Status.offline and not m.bot])
    
    embed = discord.Embed(title="📋 Crew Manifest", color=discord.Color.blue())
    embed.add_field(name="👥 Total Crew", value=f"{total}", inline=True)
    embed.add_field(name="🧑‍🚀 Humans", value=f"{humans}", inline=True)
    embed.add_field(name="🤖 Bots", value=f"{bots}", inline=True)
    embed.add_field(name="🟢 Online", value=f"{online}", inline=True)
    embed.add_field(name="📡 Active Rate", value=f"{(online/humans*100):.1f}%", inline=True)
    embed.set_footer(text=f"Space Station: {guild.name}")
    await interaction.response.send_message(embed=embed)

# =========================
# ADDITIONAL INTERACTIVE COMMANDS
# =========================

@bot.tree.command(name="roll")
async def roll(interaction: discord.Interaction, sides: int = 6):
    """Roll a dice"""
    if sides < 2 or sides > 100:
        return await interaction.response.send_message("❌ Dice must have 2-100 sides.", ephemeral=True)
    
    result = random.randint(1, sides)
    embed = discord.Embed(
        title="🎲 Dice Roll",
        description=f"You rolled a **{result}** (d{sides})",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="flip")
async def flip(interaction: discord.Interaction):
    """Flip a coin"""
    result = random.choice(["Heads", "Tails"])
    embed = discord.Embed(
        title="🪙 Coin Flip",
        description=f"Result: **{result}**",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="poll")
async def poll(interaction: discord.Interaction, question: str, option1: str, option2: str, 
               option3: Optional[str] = None, option4: Optional[str] = None):
    """Create a poll with up to 4 options"""
    options = [option1, option2]
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    
    if option3:
        options.append(option3)
    if option4:
        options.append(option4)
    
    description = "\n".join(f"{emojis[i]} {opt}" for i, opt in enumerate(options))
    embed = discord.Embed(
        title=f"📊 {question}",
        description=description,
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Poll by {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()
    
    for i in range(len(options)):
        await message.add_reaction(emojis[i])

@bot.tree.command(name="avatar")
async def avatar(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    """Get a member's avatar"""
    target = member or interaction.user
    embed = discord.Embed(
        title=f"{target.display_name}'s Avatar",
        color=discord.Color.blue()
    )
    embed.set_image(url=target.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo")
async def serverinfo(interaction: discord.Interaction):
    """Display server information"""
    guild = interaction.guild
    embed = discord.Embed(title=f"📋 {guild.name}", color=discord.Color.blue())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
    embed.add_field(name="Created", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)
    embed.add_field(name="Members", value=str(guild.member_count), inline=True)
    embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
    embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
    embed.add_field(name="Boosts", value=str(guild.premium_subscription_count), inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="userinfo")
async def userinfo(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    """Display user information"""
    target = member or interaction.user
    embed = discord.Embed(title=f"👤 {target.display_name}", color=target.color)
    embed.set_thumbnail(url=target.display_avatar.url)
    
    embed.add_field(name="Username", value=str(target), inline=True)
    embed.add_field(name="ID", value=str(target.id), inline=True)
    
    if target.joined_at:
        embed.add_field(name="Joined Server", value=f"<t:{int(target.joined_at.timestamp())}:R>", inline=False)
    embed.add_field(name="Account Created", value=f"<t:{int(target.created_at.timestamp())}:R>", inline=False)
    
    roles = [role.mention for role in target.roles if role.name != "@everyone"]
    if roles:
        embed.add_field(name=f"Roles [{len(roles)}]", value=" ".join(roles), inline=False)
    
    await interaction.response.send_message(embed=embed)

# =========================
# ERROR HANDLING
# =========================

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Global error handler for slash commands"""
    if isinstance(error, app_commands.CheckFailure):
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
    elif isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(f"⏳ This command is on cooldown. Try again in {error.retry_after:.1f}s.", ephemeral=True)
    else:
        logger.error(f"Command error: {error}", exc_info=True)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ An error occurred while executing this command.", ephemeral=True)

# =========================
# RUN BOT
# =========================

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN environment variable not set")
    bot.run(TOKEN)