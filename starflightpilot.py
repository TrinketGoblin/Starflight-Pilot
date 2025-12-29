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

EMBEDS_FOLDER = "saved_embeds"
BACKUP_FILE = "ship_backup.json"
MISSIONS_FILE = "missions.json"
ENCOURAGEMENTS_FILE = "encouragements.json"

STAFF_ROLE_ID = 1454538884682612940

os.makedirs(EMBEDS_FOLDER, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Starflight")

# =========================
# DATABASE
# =========================

class PlushieManager:
    @staticmethod
    def conn():
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL not set")
        return psycopg2.connect(DATABASE_URL)

    @staticmethod
    def init_db():
        with PlushieManager.conn() as conn:
            with conn.cursor() as cur:
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
                # Create a unique index on user_id + lower(name)
                cur.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS plushie_unique_name_per_user
                ON plushies (user_id, LOWER(name));
                """)
                conn.commit()


    @staticmethod
    def add(user_id: int, data: Dict, image: Optional[bytes]) -> bool:
        try:
            with PlushieManager.conn() as conn:
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
    def list_for_user(user_id: int) -> List[Dict]:
        with PlushieManager.conn() as conn:
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
        with PlushieManager.conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT *
                    FROM plushies
                    WHERE user_id = %s AND LOWER(name) = LOWER(%s)
                """, (user_id, name))
                return cur.fetchone()

    @staticmethod
    def remove(user_id: int, name: str) -> bool:
        with PlushieManager.conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM plushies
                    WHERE user_id = %s AND LOWER(name) = LOWER(%s)
                """, (user_id, name))
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
    def save(data: Dict):
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    @staticmethod
    def load():
        if not os.path.exists(BACKUP_FILE):
            return None
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

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
    PlushieManager.init_db()
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

        with open(os.path.join(EMBEDS_FOLDER, f"{self.name}.json"), "w") as f:
            json.dump(data, f, indent=4)

        await interaction.response.send_message(
            f"✅ Embed **{self.name}** saved.",
            ephemeral=True
        )

@bot.tree.command(name="embed_create")
@staff_only()
async def embed_create(interaction: discord.Interaction, name: str):
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    await interaction.response.send_modal(EmbedModal(safe))

@bot.tree.command(name="embed_post")
@staff_only()
async def embed_post(interaction: discord.Interaction, name: str, channel: Optional[discord.TextChannel] = None):
    path = os.path.join(EMBEDS_FOLDER, f"{name}.json")
    if not os.path.exists(path):
        return await interaction.response.send_message("❌ Embed not found.", ephemeral=True)

    with open(path) as f:
        d = json.load(f)

    color = discord.Color.blue()
    if d.get("color"):
        try:
            color = discord.Color(int(d["color"].replace("#", ""), 16))
        except:
            pass

    embed = discord.Embed(
        title=d.get("title") or None,
        description=d.get("description") or None,
        color=color
    )

    if d.get("image"):
        embed.set_image(url=d["image"])
    if d.get("footer"):
        embed.set_footer(text=d["footer"])

    await (channel or interaction.channel).send(embed=embed)
    await interaction.response.send_message("✅ Posted.", ephemeral=True)

# =========================
# SHIP COMMANDS
# =========================

@bot.tree.command(name="backup_ship")
@staff_only()
async def backup_ship(interaction: discord.Interaction):
    data = await BackupManager.create_backup(interaction.guild)
    BackupManager.save(data)
    await interaction.response.send_message("💾 Ship backed up.", ephemeral=True)

@bot.tree.command(name="sync_tree")
@commands.has_permissions(administrator=True)
async def sync_tree(ctx):
    await bot.tree.sync()
    await ctx.send("📡 Slash commands synced.")

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

@bot.tree.command(name="plushie_scan")
async def plushie_scan(interaction: discord.Interaction, photo: Optional[discord.Attachment] = None):
    await interaction.response.send_modal(PlushieModal(photo.url if photo else None))

@bot.tree.command(name="plushie_info")
async def plushie_info(interaction: discord.Interaction, owner: discord.Member, name: str):
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

    file = None
    if p["image"]:
        file = discord.File(io.BytesIO(p["image"]), "plushie.jpg")
        embed.set_image(url="attachment://plushie.jpg")

    await interaction.response.send_message(embed=embed, file=file)

# =========================
# RUN
# =========================

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN missing")
    bot.run(TOKEN)
