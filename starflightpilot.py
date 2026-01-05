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
from collections import deque
import tempfile

FFMPEG_OPTIONS = {
    "before_options": "-nostdin -loglevel panic",
    "options": "-vn"
}

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

# Image directory for astronaut clipart
IMAGES_DIR = "astronauts"

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
# IMAGE HELPER
# =========================

def get_astronaut_image(filename: str) -> Optional[discord.File]:
    """Get an astronaut clipart image as a Discord File"""
    try:
        filepath = os.path.join(IMAGES_DIR, filename)
        if os.path.exists(filepath):
            return discord.File(filepath, filename=filename)
    except Exception as e:
        logger.error(f"Failed to load image {filename}: {e}")
    return None

def get_random_astronaut_image() -> Optional[discord.File]:
    """Get a random astronaut image from the directory"""
    try:
        if os.path.exists(IMAGES_DIR):
            images = [f for f in os.listdir(IMAGES_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            if images:
                filename = random.choice(images)
                return discord.File(os.path.join(IMAGES_DIR, filename), filename=filename)
    except Exception as e:
        logger.error(f"Failed to get random image: {e}")
    return None

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


_db_initialized = False

# =========================
# DATABASE INITIALIZATION
# =========================

# Shop items configuration
SHOP_ITEMS = {
    "fuel": {"name": "Fuel Cell", "description": "Powers your ship's engines", "price": 50, "emoji": "⛽", "type": "consumable", "rarity": 1},
    "repair_kit": {"name": "Repair Kit", "description": "Fixes ship damage", "price": 75, "emoji": "🔧", "type": "consumable", "rarity": 1},
    "stardust": {"name": "Stardust", "description": "Rare cosmic material", "price": 200, "emoji": "✨", "type": "material", "rarity": 2},
    "alien_artifact": {"name": "Alien Artifact", "description": "Mysterious ancient technology", "price": 500, "emoji": "🗿", "type": "collectible", "rarity": 3},
    "quantum_core": {"name": "Quantum Core", "description": "Advanced ship component", "price": 1000, "emoji": "💎", "type": "upgrade", "rarity": 4},
    "nebula_crystal": {"name": "Nebula Crystal", "description": "Beautiful and valuable", "price": 750, "emoji": "🔮", "type": "collectible", "rarity": 3},
    "plasma_cannon": {"name": "Plasma Cannon", "description": "Powerful weapon upgrade", "price": 1500, "emoji": "🔫", "type": "upgrade", "rarity": 4},
    "shield_booster": {"name": "Shield Booster", "description": "Enhanced protection", "price": 1200, "emoji": "🛡️", "type": "upgrade", "rarity": 4},
}

SHIP_UPGRADES = {
    "engine": {"name": "Engine", "emoji": "🚀", "base_cost": 100},
    "weapon": {"name": "Weapons", "emoji": "🔫", "base_cost": 150},
    "shield": {"name": "Shields", "emoji": "🛡️", "base_cost": 125},
}

def init_default_achievements(cur):
    """Create default space-themed achievements"""
    achievements = [
        # Mission achievements
        ("first_mission", "First Mission", "Complete your first space mission", "🎯", "explorer", "missions_completed", 1, 5, False),
        ("mission_specialist", "Mission Specialist", "Complete 25 missions", "🛸", "explorer", "missions_completed", 25, 50, False),
        ("veteran_pilot", "Veteran Pilot", "Complete 100 missions", "👨‍🚀", "explorer", "missions_completed", 100, 200, False),
        ("mission_master", "Mission Master", "Complete 250 missions", "🏅", "explorer", "missions_completed", 250, 500, False),
        
        # Encouragement achievements
        ("first_contact", "First Contact", "Send your first encouragement", "📡", "social", "encouragements_given", 1, 5, False),
        ("ambassador", "Ambassador", "Encourage 20 crew members", "🤝", "social", "encouragements_given", 20, 40, False),
        ("galactic_friend", "Galactic Friend", "Encourage 50 crew members", "💫", "social", "encouragements_given", 50, 100, False),
        ("beloved_crew", "Beloved Crew", "Receive 15 encouragements", "⭐", "social", "encouragements_received", 15, 30, False),
        
        # Plushie achievements
        ("first_companion", "First Companion", "Register your first plushie", "🧸", "collector", "plushies_registered", 1, 5, False),
        ("plushie_fleet", "Plushie Fleet", "Register 10 plushies", "🎪", "collector", "plushies_registered", 10, 50, False),
        ("curator", "Curator", "Register 25 plushies", "🛍️", "collector", "plushies_registered", 25, 100, False),
        
        # Knowledge achievements
        ("space_cadet", "Space Cadet", "Learn 10 space facts", "📚", "scholar", "facts_learned", 10, 20, False),
        ("astronomer", "Astronomer", "Learn 50 space facts", "🔭", "scholar", "facts_learned", 50, 100, False),
        ("astrophysicist", "Astrophysicist", "Learn 100 space facts", "👩‍🔬", "scholar", "facts_learned", 100, 200, False),
        
        # Exploration achievements
        ("planet_hunter", "Planet Hunter", "Discover 10 planets", "🪐", "explorer", "planets_discovered", 10, 20, False),
        ("spacewalker", "Spacewalker", "Take 15 spacewalks", "🧑‍🚀", "explorer", "spacewalks_taken", 15, 30, False),
        
        # Economy achievements
        ("first_purchase", "First Purchase", "Buy your first item", "💰", "merchant", "items_purchased", 1, 5, False),
        ("savvy_shopper", "Savvy Shopper", "Purchase 25 items", "🛍️", "merchant", "items_purchased", 25, 50, False),
        ("collector_supreme", "Collector Supreme", "Own 50+ items in inventory", "📦", "merchant", "total_items_owned", 50, 100, False),
        ("ship_engineer", "Ship Engineer", "Upgrade your ship 10 times", "🔧", "engineer", "ship_upgrades", 10, 75, False),
        ("master_engineer", "Master Engineer", "Upgrade your ship 25 times", "⚙️", "engineer", "ship_upgrades", 25, 150, False),
        
        # Hidden achievements
        ("secret_astronaut", "Secret Astronaut", "Mission Control knows your call sign", "🎖️", "hidden", "missions_completed", 500, 1000, True),
        ("cosmic_legend", "Cosmic Legend", "A true space pioneer", "🌌", "hidden", "encouragements_given", 100, 500, True),
        ("millionaire", "Space Millionaire", "Accumulate 10,000 credits", "💎", "hidden", "total_credits_earned", 10000, 2000, True),
    ]
    
    for ach in achievements:
        cur.execute("""INSERT INTO achievements (id, name, description, icon, category, requirement_type, requirement_count, points, hidden)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""", ach)

def init_shop_items(cur):
    """Populate shop items table"""
    for item_id, data in SHOP_ITEMS.items():
        cur.execute("""
            INSERT INTO shop_items (id, name, description, price, emoji, type, rarity)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET 
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                price = EXCLUDED.price,
                emoji = EXCLUDED.emoji,
                type = EXCLUDED.type,
                rarity = EXCLUDED.rarity
        """, (item_id, data['name'], data['description'], data['price'], data['emoji'], data['type'], data['rarity']))

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
            
            # Add new economy stat columns
            cur.execute("""
                DO $$ 
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='user_stats' AND column_name='items_purchased'
                    ) THEN
                        ALTER TABLE user_stats ADD COLUMN items_purchased INTEGER DEFAULT 0;
                    END IF;
                    
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='user_stats' AND column_name='ship_upgrades'
                    ) THEN
                        ALTER TABLE user_stats ADD COLUMN ship_upgrades INTEGER DEFAULT 0;
                    END IF;
                    
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='user_stats' AND column_name='total_items_owned'
                    ) THEN
                        ALTER TABLE user_stats ADD COLUMN total_items_owned INTEGER DEFAULT 0;
                    END IF;
                    
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='user_stats' AND column_name='total_credits_earned'
                    ) THEN
                        ALTER TABLE user_stats ADD COLUMN total_credits_earned INTEGER DEFAULT 0;
                    END IF;
                END $$;
            """)
    logger.info("Database migrations completed")

def init_db():
    """Initialize all database tables (idempotent & safe)"""
    global _db_initialized
    if _db_initialized:
        return
    with DatabasePool.get_conn() as conn:
        conn.autocommit = True
        cur = conn.cursor()
        try:
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
            
            # Achievements tables
            cur.execute("""
                CREATE TABLE IF NOT EXISTS achievements (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    icon TEXT,
                    category TEXT,
                    requirement_type TEXT,
                    requirement_count INTEGER,
                    points INTEGER DEFAULT 0,
                    hidden BOOLEAN DEFAULT FALSE
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_achievements (
                    user_id BIGINT,
                    achievement_id TEXT,
                    progress INTEGER DEFAULT 0,
                    unlocked BOOLEAN DEFAULT FALSE,
                    unlocked_at TIMESTAMPTZ,
                    PRIMARY KEY (user_id, achievement_id)
                )
            """)
            
            # User stats table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id BIGINT PRIMARY KEY,
                    missions_completed INTEGER DEFAULT 0,
                    encouragements_given INTEGER DEFAULT 0,
                    encouragements_received INTEGER DEFAULT 0,
                    plushies_registered INTEGER DEFAULT 0,
                    facts_learned INTEGER DEFAULT 0,
                    planets_discovered INTEGER DEFAULT 0,
                    spacewalks_taken INTEGER DEFAULT 0,
                    items_purchased INTEGER DEFAULT 0,
                    ship_upgrades INTEGER DEFAULT 0,
                    total_items_owned INTEGER DEFAULT 0,
                    total_credits_earned INTEGER DEFAULT 0,
                    total_points INTEGER DEFAULT 0
                )
            """)
            
            # Active missions table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS active_missions (
                    user_id BIGINT PRIMARY KEY,
                    mission_text TEXT NOT NULL,
                    started_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Shop items table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS shop_items (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    price INTEGER NOT NULL,
                    emoji TEXT,
                    type TEXT,
                    rarity INTEGER DEFAULT 1
                )
            """)
            
            # Inventory table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    user_id BIGINT,
                    item_id TEXT,
                    quantity INTEGER DEFAULT 1,
                    PRIMARY KEY (user_id, item_id)
                )
            """)
            
            # Ships table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ships (
                    user_id BIGINT PRIMARY KEY,
                    name TEXT NOT NULL,
                    ship_class TEXT DEFAULT 'Scout',
                    engine_level INTEGER DEFAULT 1,
                    weapon_level INTEGER DEFAULT 1,
                    shield_level INTEGER DEFAULT 1,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Moderator applications table - THIS WAS MISSING!
            cur.execute("""
                CREATE TABLE IF NOT EXISTS mod_applications (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username TEXT NOT NULL,
                    age TEXT NOT NULL,
                    timezone TEXT NOT NULL,
                    experience TEXT NOT NULL,
                    why_mod TEXT NOT NULL,
                    scenarios TEXT NOT NULL,
                    availability TEXT NOT NULL,
                    additional TEXT,
                    status TEXT DEFAULT 'pending',
                    reviewed_by BIGINT,
                    reviewed_at TIMESTAMPTZ,
                    submitted_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Initialize default data
            init_default_achievements(cur)
            init_shop_items(cur)
            
        finally:
            cur.close()
    
    _db_initialized = True
    logger.info("✅ Database initialized successfully")
# =========================
# ACHIEVEMENT SYSTEM
# =========================

class AchievementManager:
    @staticmethod
    async def check_and_award(user_id: int, stat_type: str, new_value: int, channel: discord.TextChannel = None):
        """Check if user unlocked any achievements and award them"""
        unlocked = []
        
        with DatabasePool.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get relevant achievements for this stat type
                cur.execute("""SELECT a.* FROM achievements a
                              LEFT JOIN user_achievements ua ON a.id = ua.achievement_id AND ua.user_id = %s
                              WHERE a.requirement_type = %s AND (ua.unlocked IS NULL OR ua.unlocked = FALSE)""",
                           (user_id, stat_type))
                achievements = cur.fetchall()
                
                for ach in achievements:
                    if new_value >= ach['requirement_count']:
                        # Unlock achievement
                        cur.execute("""INSERT INTO user_achievements (user_id, achievement_id, progress, unlocked, unlocked_at)
                                      VALUES (%s, %s, %s, TRUE, NOW())
                                      ON CONFLICT (user_id, achievement_id) 
                                      DO UPDATE SET unlocked = TRUE, unlocked_at = NOW(), progress = EXCLUDED.progress""",
                                   (user_id, ach['id'], new_value))
                        
                        # Add points
                        cur.execute("""INSERT INTO user_stats (user_id, total_points) VALUES (%s, %s)
                                      ON CONFLICT (user_id) DO UPDATE SET total_points = user_stats.total_points + EXCLUDED.total_points""",
                                   (user_id, ach['points']))
                        
                        # Track total credits earned
                        cur.execute("""INSERT INTO user_stats (user_id, total_credits_earned) VALUES (%s, %s)
                                      ON CONFLICT (user_id) DO UPDATE SET total_credits_earned = user_stats.total_credits_earned + EXCLUDED.total_credits_earned""",
                                   (user_id, ach['points']))
                        
                        unlocked.append(ach)
                    else:
                        # Update progress
                        cur.execute("""INSERT INTO user_achievements (user_id, achievement_id, progress)
                                      VALUES (%s, %s, %s)
                                      ON CONFLICT (user_id, achievement_id) DO UPDATE SET progress = EXCLUDED.progress""",
                                   (user_id, ach['id'], new_value))
        
        # Send notifications for unlocked achievements
        if unlocked and channel:
            for ach in unlocked:
                await AchievementManager.send_unlock_notification(channel, user_id, ach)
        
        # Also check total_credits_earned achievements after awarding points (but avoid recursion)
        if unlocked and stat_type != "total_credits_earned":
            with DatabasePool.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT total_credits_earned FROM user_stats WHERE user_id = %s", (user_id,))
                    stats = cur.fetchone()
                    if stats:
                        await AchievementManager.check_and_award(user_id, "total_credits_earned", stats['total_credits_earned'], channel)
        
        return unlocked
    
    @staticmethod
    async def send_unlock_notification(channel: discord.TextChannel, user_id: int, achievement: dict):
        """Send a notification when achievement is unlocked"""
        user = await channel.guild.fetch_member(user_id)
        embed = discord.Embed(
            title="🎊 Achievement Unlocked!",
            description=f"{achievement['icon']} **{achievement['name']}**\n*{achievement['description']}*\n\n+{achievement['points']} points!",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"Congratulations, {user.display_name}!")
        
        # Try to attach a random astronaut image
        astro_image = get_random_astronaut_image()
        if astro_image:
            embed.set_image(url=f"attachment://{astro_image.filename}")
            await channel.send(embed=embed, file=astro_image)
        else:
            await channel.send(embed=embed)
    
    @staticmethod
    def increment_stat(user_id: int, stat_name: str, amount: int = 1):
        """Increment a user stat and return new value"""
        with DatabasePool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""INSERT INTO user_stats (user_id, {stat_name}) VALUES (%s, %s)
                               ON CONFLICT (user_id) DO UPDATE SET {stat_name} = user_stats.{stat_name} + EXCLUDED.{stat_name}
                               RETURNING {stat_name}""",
                           (user_id, amount))
                new_value = cur.fetchone()[0]
                
                # Also track total credits earned when points are added
                if stat_name == "total_points" and amount > 0:
                    cur.execute("""INSERT INTO user_stats (user_id, total_credits_earned) VALUES (%s, %s)
                                   ON CONFLICT (user_id) DO UPDATE SET total_credits_earned = user_stats.total_credits_earned + EXCLUDED.total_credits_earned""",
                               (user_id, amount))
                
                return new_value

# =========================
# SPACE ECONOMY & SHIPS
# =========================

def calculate_upgrade_cost(current_level: int, base_cost: int) -> int:
    """Calculate cost for next upgrade level"""
    return base_cost * (current_level + 1)

class ShipManager:
    """Manages personal starship operations"""
    
    @staticmethod
    def create_ship(user_id: int, name: str) -> bool:
        try:
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO ships (user_id, name, ship_class, engine_level, weapon_level, shield_level)
                        VALUES (%s, %s, 'Scout', 1, 1, 1)
                    """, (user_id, name))
            return True
        except Exception as e:
            logger.error(f"Failed to create ship: {e}")
            return False
    
    @staticmethod
    def get_ship(user_id: int) -> Optional[Dict]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM ships WHERE user_id = %s", (user_id,))
                return cur.fetchone()
    
    @staticmethod
    def upgrade_ship(user_id: int, component: str) -> bool:
        try:
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"""
                        UPDATE ships SET {component}_level = {component}_level + 1
                        WHERE user_id = %s
                        RETURNING {component}_level
                    """, (user_id,))
                    result = cur.fetchone()
                    return result is not None
        except Exception as e:
            logger.error(f"Failed to upgrade ship: {e}")
            return False

class InventoryManager:
    """Manages user inventory and items"""
    
    @staticmethod
    def add_item(user_id: int, item_id: str, quantity: int = 1) -> bool:
        try:
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO inventory (user_id, item_id, quantity)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (user_id, item_id) 
                        DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity
                    """, (user_id, item_id, quantity))
            return True
        except Exception as e:
            logger.error(f"Failed to add item: {e}")
            return False
    
    @staticmethod
    def remove_item(user_id: int, item_id: str, quantity: int = 1) -> bool:
        try:
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE inventory SET quantity = quantity - %s
                        WHERE user_id = %s AND item_id = %s AND quantity >= %s
                        RETURNING quantity
                    """, (quantity, user_id, item_id, quantity))
                    result = cur.fetchone()
                    if result and result[0] == 0:
                        cur.execute("DELETE FROM inventory WHERE user_id = %s AND item_id = %s", (user_id, item_id))
                    return result is not None
        except Exception as e:
            logger.error(f"Failed to remove item: {e}")
            return False
    
    @staticmethod
    def get_inventory(user_id: int) -> List[Dict]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT i.item_id, i.quantity, si.name, si.description, si.emoji, si.rarity
                    FROM inventory i
                    JOIN shop_items si ON i.item_id = si.id
                    WHERE i.user_id = %s
                    ORDER BY si.rarity DESC, si.name
                """, (user_id,))
                return cur.fetchall()

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
        try:
            synced = await self.tree.sync()
            logger.info(f"✅ Synced {len(synced)} commands globally")
        except Exception as e:
            logger.error(f"❌ Command sync failed: {e}")

bot = StarflightBot()

@bot.event
async def on_ready():
    init_db()
    logger.info(f"🚀 Starflight Pilot online as {bot.user}")
    logger.info(f"📋 Registered commands: {[cmd.name for cmd in bot.tree.get_commands()]}")

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Auto-disconnect if bot is alone in voice channel"""
    if member.id != bot.user.id:
        return
    
    # If bot left a channel
    if before.channel and not after.channel:
        player = music_players.get(member.guild.id)
        if player:
            await player.leave()

async def cleanup_music_players():
    """Clean up all music players on shutdown"""
    for player in music_players.values():
        await player.leave()
    music_players.clear()
    logger.info("🧹 Music players cleaned up")

VALID_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

def get_astronaut_image(filename: str):
    if not filename or not filename.lower().endswith(VALID_IMAGE_EXTS):
        return None
    path = os.path.join(IMAGES_DIR, filename)
    if not os.path.exists(path):
        return None
    return discord.File(path, filename=filename)

# =========================
# MUSIC PLAYER SYSTEM
# =========================

class Song:
    """Represents a song in the queue"""
    def __init__(self, source: str, title: str, requester: discord.Member, is_file: bool = False):
        self.source = source
        self.title = title
        self.requester = requester
        self.is_file = is_file

class MusicPlayer:
    """Manages music playback for a guild"""
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.voice_client: Optional[discord.VoiceClient] = None
        self.queue = deque()
        self.current_song: Optional[Song] = None
        self.volume = 0.5
        self.loop = False
        
    async def join(self, channel: discord.VoiceChannel):
        """Join a voice channel"""
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.move_to(channel)
        else:
            self.voice_client = await channel.connect()
        return self.voice_client
    
    async def leave(self):
        """Leave the voice channel"""
        # Clean up current temp file
        if self.current_song and self.current_song.is_file:
            try:
                if os.path.exists(self.current_song.source):
                    os.remove(self.current_song.source)
            except Exception as e:
                logger.error(f"Error removing temp file: {e}")
        
        # Clean up queued temp files
        for song in self.queue:
            if song.is_file:
                try:
                    if os.path.exists(song.source):
                        os.remove(song.source)
                except Exception as e:
                    logger.error(f"Error removing temp file: {e}")
        
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
            self.current_song = None
            self.queue.clear()
    
    def add_song(self, song: Song):
        """Add a song to the queue"""
        self.queue.append(song)
    
    async def play_next(self):
        if self.current_song and self.current_song.is_file:
            try:
                if os.path.exists(self.current_song.source):
                    os.remove(self.current_song.source)
            except Exception as e:
                logger.error(f"Temp file cleanup error: {e}")

        if self.loop and self.current_song:
            song = self.current_song
        elif self.queue:
            song = self.queue.popleft()
        else:
            self.current_song = None
            return

        self.current_song = song

        FFMPEG_OPTIONS = {
            "before_options": "-nostdin -loglevel panic",
            "options": "-vn"
        }

        try:
            source = discord.FFmpegPCMAudio(song.source, **FFMPEG_OPTIONS)
            source = discord.PCMVolumeTransformer(source, volume=self.volume)

            loop = asyncio.get_running_loop()

            self.voice_client.play(
                source,
                after=lambda e: loop.call_soon_threadsafe(
                    asyncio.create_task, self.play_next()
                )
            )
        except Exception as e:
            logger.error(f"Playback error: {e}")
            await self.play_next()
        
    def pause(self):
        """Pause playback"""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
    
    def resume(self):
        """Resume playback"""
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
    
    def stop(self):
        """Stop playback"""
        if self.voice_client:
            self.voice_client.stop()
            self.current_song = None
    
    def skip(self):
        """Skip current song"""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
    
    def set_volume(self, volume: float):
        """Set playback volume (0.0 to 1.0)"""
        self.volume = max(0.0, min(1.0, volume))
        if self.voice_client and self.voice_client.source:
            self.voice_client.source.volume = self.volume

# Global music players dictionary
music_players: Dict[int, MusicPlayer] = {}

def get_music_player(guild: discord.Guild) -> MusicPlayer:
    """Get or create a music player for a guild"""
    if guild.id not in music_players:
        music_players[guild.id] = MusicPlayer(guild)
    return music_players[guild.id]

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

    def __init__(self, image_url: Optional[str], user_id: int, channel):
        super().__init__()
        self.image_url = image_url
        self.user_id = user_id
        self.channel = channel

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
            
            # Track stats and check achievements
            plushie_count = AchievementManager.increment_stat(self.user_id, "plushies_registered")
            await AchievementManager.check_and_award(self.user_id, "plushies_registered", plushie_count, self.channel)
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
class ModApplicationModal(discord.ui.Modal, title="Moderator Application"):
    age = discord.ui.TextInput(
        label="Age",
        placeholder="How old are you?",
        max_length=3
    )
    timezone = discord.ui.TextInput(
        label="Timezone",
        placeholder="What timezone are you in? (e.g., EST, PST, GMT)",
        max_length=50
    )
    experience = discord.ui.TextInput(
        label="Moderation Experience",
        placeholder="Describe any previous moderation experience",
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    why_mod = discord.ui.TextInput(
        label="Why do you want to be a moderator?",
        style=discord.TextStyle.paragraph,
        max_length=500
    )
    availability = discord.ui.TextInput(
        label="Availability",
        placeholder="When are you typically online? (days/times)",
        style=discord.TextStyle.paragraph,
        max_length=300
    )

    def __init__(self):
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        # Check if user has a pending application
        with DatabasePool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM mod_applications 
                    WHERE user_id = %s AND status = 'pending'
                """, (interaction.user.id,))
                existing = cur.fetchone()
                
                if existing:
                    return await interaction.response.send_message(
                        "🚫 You already have a pending moderator application. Please wait for a response from staff.",
                        ephemeral=True
                    )
                
                # Save application (simplified - removed the two-part modal)
                cur.execute("""
                    INSERT INTO mod_applications 
                    (user_id, username, age, timezone, experience, why_mod, scenarios, availability, additional)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    interaction.user.id,
                    str(interaction.user),
                    self.age.value,
                    self.timezone.value,
                    self.experience.value,
                    self.why_mod.value,
                    "See application details",  # placeholder for scenarios field
                    self.availability.value,
                    "N/A"  # no additional info collected
                ))
        
        # Send confirmation to user
        embed = discord.Embed(
            title="✅ Application Submitted!",
            description="Thank you for applying to be a moderator for the Starflight Pilot crew!",
            color=discord.Color.green()
        )
        embed.add_field(
            name="What's Next?",
            value="Our staff team will review your application and get back to you soon. You'll receive a DM with our decision.",
            inline=False
        )
        embed.set_footer(text="May the stars guide you! 🚀")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Notify staff in a staff channel (optional)
        staff_channel = discord.utils.get(interaction.guild.channels, name="staff-notifications")
        if staff_channel:
            staff_embed = discord.Embed(
                title="📋 New Moderator Application",
                description=f"**{interaction.user.mention}** has submitted a moderator application!",
                color=discord.Color.blue()
            )
            staff_embed.add_field(name="Applicant", value=interaction.user.mention, inline=True)
            staff_embed.add_field(name="User ID", value=str(interaction.user.id), inline=True)
            staff_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            staff_embed.set_footer(text="Use /mod_applications to review")
            await staff_channel.send(embed=staff_embed)

    async def on_submit(self, interaction: discord.Interaction):
        # Check if user has a pending application
        with DatabasePool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM mod_applications 
                    WHERE user_id = %s AND status = 'pending'
                """, (interaction.user.id,))
                existing = cur.fetchone()
                
                if existing:
                    return await interaction.response.send_message(
                        "🚫 You already have a pending moderator application. Please wait for a response from staff.",
                        ephemeral=True
                    )
                
                cur.execute("""
                    INSERT INTO mod_applications 
                    (user_id, username, age, timezone, experience, why_mod, scenarios, availability, additional)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    interaction.user.id,
                    str(interaction.user),
                    self.age.value,
                    self.timezone.value,
                    self.experience.value,
                    self.why_mod.value,
                    "See application details",  # Fixed - no longer references self.scenarios
                    self.availability.value,
                    "N/A"  # Fixed - no longer references self.additional
                ))
        )
        embed.add_field(
            name="What's Next?",
            value="Our staff team will review your application and get back to you soon. You'll receive a DM with our decision.",
            inline=False
        )
        embed.set_footer(text="May the stars guide you! 🚀")
        
        await interaction.response.send_message(embed=embed)
        
        # Notify staff in a staff channel (optional - you can configure this)
        # Find a staff notifications channel or log channel
        staff_channel = discord.utils.get(interaction.guild.channels, name="staff-notifications")
        if staff_channel:
            staff_embed = discord.Embed(
                title="📋 New Moderator Application",
                description=f"**{interaction.user.mention}** has submitted a moderator application!",
                color=discord.Color.blue()
            )
            staff_embed.add_field(name="Applicant", value=interaction.user.mention, inline=True)
            staff_embed.add_field(name="User ID", value=str(interaction.user.id), inline=True)
            staff_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            staff_embed.set_footer(text="Use /mod_applications to review")
            await staff_channel.send(embed=staff_embed)

# =========================
# ACHIEVEMENT COMMANDS
# =========================

@bot.tree.command(name="achievements")
async def achievements(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    """View your achievements"""
    target = member or interaction.user
    
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get user stats
            cur.execute("SELECT * FROM user_stats WHERE user_id = %s", (target.id,))
            stats = cur.fetchone()
            
            # Get unlocked achievements
            cur.execute("""SELECT a.*, ua.unlocked_at FROM achievements a
                          INNER JOIN user_achievements ua ON a.id = ua.achievement_id
                          WHERE ua.user_id = %s AND ua.unlocked = TRUE
                          ORDER BY ua.unlocked_at DESC""", (target.id,))
            unlocked = cur.fetchall()
            
            # Get locked achievements (non-hidden)
            cur.execute("""SELECT a.*, COALESCE(ua.progress, 0) as progress FROM achievements a
                          LEFT JOIN user_achievements ua ON a.id = ua.achievement_id AND ua.user_id = %s
                          WHERE (ua.unlocked IS NULL OR ua.unlocked = FALSE) AND a.hidden = FALSE
                          ORDER BY a.category, a.requirement_count""", (target.id,))
            locked = cur.fetchall()
    
    total_points = stats['total_points'] if stats else 0
    unlocked_count = len(unlocked)
    
    embed = discord.Embed(
        title=f"🏆 {target.display_name}'s Achievements",
        description=f"**Total Points:** {total_points} 🌟\n**Unlocked:** {unlocked_count} achievements\n",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    
    # Show unlocked achievements
    if unlocked:
        unlocked_text = "\n".join([f"{a['icon']} **{a['name']}** - {a['description']} (+{a['points']})" for a in unlocked[:5]])
        embed.add_field(name="✅ Recent Unlocks", value=unlocked_text, inline=False)
    
    # Show locked achievements
    if locked:
        locked_text = "\n".join([f"🔒 **{a['name']}** - {a['progress']}/{a['requirement_count']}" for a in locked[:5]])
        embed.add_field(name="🎯 In Progress", value=locked_text, inline=False)
    
    embed.set_footer(text="Shop & Achievement system by Starflight Pilot Bot")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard")
async def leaderboard(interaction: discord.Interaction):
    """View top pilots in the space station"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""SELECT user_id, total_points FROM user_stats 
                          ORDER BY total_points DESC LIMIT 10""")
            leaders = cur.fetchall()
    
    if not leaders:
        return await interaction.response.send_message("🏆 The leaderboard is empty!")
    
    embed = discord.Embed(
        title="🏆 Space Station Leaderboard",
        description="*The most accomplished pilots*",
        color=discord.Color.gold()
    )
    
    medals = ["🥇", "🥈", "🥉"]
    leaderboard_text = ""
    
    for i, leader in enumerate(leaders):
        try:
            user = await interaction.guild.fetch_member(leader['user_id'])
            medal = medals[i] if i < 3 else f"{i+1}."
            leaderboard_text += f"{medal} **{user.display_name}** - {leader['total_points']} points\n"
        except:
            continue
    
    embed.description = leaderboard_text
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="profile")
async def profile(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    """View your space pilot profile"""
    target = member or interaction.user
    
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM user_stats WHERE user_id = %s", (target.id,))
            stats = cur.fetchone()
            
            cur.execute("""SELECT COUNT(*) as count FROM user_achievements 
                          WHERE user_id = %s AND unlocked = TRUE""", (target.id,))
            ach_count = cur.fetchone()['count']
    
    if not stats:
        return await interaction.response.send_message(f"{target.display_name} hasn't started their pilot journey yet!")
    
    embed = discord.Embed(
        title=f"👨‍🚀 {target.display_name}'s Pilot Profile",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="🌟 Total Points", value=str(stats['total_points']), inline=True)
    embed.add_field(name="🏆 Achievements", value=str(ach_count), inline=True)
    embed.add_field(name="🎯 Missions Completed", value=str(stats['missions_completed']), inline=True)
    embed.add_field(name="📡 Encouragements Given", value=str(stats['encouragements_given']), inline=True)
    embed.add_field(name="💫 Encouragements Received", value=str(stats['encouragements_received']), inline=True)
    embed.add_field(name="🧸 Plushies Registered", value=str(stats['plushies_registered']), inline=True)
    embed.add_field(name="📚 Facts Learned", value=str(stats['facts_learned']), inline=True)
    embed.add_field(name="🪐 Planets Discovered", value=str(stats['planets_discovered']), inline=True)
    embed.add_field(name="🧑‍🚀 Spacewalks Taken", value=str(stats['spacewalks_taken']), inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="balance")
async def balance(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    """Check your or another user's credit balance."""
    target = member or interaction.user

    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT total_points FROM user_stats WHERE user_id = %s", (target.id,))
            stats = cur.fetchone()

    balance = stats['total_points'] if stats else 0

    embed = discord.Embed(
        title=f"💰 {target.display_name}'s Credit Balance",
        description=f"You have **{balance}** credits.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    await interaction.response.send_message(embed=embed)

# =========================
# MUSIC COMMANDS
# =========================

@bot.tree.command(name="join")
async def join(interaction: discord.Interaction):
    """Join your voice channel"""
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ You need to be in a voice channel!", ephemeral=True)
    
    player = get_music_player(interaction.guild)
    await player.join(interaction.user.voice.channel)
    await interaction.response.send_message(f"🎵 Joined {interaction.user.voice.channel.mention}")

@bot.tree.command(name="leave")
async def leave(interaction: discord.Interaction):
    """Leave the voice channel"""
    player = get_music_player(interaction.guild)
    if not player.voice_client:
        return await interaction.response.send_message("❌ Not in a voice channel!", ephemeral=True)
    
    await player.leave()
    await interaction.response.send_message("👋 Left the voice channel")

@bot.tree.command(name="play")
async def play(interaction: discord.Interaction, file: Optional[discord.Attachment] = None, url: Optional[str] = None):
    """Play an MP3 file or URL (file must be under 50MB for Discord limits)"""
    if not file and not url:
        return await interaction.response.send_message("❌ Please provide an MP3 file or URL!", ephemeral=True)
    
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ You need to be in a voice channel!", ephemeral=True)
    
    await interaction.response.defer()
    
    player = get_music_player(interaction.guild)
    
    # Join voice channel if not connected
    if not player.voice_client:
        await player.join(interaction.user.voice.channel)
    
    try:
        if file:
            # Check file size (Discord limit is 50MB for most servers)
            if file.size > 50 * 1024 * 1024:
                return await interaction.followup.send("❌ File is too large! Maximum size is 50MB.")
            
            # Download the file to a temporary location
            if not file.filename.endswith('.mp3'):
                return await interaction.followup.send("❌ Please upload an MP3 file!")
            
            # Create a temporary file
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"{interaction.id}_{file.filename}")
            
            # Download the file
            await file.save(temp_path)
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                return await interaction.followup.send("❌ Failed to save audio file.")

            song = Song(
                source=temp_path,
                title=file.filename,
                requester=interaction.user,
                is_file=True
            )
        else:
            # Use URL directly
            song = Song(
                source=url,
                title=url.split('/')[-1] or "Audio Stream",
                requester=interaction.user,
                is_file=False
            )
        
        # Add to queue
        was_playing = player.voice_client.is_playing() if player.voice_client else False
        player.add_song(song)
        
        if not was_playing:
            await player.play_next()
            embed = discord.Embed(
                title="🎵 Now Playing",
                description=f"**{song.title}**\nRequested by {song.requester.mention}",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="📋 Added to Queue",
                description=f"**{song.title}**\nRequested by {song.requester.mention}\nPosition: {len(player.queue)}",
                color=discord.Color.blue()
            )
        
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Error playing audio: {e}")
        await interaction.followup.send(f"❌ Error playing audio: {e}")

@bot.tree.command(name="pause")
async def pause(interaction: discord.Interaction):
    """Pause the current song"""
    player = get_music_player(interaction.guild)
    if not player.voice_client or not player.voice_client.is_playing():
        return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)
    
    player.pause()
    await interaction.response.send_message("⏸️ Paused playback")

@bot.tree.command(name="resume")
async def resume(interaction: discord.Interaction):
    """Resume the current song"""
    player = get_music_player(interaction.guild)
    if not player.voice_client or not player.voice_client.is_paused():
        return await interaction.response.send_message("❌ Nothing is paused!", ephemeral=True)
    
    player.resume()
    await interaction.response.send_message("▶️ Resumed playback")

@bot.tree.command(name="stop")
async def stop(interaction: discord.Interaction):
    """Stop playback and clear the queue"""
    player = get_music_player(interaction.guild)
    if not player.voice_client:
        return await interaction.response.send_message("❌ Not playing anything!", ephemeral=True)
    
    player.queue.clear()
    player.stop()
    await interaction.response.send_message("⏹️ Stopped playback and cleared queue")

@bot.tree.command(name="skip")
async def skip(interaction: discord.Interaction):
    """Skip the current song"""
    player = get_music_player(interaction.guild)
    if not player.voice_client or not player.voice_client.is_playing():
        return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)
    
    player.skip()
    await interaction.response.send_message("⏭️ Skipped to next song")

@bot.tree.command(name="queue")
async def queue(interaction: discord.Interaction):
    """View the current music queue"""
    player = get_music_player(interaction.guild)
    
    if not player.current_song and not player.queue:
        return await interaction.response.send_message("📋 Queue is empty!", ephemeral=True)
    
    embed = discord.Embed(
        title="🎵 Music Queue",
        color=discord.Color.blue()
    )
    
    if player.current_song:
        embed.add_field(
            name="🎵 Now Playing",
            value=f"**{player.current_song.title}**\nRequested by {player.current_song.requester.mention}",
            inline=False
        )
    
    if player.queue:
        queue_text = "\n".join([
            f"{i+1}. **{song.title}** - {song.requester.mention}"
            for i, song in enumerate(list(player.queue)[:10])
        ])
        if len(player.queue) > 10:
            queue_text += f"\n...and {len(player.queue) - 10} more"
        
        embed.add_field(
            name=f"📋 Up Next ({len(player.queue)} songs)",
            value=queue_text,
            inline=False
        )
    
    embed.set_footer(text=f"Volume: {int(player.volume * 100)}% | Loop: {'On' if player.loop else 'Off'}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="nowplaying")
async def nowplaying(interaction: discord.Interaction):
    """Show what's currently playing"""
    player = get_music_player(interaction.guild)
    
    if not player.current_song:
        return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)
    
    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**{player.current_song.title}**",
        color=discord.Color.green()
    )
    embed.add_field(name="Requested by", value=player.current_song.requester.mention)
    embed.add_field(name="Volume", value=f"{int(player.volume * 100)}%")
    embed.add_field(name="Loop", value="On" if player.loop else "Off")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="volume")
async def volume(interaction: discord.Interaction, level: int):
    """Set playback volume (0-100)"""
    if not 0 <= level <= 100:
        return await interaction.response.send_message("❌ Volume must be between 0 and 100!", ephemeral=True)
    
    player = get_music_player(interaction.guild)
    player.set_volume(level / 100)
    await interaction.response.send_message(f"🔊 Volume set to {level}%")

@bot.tree.command(name="loop")
async def loop(interaction: discord.Interaction):
    """Toggle loop mode for current song"""
    player = get_music_player(interaction.guild)
    player.loop = not player.loop
    
    status = "enabled" if player.loop else "disabled"
    emoji = "🔁" if player.loop else "➡️"
    await interaction.response.send_message(f"{emoji} Loop mode {status}")

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
    try:
        synced = await bot.tree.sync()
        guild_synced = await bot.tree.sync(guild=interaction.guild)
        await interaction.followup.send(f"📡 Commands synced! Global: {len(synced)}, Guild: {len(guild_synced)}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Sync error: {e}", ephemeral=True)

# =========================
# PLUSHIE COMMANDS
# =========================

@bot.tree.command(name="plushie_scan")
async def plushie_scan(interaction: discord.Interaction, photo: Optional[discord.Attachment] = None):
    """Register a new plushie to your collection"""
    await interaction.response.send_modal(PlushieModal(photo.url if photo else None, interaction.user.id, interaction.channel))

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
    
    # Store active mission
    with DatabasePool.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO active_missions (user_id, mission_text, started_at)
                          VALUES (%s, %s, NOW())
                          ON CONFLICT (user_id) DO UPDATE SET 
                          mission_text = EXCLUDED.mission_text, started_at = NOW()""",
                       (interaction.user.id, mission_text))
    
    embed = discord.Embed(
        title="🎯 New Mission Assigned!",
        description=f"{mission_text}\n\n*Use `/mission_report` when complete!*",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Mission Control • {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="mission_report")
async def mission_report(interaction: discord.Interaction):
    """Mark your current mission as complete"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM active_missions WHERE user_id = %s", (interaction.user.id,))
            active = cur.fetchone()
            
            if not active:
                return await interaction.response.send_message("❌ You don't have an active mission. Use `/mission` to get one!", ephemeral=True)
            
            # Delete active mission
            cur.execute("DELETE FROM active_missions WHERE user_id = %s", (interaction.user.id,))
    
    embed = discord.Embed(
        title="✅ Mission Complete!",
        description=f"**Mission:** {active['mission_text']}\n\n*Excellent work, pilot!*",
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Completed by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)
    
    # Track stats and check achievements
    mission_count = AchievementManager.increment_stat(interaction.user.id, "missions_completed")
    await AchievementManager.check_and_award(interaction.user.id, "missions_completed", mission_count, interaction.channel)

@bot.tree.command(name="mission_status")
async def mission_status(interaction: discord.Interaction):
    """Check your current active mission"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM active_missions WHERE user_id = %s", (interaction.user.id,))
            active = cur.fetchone()
    
    if not active:
        return await interaction.response.send_message("📋 You don't have an active mission. Use `/mission` to get one!", ephemeral=True)
    
    time_elapsed = datetime.now(timezone.utc) - active['started_at']
    minutes = int(time_elapsed.total_seconds() / 60)
    
    embed = discord.Embed(
        title="📋 Active Mission Status",
        description=f"**Mission:** {active['mission_text']}\n\n**Time Elapsed:** {minutes} minutes",
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Use /mission_report when complete!")
    await interaction.response.send_message(embed=embed, ephemeral=True)

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
    
    # Track stats and check achievements
    given_count = AchievementManager.increment_stat(interaction.user.id, "encouragements_given")
    received_count = AchievementManager.increment_stat(target.id, "encouragements_received")
    
    await AchievementManager.check_and_award(interaction.user.id, "encouragements_given", given_count, interaction.channel)
    await AchievementManager.check_and_award(target.id, "encouragements_received", received_count, interaction.channel)

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
    
    # Track stats and check achievements
    facts_count = AchievementManager.increment_stat(interaction.user.id, "facts_learned")
    await AchievementManager.check_and_award(interaction.user.id, "facts_learned", facts_count, interaction.channel)

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
    
    # Track stats and check achievements
    planets_count = AchievementManager.increment_stat(interaction.user.id, "planets_discovered")
    await AchievementManager.check_and_award(interaction.user.id, "planets_discovered", planets_count, interaction.channel)

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
    
    # Track stats and check achievements
    spacewalks_count = AchievementManager.increment_stat(interaction.user.id, "spacewalks_taken")
    await AchievementManager.check_and_award(interaction.user.id, "spacewalks_taken", spacewalks_count, interaction.channel)

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

@bot.tree.command(name="shop")
async def shop(interaction: discord.Interaction):
    """View available shop items"""
    embed = discord.Embed(
        title="🛒 Space Station Shop",
        description="Spend credits to upgrade your journey",
        color=discord.Color.blue()
    )

    for item_id, item in SHOP_ITEMS.items():
        embed.add_field(
            name=f"{item['emoji']} {item['name']} — {item['price']}💳",
            value=item["description"],
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="buy")
async def buy(interaction: discord.Interaction, item_id: str, quantity: int = 1):
    """Buy an item from the shop"""
    item = SHOP_ITEMS.get(item_id)
    if not item:
        return await interaction.response.send_message("❌ Item not found.", ephemeral=True)

    cost = item["price"] * max(1, quantity)

    with DatabasePool.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT total_points FROM user_stats WHERE user_id = %s",
                (interaction.user.id,)
            )
            row = cur.fetchone()
            balance = row[0] if row else 0

            if balance < cost:
                return await interaction.response.send_message(
                    f"❌ You need {cost} credits but only have {balance}.",
                    ephemeral=True
                )

            cur.execute(
                """INSERT INTO user_stats (user_id, total_points)
                   VALUES (%s, %s)
                   ON CONFLICT (user_id)
                   DO UPDATE SET total_points = user_stats.total_points - %s""",
                (interaction.user.id, balance - cost, cost)
            )

    InventoryManager.add_item(interaction.user.id, item_id, quantity)

    purchased = AchievementManager.increment_stat(
        interaction.user.id, "items_purchased", quantity
    )
    await AchievementManager.check_and_award(
        interaction.user.id, "items_purchased", purchased, interaction.channel
    )

    await interaction.response.send_message(
        f"✅ Purchased **{quantity}× {item['name']}** for {cost} credits!"
    )

@bot.tree.command(name="inventory")
async def inventory(interaction: discord.Interaction):
    """View your inventory"""
    items = InventoryManager.get_inventory(interaction.user.id)
    if not items:
        return await interaction.response.send_message("📦 Your inventory is empty.")

    embed = discord.Embed(
        title="🎒 Your Inventory",
        color=discord.Color.green()
    )

    for item in items:
        embed.add_field(
            name=f"{item['emoji']} {item['name']} ×{item['quantity']}",
            value=item["description"],
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ship")
async def ship(interaction: discord.Interaction):
    """View your ship"""
    ship = ShipManager.get_ship(interaction.user.id)
    if not ship:
        return await interaction.response.send_message(
            "🚀 You don't have a ship yet. Use `/ship_create`."
        )

    embed = discord.Embed(
        title=f"🚀 {ship['name']}",
        description=f"Class: **{ship['ship_class']}**",
        color=discord.Color.orange()
    )

    embed.add_field(name="🚀 Engine", value=f"Level {ship['engine_level']}")
    embed.add_field(name="🔫 Weapons", value=f"Level {ship['weapon_level']}")
    embed.add_field(name="🛡️ Shields", value=f"Level {ship['shield_level']}")

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ship_create")
async def ship_create(interaction: discord.Interaction, name: str):
    """Create your first ship"""
    if ShipManager.get_ship(interaction.user.id):
        return await interaction.response.send_message(
            "❌ You already own a ship.",
            ephemeral=True
        )

    if ShipManager.create_ship(interaction.user.id, name):
        await interaction.response.send_message(f"🚀 Ship **{name}** commissioned!")
    else:
        await interaction.response.send_message("❌ Failed to create ship.")

@bot.tree.command(name="ship_upgrade")
async def ship_upgrade(interaction: discord.Interaction, component: str):
    """Upgrade a ship component"""
    component = component.lower()
    upgrade = SHIP_UPGRADES.get(component)

    if not upgrade:
        return await interaction.response.send_message(
            "❌ Invalid component. Choose engine, weapon, or shield.",
            ephemeral=True
        )

    ship = ShipManager.get_ship(interaction.user.id)
    if not ship:
        return await interaction.response.send_message(
            "❌ You don't own a ship.",
            ephemeral=True
        )

    level = ship[f"{component}_level"]
    cost = calculate_upgrade_cost(level, upgrade["base_cost"])

    with DatabasePool.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT total_points FROM user_stats WHERE user_id = %s",
                (interaction.user.id,)
            )
            balance = cur.fetchone()[0]

            if balance < cost:
                return await interaction.response.send_message(
                    f"❌ Upgrade costs {cost}, you have {balance}.",
                    ephemeral=True
                )

            cur.execute(
                "UPDATE user_stats SET total_points = total_points - %s WHERE user_id = %s",
                (cost, interaction.user.id)
            )

    if ShipManager.upgrade_ship(interaction.user.id, component):
        upgraded = AchievementManager.increment_stat(
            interaction.user.id, "ship_upgrades"
        )
        await AchievementManager.check_and_award(
            interaction.user.id, "ship_upgrades", upgraded, interaction.channel
        )

        await interaction.response.send_message(
            f"⚙️ {upgrade['emoji']} **{upgrade['name']} upgraded to Level {level + 1}!**"
        )
    else:
        await interaction.response.send_message("❌ Failed to upgrade ship.")

# =========================
# MODERATOR APPLICATION COMMANDS
# =========================

@bot.tree.command(name="apply_mod")
async def apply_mod(interaction: discord.Interaction):
    """Apply to become a moderator for the Starflight Pilot crew"""
    await interaction.response.send_modal(ModApplicationModal())

@bot.tree.command(name="mod_applications")
@is_staff()
async def mod_applications(interaction: discord.Interaction, status: Optional[str] = "pending"):
    """View moderator applications (Staff only)"""
    valid_statuses = ["pending", "accepted", "rejected", "all"]
    if status not in valid_statuses:
        return await interaction.response.send_message(
            f"❌ Invalid status. Use: {', '.join(valid_statuses)}",
            ephemeral=True
        )
    
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if status == "all":
                cur.execute("""
                    SELECT * FROM mod_applications 
                    ORDER BY submitted_at DESC LIMIT 20
                """)
            else:
                cur.execute("""
                    SELECT * FROM mod_applications 
                    WHERE status = %s 
                    ORDER BY submitted_at DESC LIMIT 20
                """, (status,))
            applications = cur.fetchall()
    
    if not applications:
        return await interaction.response.send_message(
            f"📋 No {status} applications found.",
            ephemeral=True
        )
    
    embed = discord.Embed(
        title=f"📋 Moderator Applications ({status.title()})",
        color=discord.Color.blue()
    )
    
    for app in applications[:10]:  # Show first 10
        try:
            user = await interaction.guild.fetch_member(app['user_id'])
            status_emoji = {"pending": "⏳", "accepted": "✅", "rejected": "❌"}.get(app['status'], "❓")
            
            embed.add_field(
                name=f"{status_emoji} {user.display_name} (ID: {app['id']})",
                value=f"Submitted: <t:{int(app['submitted_at'].timestamp())}:R>\nUse `/mod_application_view {app['id']}` to review",
                inline=False
            )
        except:
            embed.add_field(
                name=f"{status_emoji} Unknown User (ID: {app['id']})",
                value=f"User ID: {app['user_id']}\nSubmitted: <t:{int(app['submitted_at'].timestamp())}:R>",
                inline=False
            )
    
    if len(applications) > 10:
        embed.set_footer(text=f"Showing 10 of {len(applications)} applications")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="mod_application_view")
@is_staff()
async def mod_application_view(interaction: discord.Interaction, application_id: int):
    """View a specific moderator application (Staff only)"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM mod_applications WHERE id = %s", (application_id,))
            app = cur.fetchone()
    
    if not app:
        return await interaction.response.send_message("❌ Application not found.", ephemeral=True)
    
    try:
        user = await interaction.guild.fetch_member(app['user_id'])
        user_mention = user.mention
        avatar_url = user.display_avatar.url
    except:
        user_mention = f"Unknown User (ID: {app['user_id']})"
        avatar_url = None
    
    status_color = {
        "pending": discord.Color.orange(),
        "accepted": discord.Color.green(),
        "rejected": discord.Color.red()
    }.get(app['status'], discord.Color.grey())
    
    embed = discord.Embed(
        title=f"📋 Application #{app['id']}",
        color=status_color
    )
    
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
    
    embed.add_field(name="👤 Applicant", value=user_mention, inline=True)
    embed.add_field(name="📊 Status", value=app['status'].title(), inline=True)
    embed.add_field(name="📅 Submitted", value=f"<t:{int(app['submitted_at'].timestamp())}:R>", inline=True)
    embed.add_field(name="🎂 Age", value=app['age'], inline=True)
    embed.add_field(name="🌍 Timezone", value=app['timezone'], inline=True)
    embed.add_field(name="⏰ Availability", value=app['availability'], inline=True)
    embed.add_field(name="📚 Experience", value=app['experience'], inline=False)
    embed.add_field(name="💭 Why Moderator?", value=app['why_mod'], inline=False)
    embed.add_field(name="⚖️ Conflict Handling", value=app['scenarios'], inline=False)
    
    if app['additional'] and app['additional'] != "N/A":
        embed.add_field(name="➕ Additional Info", value=app['additional'], inline=False)
    
    if app['reviewed_by']:
        try:
            reviewer = await interaction.guild.fetch_member(app['reviewed_by'])
            embed.add_field(
                name="👔 Reviewed By",
                value=f"{reviewer.mention} on <t:{int(app['reviewed_at'].timestamp())}:R>",
                inline=False
            )
        except:
            pass
    
    embed.set_footer(text=f"Use /mod_application_accept or /mod_application_reject {application_id}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="mod_application_accept")
@is_staff()
async def mod_application_accept(interaction: discord.Interaction, application_id: int, message: Optional[str] = None):
    """Accept a moderator application (Staff only)"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM mod_applications WHERE id = %s", (application_id,))
            app = cur.fetchone()
            
            if not app:
                return await interaction.response.send_message("❌ Application not found.", ephemeral=True)
            
            if app['status'] != 'pending':
                return await interaction.response.send_message(
                    f"❌ This application has already been {app['status']}.",
                    ephemeral=True
                )
            
            # Update application status
            cur.execute("""
                UPDATE mod_applications 
                SET status = 'accepted', reviewed_by = %s, reviewed_at = NOW()
                WHERE id = %s
            """, (interaction.user.id, application_id))
    
    # Send DM to applicant
    try:
        user = await interaction.guild.fetch_member(app['user_id'])
        
        dm_embed = discord.Embed(
            title="✅ Moderator Application Accepted!",
            description="Congratulations! Your application to become a moderator has been **accepted**!",
            color=discord.Color.green()
        )
        dm_embed.add_field(
            name="🎊 Welcome to the Team!",
            value="A staff member will reach out to you soon with next steps and training information.",
            inline=False
        )
        
        if message:
            dm_embed.add_field(name="📝 Message from Staff", value=message, inline=False)
        
        dm_embed.set_footer(text=f"Starflight Pilot • {interaction.guild.name}")
        
        await user.send(embed=dm_embed)
        dm_status = "✅ DM sent"
    except:
        dm_status = "⚠️ Could not send DM"
    
    await interaction.response.send_message(
        f"✅ Application #{application_id} **accepted**! {dm_status}",
        ephemeral=True
    )

@bot.tree.command(name="mod_application_reject")
@is_staff()
async def mod_application_reject(interaction: discord.Interaction, application_id: int, reason: Optional[str] = None):
    """Reject a moderator application (Staff only)"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM mod_applications WHERE id = %s", (application_id,))
            app = cur.fetchone()
            
            if not app:
                return await interaction.response.send_message("❌ Application not found.", ephemeral=True)
            
            if app['status'] != 'pending':
                return await interaction.response.send_message(
                    f"❌ This application has already been {app['status']}.",
                    ephemeral=True
                )
            
            # Update application status
            cur.execute("""
                UPDATE mod_applications 
                SET status = 'rejected', reviewed_by = %s, reviewed_at = NOW()
                WHERE id = %s
            """, (interaction.user.id, application_id))
    
    # Send DM to applicant
    try:
        user = await interaction.guild.fetch_member(app['user_id'])
        
        dm_embed = discord.Embed(
            title="❌ Moderator Application Update",
            description="Thank you for your interest in becoming a moderator. Unfortunately, we are unable to accept your application at this time.",
            color=discord.Color.red()
        )
        dm_embed.add_field(
            name="🌟 Don't Give Up!",
            value="This doesn't mean you can't apply again in the future. Continue being an active and positive member of our community!",
            inline=False
        )
        
        if reason:
            dm_embed.add_field(name="📝 Feedback", value=reason, inline=False)
        
        dm_embed.set_footer(text=f"Starflight Pilot • {interaction.guild.name}")
        
        await user.send(embed=dm_embed)
        dm_status = "✅ DM sent"
    except:
        dm_status = "⚠️ Could not send DM"
    
    await interaction.response.send_message(
        f"❌ Application #{application_id} **rejected**. {dm_status}",
        ephemeral=True
    )

@bot.tree.command(name="my_application")
async def my_application(interaction: discord.Interaction):
    """Check the status of your moderator application"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM mod_applications 
                WHERE user_id = %s 
                ORDER BY submitted_at DESC LIMIT 1
            """, (interaction.user.id,))
            app = cur.fetchone()
    
    if not app:
        return await interaction.response.send_message(
            "📋 You haven't submitted a moderator application yet. Use `/apply_mod` to apply!",
            ephemeral=True
        )
    
    status_emoji = {"pending": "⏳", "accepted": "✅", "rejected": "❌"}.get(app['status'], "❓")
    status_color = {
        "pending": discord.Color.orange(),
        "accepted": discord.Color.green(),
        "rejected": discord.Color.red()
    }.get(app['status'], discord.Color.grey())
    
    embed = discord.Embed(
        title=f"{status_emoji} Your Moderator Application",
        color=status_color
    )
    embed.add_field(name="📊 Status", value=app['status'].title(), inline=True)
    embed.add_field(name="📅 Submitted", value=f"<t:{int(app['submitted_at'].timestamp())}:R>", inline=True)
    
    if app['status'] == 'pending':
        embed.description = "Your application is currently being reviewed by our staff team. We'll notify you once a decision has been made!"
    elif app['status'] == 'accepted':
        embed.description = "Congratulations! Your application was accepted. A staff member should reach out to you soon."
    elif app['status'] == 'rejected':
        embed.description = "Your application was not accepted this time. You're welcome to apply again in the future after being an active community member!"
    
    embed.set_footer(text="Thank you for your interest in helping our community! 🚀")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

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
    
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        logger.info("🛑 Bot shutdown requested")
    finally:
        # Clean up music players
        asyncio.run(cleanup_music_players())
