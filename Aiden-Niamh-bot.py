import discord
from discord.ext import commands
from discord import app_commands

import os
import json
import logging
from typing import Optional, Dict

# Ensure psycopg2 is imported correctly
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    raise ImportError("The 'psycopg2' library is missing. Install it using 'pip install psycopg2-binary'.")

from dotenv import load_dotenv

# =========================
# ENV / CONFIG
# =========================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
STAFF_ROLE_ID = 1454538884682612940 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SyncBot")

# =========================
# DATABASE
# =========================

class DatabaseManager:
    @staticmethod
    def conn():
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL not set in .env file.")
        return psycopg2.connect(DATABASE_URL)

    @staticmethod
    def init_db():
        with DatabaseManager.conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS server_backups (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    backup_data JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """)
                conn.commit()

# =========================
# BACKUP / RESTORE LOGIC
# =========================

class BackupManager:
    @staticmethod
    async def create_backup(guild: discord.Guild) -> Dict:
        data = {"roles": [], "categories": []}

        # Backup Roles
        for role in reversed(guild.roles):
            if role.is_default() or role.managed:
                continue
            data["roles"].append({
                "role_id": role.id,
                "name": role.name,
                "color": role.color.value,
                "permissions": role.permissions.value,
                "hoist": role.hoist
            })

        # Backup Categories and Channels
        for cat in guild.categories:
            cat_data = {
                "category_id": cat.id,
                "name": cat.name,
                "overwrites": BackupManager.serialize_overwrites(cat.overwrites),
                "channels": []
            }

            for ch in cat.channels:
                chan_info = {
                    "channel_id": ch.id,
                    "name": ch.name,
                    "type": str(ch.type),
                    "overwrites": BackupManager.serialize_overwrites(ch.overwrites)
                }
                
                if isinstance(ch, discord.TextChannel):
                    chan_info["nsfw"] = ch.is_nsfw()
                
                cat_data["channels"].append(chan_info)
                
            data["categories"].append(cat_data)
        return data

    @staticmethod
    def save_to_db(guild_id: int, data: Dict):
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
        role_map = {} 
        for r_data in data.get("roles", []):
            try:
                existing_role = guild.get_role(r_data["role_id"]) or discord.utils.get(guild.roles, name=r_data["name"])
                if not existing_role:
                    existing_role = await guild.create_role(
                        name=r_data["name"],
                        color=discord.Color(r_data["color"]),
                        permissions=discord.Permissions(r_data["permissions"]),
                        hoist=r_data["hoist"]
                    )
                role_map[r_data["name"]] = existing_role
            except Exception as e:
                logger.error(f"Failed to restore role {r_data['name']}: {e}")

        for cat_data in data.get("categories", []):
            try:
                overwrites = BackupManager.deserialize_target_overwrites(guild, cat_data["overwrites"], role_map)
                new_cat = guild.get_channel(cat_data["category_id"]) or discord.utils.get(guild.categories, name=cat_data["name"])
                
                if not new_cat:
                    new_cat = await guild.create_category(name=cat_data["name"], overwrites=overwrites)

                for ch_data in cat_data.get("channels", []):
                    ch_overwrites = BackupManager.deserialize_target_overwrites(guild, ch_data["overwrites"], role_map)
                    existing_chan = guild.get_channel(ch_data["channel_id"]) or discord.utils.get(new_cat.channels, name=ch_data["name"])
                    
                    if not existing_chan:
                        if ch_data["type"] == "text":
                            await new_cat.create_text_channel(
                                name=ch_data["name"], 
                                overwrites=ch_overwrites,
                                nsfw=ch_data.get("nsfw", False)
                            )
                        elif ch_data["type"] == "voice":
                            await new_cat.create_voice_channel(
                                name=ch_data["name"], 
                                overwrites=ch_overwrites
                            )
            except Exception as e:
                logger.error(f"Failed to restore category/channel: {e}")

    @staticmethod
    def serialize_overwrites(overwrites):
        result = []
        for target, ovr in overwrites.items():
            allow, deny = ovr.pair()
            result.append({
                "target_id": target.id,
                "name": target.name,
                "is_role": isinstance(target, discord.Role),
                "allow": allow.value,
                "deny": deny.value
            })
        return result

    @staticmethod
    def deserialize_target_overwrites(guild, overwrites_data, role_map):
        overwrites = {}
        for ovr in overwrites_data:
            target = None
            if ovr["is_role"]:
                target = role_map.get(ovr["name"]) or guild.get_role(ovr["target_id"])
            else:
                target = guild.get_member(ovr["target_id"]) or discord.utils.get(guild.members, name=ovr["name"])
            
            if target:
                overwrites[target] = discord.PermissionOverwrite.from_pair(
                    discord.Permissions(ovr["allow"]),
                    discord.Permissions(ovr["deny"])
                )
        return overwrites

    @staticmethod
    def load_from_db(guild_id: int):
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
# BOT SETUP
# =========================

# FIXED: Added Message Content Intent
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True 

class SyncBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()

bot = SyncBot()

@bot.event
async def on_ready():
    try:
        DatabaseManager.init_db()
        logger.info(f"🚀 Sync Bot Online as {bot.user}")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

def staff_only():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator:
            return True
        if any(role.id == STAFF_ROLE_ID for role in interaction.user.roles):
            return True
        await interaction.response.send_message("❌ Staff only.", ephemeral=True)
        return False
    return app_commands.check(predicate)

# =========================
# COMMANDS
# =========================

@bot.tree.command(name="backup_tavern")
@staff_only()
async def backup_tavern(interaction: discord.Interaction):
    """Saves the current server layout (IDs & NSFW status)"""
    await interaction.response.defer(ephemeral=True)
    data = await BackupManager.create_backup(interaction.guild)
    if BackupManager.save_to_db(interaction.guild.id, data):
        await interaction.followup.send("💾 Server layout backed up (tracked by IDs).", ephemeral=True)
    else:
        await interaction.followup.send("❌ Failed to save backup.", ephemeral=True)

@bot.tree.command(name="restore_tavern")
@staff_only()
async def restore_tavern(interaction: discord.Interaction):
    """Recreates the server layout using IDs first, then Names"""
    await interaction.response.defer(ephemeral=True)
    data = BackupManager.load_from_db(interaction.guild.id)
    if not data:
        return await interaction.followup.send("⚠️ No backup found.", ephemeral=True)
    try:
        await BackupManager.restore_from_data(interaction.guild, data)
        await interaction.followup.send("🛠️ Restoration complete!", ephemeral=True)
    except Exception as e:
        logger.error(f"Restore Error: {e}")
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

@bot.tree.command(name="sync_tree")
@staff_only()
async def sync_tree(interaction: discord.Interaction):
    """Sync slash commands"""
    await interaction.response.defer(ephemeral=True)
    await bot.tree.sync()
    await interaction.followup.send("📡 Commands synced.", ephemeral=True)

if __name__ == "__main__":
    bot.run(TOKEN)