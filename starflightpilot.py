# =========================
# STARFLIGHT PILOT BOT
# =========================

import discord
from discord.ext import commands
from discord import app_commands

import os
import json
import logging
import random
import io
import re

from typing import Optional, Dict, List
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from PIL import Image
import aiohttp

# =========================
# ENV / CONFIG
# =========================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

BACKUP_FILE = "ship_backup.json"
MISSIONS_FILE = "missions.json"
ENCOURAGEMENTS_FILE = "encouragements.json"

STAFF_ROLE_ID = 1454538884682612940

# Header and Footer for all posts
HEADER_EMBED = {
    "color": 2635882,
    "description": "🎛️ **Announcement**",
    "image": "https://64.media.tumblr.com/fb4527b4d5ba87d89b66a9c7ce471836/01cb3d1ba106fa8c-2e/s1280x1920/e393f5a5a2d9275d944befbe0c0a14f051176874.pnj"
}

FOOTER_EMBED = {
    "color": 16775108,
    "description": "🚀 **pls invite ppl to join our discord server and help us grow!**\n\n[Click here](https://discord.gg/4QzQYeuApB) to join!",
    "image": "https://64.media.tumblr.com/b1087d6d3803689dd69ed77055e45141/01cb3d1ba106fa8c-7a/s1280x1920/b8342d92c350abeee78d7c8b0636625679dfc8ae.pnj"
}

# Note: To change header/footer, only modify the image URLs above, keep the text as-is

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Starflight")

# =========================
# DATABASE
# =========================

class DatabaseManager:
    
    @staticmethod
    def conn():
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL not set")
        return psycopg2.connect(DATABASE_URL)

    @staticmethod
    def init_db():
        with DatabaseManager.conn() as conn:
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
                    registered_date TEXT,
                    image BYTEA
                )
                """)
                cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS plushie_unique_name_per_user
                ON plushies (user_id, LOWER(name));
                """)
                
                # Embeds table
                cur.execute("""
                CREATE TABLE IF NOT EXISTS embeds (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    title TEXT,
                    description TEXT,
                    color TEXT,
                    image_url TEXT,
                    footer TEXT,
                    fields JSONB DEFAULT '[]'::jsonb,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                # Inside DatabaseManager.init_db()
                cur.execute("""
                CREATE TABLE IF NOT EXISTS server_backups (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    backup_data JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                
                conn.commit()


class PlushieManager:
    @staticmethod
    def add(user_id: int, data: Dict, image: Optional[bytes]) -> bool:
        try:
            with DatabaseManager.conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO plushies
                        (user_id, name, species, color, personality, description, registered_date, image)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        user_id,
                        data["name"],
                        data["species"],
                        data["color"],
                        data["personality"],
                        data["description"],
                        data["registered_date"],
                        psycopg2.Binary(image) if image else None
                    ))
                    conn.commit()
            return True
        except Exception as e:
            logger.error(e)
            return False

    @staticmethod
    def update(user_id: int, name: str, data: Dict, image: Optional[bytes] = None) -> bool:
        try:
            with DatabaseManager.conn() as conn:
                with conn.cursor() as cur:
                    # Build dynamic update query based on provided fields
                    updates = []
                    params = []
                    
                    if "species" in data:
                        updates.append("species = %s")
                        params.append(data["species"])
                    if "color" in data:
                        updates.append("color = %s")
                        params.append(data["color"])
                    if "personality" in data:
                        updates.append("personality = %s")
                        params.append(data["personality"])
                    if "description" in data:
                        updates.append("description = %s")
                        params.append(data["description"])
                    if image is not None:
                        updates.append("image = %s")
                        params.append(psycopg2.Binary(image))
                    
                    if not updates:
                        return False
                    
                    params.extend([user_id, name])
                    query = f"UPDATE plushies SET {', '.join(updates)} WHERE user_id = %s AND LOWER(name) = LOWER(%s)"
                    
                    cur.execute(query, params)
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(e)
            return False

    @staticmethod
    def list_for_user(user_id: int) -> List[Dict]:
        with DatabaseManager.conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT name, species
                    FROM plushies
                    WHERE user_id = %s
                    ORDER BY name
                """, (user_id,))
                return cur.fetchall()

    @staticmethod
    def get(user_id: int, name: str) -> Optional[Dict]:
        with DatabaseManager.conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT *
                    FROM plushies
                    WHERE user_id = %s AND LOWER(name) = LOWER(%s)
                """, (user_id, name))
                return cur.fetchone()

    @staticmethod
    def remove(user_id: int, name: str) -> bool:
        with DatabaseManager.conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM plushies
                    WHERE user_id = %s AND LOWER(name) = LOWER(%s)
                """, (user_id, name))
                return cur.rowcount > 0


class EmbedManager:
    @staticmethod
    def save(name: str, data: Dict) -> bool:
        try:
            with DatabaseManager.conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO embeds (name, title, description, color, image_url, footer, fields)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (name) 
                        DO UPDATE SET 
                            title = EXCLUDED.title,
                            description = EXCLUDED.description,
                            color = EXCLUDED.color,
                            image_url = EXCLUDED.image_url,
                            footer = EXCLUDED.footer,
                            fields = EXCLUDED.fields,
                            updated_at = CURRENT_TIMESTAMP
                    """, (
                        name,
                        data.get("title"),
                        data.get("description"),
                        data.get("color"),
                        data.get("image"),
                        data.get("footer"),
                        json.dumps(data.get("fields", []))
                    ))
                    conn.commit()
            return True
        except Exception as e:
            logger.error(e)
            return False

    @staticmethod
    def get(name: str) -> Optional[Dict]:
        with DatabaseManager.conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT name, title, description, color, image_url, footer, fields
                    FROM embeds
                    WHERE name = %s
                """, (name,))
                result = cur.fetchone()
                if result:
                    result["image"] = result.pop("image_url")
                return result

    @staticmethod
    def list_all() -> List[str]:
        with DatabaseManager.conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT name FROM embeds ORDER BY name")
                return [row[0] for row in cur.fetchall()]

    @staticmethod
    def delete(name: str) -> bool:
        with DatabaseManager.conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM embeds WHERE name = %s", (name,))
                return cur.rowcount > 0

# =========================
# IMAGE PROCESSING
# =========================

class ImageProcessor:
    @staticmethod
    def compress(data: bytes) -> bytes:
        img = Image.open(io.BytesIO(data))
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail((800, 800))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        return buf.getvalue()

# =========================
# EMBED HELPERS
# =========================

def create_header_embed() -> discord.Embed:
    """Create the standard header embed for all posts"""
    embed = discord.Embed(
        description=HEADER_EMBED["description"],
        color=discord.Color(HEADER_EMBED["color"])
    )
    embed.set_image(url=HEADER_EMBED["image"])
    return embed

def create_footer_embed() -> discord.Embed:
    """Create the standard footer embed for all posts"""
    embed = discord.Embed(
        description=FOOTER_EMBED["description"],
        color=discord.Color(FOOTER_EMBED["color"])
    )
    embed.set_image(url=FOOTER_EMBED["image"])
    return embed

def create_embed_from_data(data: Dict) -> discord.Embed:
    """Create a Discord embed from stored data"""
    color = discord.Color.blue()
    if data.get("color"):
        try:
            color = discord.Color(int(data["color"].replace("#", ""), 16))
        except:
            pass

    embed = discord.Embed(
        title=data.get("title") or None,
        description=data.get("description") or None,
        color=color
    )

    if data.get("image"):
        embed.set_image(url=data["image"])
    if data.get("footer"):
        embed.set_footer(text=data["footer"])
    
    # Add fields if they exist
    if data.get("fields"):
        fields = data["fields"] if isinstance(data["fields"], list) else json.loads(data["fields"])
        for field in fields:
            embed.add_field(
                name=field.get("name", ""),
                value=field.get("value", ""),
                inline=field.get("inline", False)
            )

    return embed

# =========================
# BACKUP / SHIP SYSTEM
# =========================

class BackupManager:
    @staticmethod
    async def create_backup(guild: discord.Guild) -> Dict:
        data = {"roles": [], "categories": []}

        for role in reversed(guild.roles):
            if role.is_default():
                continue
            data["roles"].append({
                "name": role.name,
                "color": role.color.value,
                "permissions": role.permissions.value,
                "hoist": role.hoist
            })

        for cat in guild.categories:
            cat_data = {
                "name": cat.name,
                "overwrites": BackupManager.serialize_overwrites(cat.overwrites),
                "channels": []
            }

            for ch in cat.channels:
                cat_data["channels"].append({
                    "name": ch.name,
                    "type": str(ch.type),
                    "overwrites": BackupManager.serialize_overwrites(ch.overwrites)
                })

            data["categories"].append(cat_data)

        return data
@staticmethod
    def save_to_db(guild_id: int, data: Dict):
        """Saves backup to PostgreSQL instead of a file"""
        try:
            with DatabaseManager.conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO server_backups (guild_id, backup_data)
                        VALUES (%s, %s)
                    """, (guild_id, json.dumps(data)))
                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Backup Save Error: {e}")
            return False
@staticmethod
async def restore_from_data(guild: discord.Guild, data: Dict):
        # 1. Restore Roles (Skip @everyone and managed/bot roles)
        role_map = {} # Maps old names to new role objects
        for r_data in data.get("roles", []):
            try:
                new_role = await guild.create_role(
                    name=r_data["name"],
                    color=discord.Color(r_data["color"]),
                    permissions=discord.Permissions(r_data["permissions"]),
                    hoist=r_data["hoist"]
                )
                role_map[r_data["name"]] = new_role
            except Exception as e:
                logger.error(f"Failed to restore role {r_data['name']}: {e}")

        # 2. Restore Categories and Channels
        for cat_data in data.get("categories", []):
            try:
                # Map overwrites to the new role objects we just created
                overwrites = BackupManager.deserialize_target_overwrites(guild, cat_data["overwrites"], role_map)
                new_cat = await guild.create_category(name=cat_data["name"], overwrites=overwrites)

                for ch_data in cat_data.get("channels", []):
                    ch_overwrites = BackupManager.deserialize_target_overwrites(guild, ch_data["overwrites"], role_map)
                    if ch_data["type"] == "text":
                        await new_cat.create_text_channel(name=ch_data["name"], overwrites=ch_overwrites)
                    elif ch_data["type"] == "voice":
                        await new_cat.create_voice_channel(name=ch_data["name"], overwrites=ch_overwrites)
            except Exception as e:
                logger.error(f"Failed to restore category/channel: {e}")

    @staticmethod
    def serialize_overwrites(overwrites):
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
    def deserialize_target_overwrites(guild, overwrites_data, role_map):
        """Helper to convert stored permission data back into Discord objects"""
        overwrites = {}
        for ovr in overwrites_data:
            target = None
            if ovr["is_role"]:
                target = role_map.get(ovr["name"])
            else:
                target = discord.utils.get(guild.members, name=ovr["name"])
            
            if target:
                overwrites[target] = discord.PermissionOverwrite.from_pair(
                    discord.Permissions(ovr["allow"]),
                    discord.Permissions(ovr["deny"])
                )
        return overwrites

    @staticmethod
    def load_from_db(guild_id: int):
        """Fetches the latest backup from PostgreSQL"""
        with DatabaseManager.conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT backup_data FROM server_backups 
                    WHERE guild_id = %s 
                    ORDER BY created_at DESC LIMIT 1
                """, (guild_id,))
                result = cur.fetchone()
                return result["backup_data"] if result else None
            
# =========================
# BOT
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
    DatabaseManager.init_db()
    logger.info(f"🚀 Online as {bot.user}")

# =========================
# PERMISSIONS
# =========================

def staff_only():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator:
            return True
        if discord.utils.get(interaction.user.roles, id=STAFF_ROLE_ID):
            return True
        await interaction.response.send_message("❌ Staff only.", ephemeral=True)
        return False
    return app_commands.check(predicate)

# =========================
# EMBED BUILDER
# =========================

class EmbedModal(discord.ui.Modal, title="Create Embed"):
    title_text = discord.ui.TextInput(label="Title", required=False)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph)
    color = discord.ui.TextInput(label="Color (hex)", required=False)
    image = discord.ui.TextInput(label="Image URL", required=False)
    footer = discord.ui.TextInput(label="Footer", required=False)

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    async def on_submit(self, interaction: discord.Interaction):
        data = {
            "title": self.title_text.value,
            "description": self.description.value,
            "color": self.color.value,
            "image": self.image.value,
            "footer": self.footer.value,
            "fields": []
        }

        if EmbedManager.save(self.name, data):
            await interaction.response.send_message(
                f"✅ Embed **{self.name}** saved to database.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Failed to save embed.",
                ephemeral=True
            )

@bot.tree.command(name="embed_create")
@staff_only()
async def embed_create(interaction: discord.Interaction, name: str):
    """Create a new embed template"""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    await interaction.response.send_modal(EmbedModal(safe))

@bot.tree.command(name="embed_post")
@staff_only()
async def embed_post(interaction: discord.Interaction, name: str, channel: Optional[discord.TextChannel] = None):
    """Post a saved embed with header and footer"""
    d = EmbedManager.get(name)
    if not d:
        return await interaction.response.send_message("❌ Embed not found.", ephemeral=True)

    target_channel = channel or interaction.channel
    
    # Send header
    await target_channel.send(embed=create_header_embed())
    
    # Send main embed
    await target_channel.send(embed=create_embed_from_data(d))
    
    # Send footer
    await target_channel.send(embed=create_footer_embed())
    
    await interaction.response.send_message("✅ Posted with header and footer.", ephemeral=True)

@bot.tree.command(name="embed_list")
@staff_only()
async def embed_list(interaction: discord.Interaction):
    """List all saved embed templates"""
    embeds = EmbedManager.list_all()
    if not embeds:
        return await interaction.response.send_message("📭 No embeds saved.", ephemeral=True)
    
    embed = discord.Embed(
        title="📋 Saved Embeds",
        description="\n".join(f"• {name}" for name in embeds),
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="embed_delete")
@staff_only()
async def embed_delete(interaction: discord.Interaction, name: str):
    """Delete an embed template"""
    if EmbedManager.delete(name):
        await interaction.response.send_message(f"✅ Deleted embed **{name}**.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Embed not found.", ephemeral=True)

# =========================
# SHIP COMMANDS
# =========================

@bot.tree.command(name="backup_ship")
@staff_only()
async def backup_ship(interaction: discord.Interaction):
    """Create a backup and save it to the Railway DB"""
    await interaction.response.defer(ephemeral=True) # Give it time to process
    
    data = await BackupManager.create_backup(interaction.guild)
    if BackupManager.save_to_db(interaction.guild.id, data):
        await interaction.followup.send("💾 Ship backed up to Railway database.", ephemeral=False)
    else:
        await interaction.followup.send("❌ Failed to save backup to database.", ephemeral=False)

@bot.tree.command(name="restore_ship")
@staff_only()
async def restore_ship(interaction: discord.Interaction):
    """Restore the latest backup from the Railway DB"""
    # Defer immediately to prevent timeout during API calls
    await interaction.response.defer(ephemeral=True)

    data = BackupManager.load_from_db(interaction.guild.id)
    
    if not data:
        return await interaction.followup.send("⚠️ No ship backup found in database.", ephemeral=True)

    try:
        await BackupManager.restore_from_data(interaction.guild, data)
        await interaction.followup.send("🛠️ Restoration complete! Roles and channels have been recreated.", ephemeral=True)
    except Exception as e:
        logger.error(f"Restore Error: {e}")
        await interaction.followup.send(f"❌ An error occurred during restoration: {e}", ephemeral=True)

@bot.tree.command(name="sync_tree")
@staff_only()
async def sync_tree(interaction: discord.Interaction):
    """Sync slash commands to Discord"""
    # 1. Defer the response immediately to prevent timeout
    await interaction.response.defer(ephemeral=True)
    
    # 2. Perform the slow operation
    await bot.tree.sync()
    
    # 3. Use followup.send instead of response.send_message
    await interaction.followup.send("📡 Slash commands synced.", ephemeral=True)

# =========================
# PLUSHIE COMMANDS
# =========================

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
            async with aiohttp.ClientSession() as s:
                async with s.get(self.image_url) as r:
                    image = ImageProcessor.compress(await r.read())

        PlushieManager.add(
            interaction.user.id,
            {
                "name": self.name.value,
                "species": self.species.value,
                "color": self.color.value or "N/A",
                "personality": self.personality.value,
                "description": self.description.value,
                "registered_date": datetime.now(timezone.utc).isoformat()
            },
            image
        )

        await interaction.response.send_message("🧸 Plushie registered!", ephemeral=True)


class PlushieEditModal(discord.ui.Modal, title="Edit Plushie"):
    species = discord.ui.TextInput(label="Species", required=False)
    color = discord.ui.TextInput(label="Color", required=False)
    personality = discord.ui.TextInput(label="Personality", style=discord.TextStyle.paragraph, required=False)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, required=False)

    def __init__(self, user_id: int, name: str, image_url: Optional[str], current_data: Dict):
        super().__init__()
        self.user_id = user_id
        self.name = name
        self.image_url = image_url
        
        # Pre-fill with current values
        if current_data.get("species"):
            self.species.default = current_data["species"]
        if current_data.get("color"):
            self.color.default = current_data["color"]
        if current_data.get("personality"):
            self.personality.default = current_data["personality"]
        if current_data.get("description"):
            self.description.default = current_data["description"]

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
            async with aiohttp.ClientSession() as s:
                async with s.get(self.image_url) as r:
                    image = ImageProcessor.compress(await r.read())
        
        if PlushieManager.update(self.user_id, self.name, updates, image):
            await interaction.response.send_message("✅ Plushie updated!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Failed to update plushie.", ephemeral=True)


@bot.tree.command(name="plushie_scan")
async def plushie_scan(interaction: discord.Interaction, photo: Optional[discord.Attachment] = None):
    """Register a new plushie to your collection"""
    await interaction.response.send_modal(PlushieModal(photo.url if photo else None))

@bot.tree.command(name="plushie_edit")
async def plushie_edit(interaction: discord.Interaction, name: str, photo: Optional[discord.Attachment] = None):
    """Edit an existing plushie in your collection"""
    p = PlushieManager.get(interaction.user.id, name)
    if not p:
        return await interaction.response.send_message("❌ You don't have a plushie with that name.", ephemeral=True)
    
    await interaction.response.send_modal(
        PlushieEditModal(interaction.user.id, name, photo.url if photo else None, p)
    )

@bot.tree.command(name="plushie_info")
async def plushie_info(interaction: discord.Interaction, owner: discord.Member, name: str):
    """View detailed information about a plushie"""
    p = PlushieManager.get(owner.id, name)
    if not p:
        return await interaction.response.send_message("❌ Not found.", ephemeral=True)

    embed = discord.Embed(
        title=p["name"],
        description=p["description"],
        color=discord.Color.pink()
    )
    embed.add_field(name="Species", value=p["species"])
    embed.add_field(name="Color", value=p["color"])
    embed.add_field(name="Personality", value=p["personality"], inline=False)
    embed.set_footer(text=f"Owner: {owner.display_name}")

    file = None
    if p["image"]:
        file = discord.File(io.BytesIO(p["image"]), "plushie.jpg")
        embed.set_image(url="attachment://plushie.jpg")

    await interaction.response.send_message(embed=embed, file=file)

@bot.tree.command(name="plushie_list")
async def plushie_list(interaction: discord.Interaction, owner: Optional[discord.Member] = None):
    """View a list of plushies in your or another user's collection"""
    target = owner or interaction.user
    plushies = PlushieManager.list_for_user(target.id)
    
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
    if PlushieManager.remove(interaction.user.id, name):
        await interaction.response.send_message(f"✅ Removed **{name}**.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Plushie not found.", ephemeral=True)

# =========================
# RUN
# =========================

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN missing")
    bot.run(TOKEN)