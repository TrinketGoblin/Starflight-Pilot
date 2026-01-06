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
from typing import Optional, Dict, List, Union, Any
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from dotenv import load_dotenv
from PIL import Image
import aiohttp
from collections import deque
import tempfile

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
TOKEN = os.getenv("DISCORD_TOKEN")
STAFF_ROLE_ID = int(os.getenv("STAFF_ROLE_ID", "0"))
IMAGES_DIR = "astronauts"
PNG_DEFAULT = "astronauts\\1 - Astronaut.png"

def get_image_path(image_id: int, image_type: str = "Astronaut") -> Optional[str]:
    """Get image path with both ID and type (Astronaut or Alien)"""
    path = os.path.join(IMAGES_DIR, f"{image_id} - {image_type}.png")
    return path if os.path.exists(path) else None


PALETTE = {
    'SLB': "#f0f4ff", 'LB':  "#b1c3f9", 'SB':  "#7395cc", 
    'VB':  "#546bfa", 'PB':  "#3a4ebc", 'VLB': "#303d98", 
    'MB':  "#28386a", 'DPB': "#222f4f", 'DSB': "#1e155e",
    'SLY': "#fdf1a3", 'LY':  "#faea84", 'SY':  "#f6e267", 
    'VY':  "#f1d94b", 'PY':  "#ebcf2f", 'VLY': "#dfc11a", 
    'MY':  "#bea41a", 'DPY': "#9d8819", 'DSY': "#7e6d17",
}

SHOP_ITEMS = {
    1: {'id': 1, 'name': 'Fuel Cell', 'description': 'Refuel your spaceship to continue your journey.', 'price': 100, 'emoji': '⛽'},
    2: {'id': 2, 'name': 'Repair Kit', 'description': 'Fix damages to your spaceship.', 'price': 150, 'emoji': '🛠️'},
    3: {'id': 3, 'name': 'Stardust', 'description': 'Enhance your spaceship with cosmic energy.', 'price': 200, 'emoji': '✨'},
    4: {'id': 4, 'name': 'Galactic Map', 'description': 'Unlock new star systems to explore.', 'price': 250, 'emoji': '🗺️'},
    5: {'id': 5, 'name': 'Cosmic Shield', 'description': 'Protect your spaceship from asteroids.', 'price': 300, 'emoji': '🛡️'},
    6: {'id': 6, 'name': 'Quantum Engine', 'description': 'Upgrade your spaceship\'s speed.', 'price': 350, 'emoji': '🚀'},
    7: {'id': 7, 'name': 'Black Hole Detector', 'description': 'Avoid black holes during travel.', 'price': 400, 'emoji': '🕳️'},
    8: {'id': 8, 'name': 'Time Dilation Device', 'description': 'Slow down time for better navigation.', 'price': 450, 'emoji': '⏳'},
    9: {'id': 9, 'name': 'Alien Translator', 'description': 'Communicate with extraterrestrial beings.', 'price': 500, 'emoji': '👽'},
    "10": {'id': 10, 'name': 'Hyperdrive Booster', 'description': 'Boost your spaceship\'s acceleration.', 'price': 550, 'emoji': '⚡'}
}

SHIP_UPGRADES = {
    "engine": {'upgrade_id': 1, 'name': 'Engine', 'emoji': '🚀', 'base_cost': 100},
    "weapon": {'upgrade_id': 2, 'name': 'Weapon', 'emoji': '🔫', 'base_cost': 150},
    "shield": {'upgrade_id': 3, 'name': 'Shield', 'emoji': '🛡️', 'base_cost': 125}
}

ANNOUNCEMENT_CONFIG = {
    "header": {
        "color": PALETTE['SB'],
        "description": "<@&1454290642174742578>",
        "image_url": "https://64.media.tumblr.com/fb4527b4d5ba87d89b66a9c7ce471836/01cb3d1ba106fa8c-2e/s1280x1920/e393f5a5a2d9275d944befbe0c0a14f051176874.pnj"
    },
    "body": {
        "color": PALETTE['LB'],
    },
    "footer": {
        "color": PALETTE['SLB'],
        "description": "🚀 **pls invite ppl to join our discord server and help us grow!**\n\n[Click here](https://discord.google.com/4QzQYeuApB) to join!",
        "image_url": "https://64.media.tumblr.com/b1087d6d3803689dd69ed77055e45141/01cb3d1ba106fa8c-7a/s1280x1920/b8342d92c350abeee78d7c8b0636625679dfc8ae.pnj"
    }
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')
logger = logging.getLogger('Starlightpilot')

# Image Helper Functions
def load_image() -> Optional[Image.Image]:
    try:
        if os.path.exists(IMAGES_DIR):
            return Image.open(os.path.join(IMAGES_DIR, PNG_DEFAULT)).convert("RGBA")
        else:
            logger.warning("Images directory does not exist.")
            return None
    except Exception as e:
        logger.error(f"Error loading image: {e}")
        return None

# Database Helper Classes and Functions
class DatabasePool:
    """Manages a pool of database connections."""
    _pool: Optional[SimpleConnectionPool] = None
    @classmethod
    def initialize(cls):
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL environment variable not set or not reachable.")
        cls._pool = SimpleConnectionPool(1, 10, dsn=DATABASE_URL)
        logger.info("Database connection pool initialized.")
    @classmethod
    @contextmanager
    def get_conn(cls):
        if cls._pool is None:
            cls.initialize()
        if cls._pool is None:
            raise RuntimeError("Database connection pool is not initialized.")
        conn = cls._pool.getconn()
        try:
            yield conn
        finally:
            cls._pool.putconn(conn)
_db_initialized = False

#Database Init and Migration

def migrate_db():
    """Run database migrations"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE plushies ADD COLUMN IF NOT EXISTS image_data BYTEA;")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS items_purchased INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS ship_upgrades INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS total_items_owned INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS total_credits_earned INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS missions_completed INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS encouragements_given INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS encouragements_received INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS plushies_registered INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS facts_learned INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS missions_failed INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS spacewalks_taken INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS planets_discovered INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS salvages_completed INTEGER DEFAULT 0;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_stats_total_items_owned ON user_stats(total_items_owned);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_stats_total_credits_earned ON user_stats(total_credits_earned);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_stats_missions_completed ON user_stats(missions_completed);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_stats_encouragements_given ON user_stats(encouragements_given);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_stats_plushies_registered ON user_stats(plushies_registered);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_stats_facts_learned ON user_stats(facts_learned);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_user_stats_planets_discovered ON user_stats(planets_discovered);")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS salvages_completed INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE ships ADD COLUMN IF NOT EXISTS health INTEGER DEFAULT 100;")
            cur.execute("ALTER TABLE ships ADD COLUMN IF NOT EXISTS max_health INTEGER DEFAULT 100;")
            cur.execute("ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS salvages_completed INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE ships ADD COLUMN IF NOT EXISTS health INTEGER DEFAULT 100;")
            cur.execute("ALTER TABLE ships ADD COLUMN IF NOT EXISTS max_health INTEGER DEFAULT 100;")
            # ---------------------------------------
    logger.info("Database migrations completed")

    init_default_missions(cur)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS encouragements (
            id SERIAL PRIMARY KEY,
            message TEXT NOT NULL
        )
    """)
    init_default_encouragments(cur)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS space_facts (
            id SERIAL PRIMARY KEY,
            fact TEXT NOT NULL
        )
    """)
    init_default_space_facts(cur)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS shop_items (
            item_id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            emoji TEXT,
            type TEXT DEFAULT 'consumable',
            rarity INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ship_upgrades (
            upgrade_id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            emoji TEXT,
            base_cost INTEGER NOT NULL
        )
    """)
    init_ship_upgrades(cur)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            icon TEXT,
            category TEXT,
            requirement_type TEXT NOT NULL,
            requirement_count INTEGER NOT NULL,
            credits INTEGER DEFAULT 0,
            hidden BOOLEAN DEFAULT FALSE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_achievements (
            user_id BIGINT NOT NULL,
            achievement_id TEXT NOT NULL REFERENCES achievements(id),
            progress INTEGER DEFAULT 0,
            unlocked BOOLEAN DEFAULT FALSE,
            unlocked_at TIMESTAMPTZ,
            PRIMARY KEY (user_id, achievement_id)
        )
    """)
def init_default_missions(cur):
    """Create default missions"""
    cur.execute("""
    INSERT INTO missions (name, description)
    VALUES 
    ('1', "🎨 Color a picture of a planet and share it in chat!"),
    ('2', "💧 Drink a glass of moon juice (water) to stay hydrated!"),
    ('3', "🌟 Count 10 stars (or anything sparkly) around you!"),
    ('4', "📚 Read a chapter of your favorite space book!"),
    ('5', "🧸 Give your favorite plushie a big hug!"),
    ('6', "🎵 Listen to a calming lullaby or space music!"),
    ('7', "🌙 Take a 10-minute nap to recharge your energy!"),
    ('8', "🍪 Have a healthy snack from the space galley!"),
    ('9', "🚀 Do 5 jumping jacks like you're in zero gravity!"),
    ('10', "✨ Tell someone something nice about them!"),
    ('11', "🌌 Draw what you think a nebula looks like!"),
    ('12', "🛌 Make your bed like you're preparing your space pod!"),
    ('13', "🎮 Play with your favorite toy for 15 minutes!"),
    ('14', "🌠 Look out the window and find 3 interesting things!"),
    ('15', "💫 Practice writing your name in 'space letters'!"),
    ('16', "🧃 Make yourself a special 'astronaut drink'!"),
    ('17', "🎪 Do a silly dance to make your crewmates smile!"),
    ('18', "🌍 Learn one new fact about space or planets!"),
    ('19', "🛸 Build something with blocks or craft supplies!"),
    ('20', "⭐ Tell someone about your day and how you're feeling!"),
    ('21', "🔭 Design a flag for your own personal moon base!"),
    ('22', "🪐 Use a spoon as a 'space shovel' to move small objects!"),
    ('23', "🛰️ Check your 'oxygen levels' by taking three slow, deep breaths!"),
    ('24', "☄️ Spot a 'shooting star' by finding something that moves fast outside!"),
    ('25', "🌑 Sit in the darkest room in your house and imagine you're in deep space!"),
    ('26', "🌌 Create a constellation by drawing dots on paper and connecting them!"),
    ('27', "📡 Send a 'radio signal' by humming a low tune for 30 seconds!"),
    ('28', "🌋 Research a volcano on another planet, like Olympus Mons!"),
    ('29', "🧼 Sanitize your flight deck by wiping down your desk or table!"),
    ('30', "👣 Walk in slow motion like you are on a high-gravity planet!"),
    ('31', "🧩 Complete a puzzle to repair the ship's navigation computer!"),
    ('32', "🥪 Cut your sandwich into the shape of a star or a rocket!"),
    ('33', "🎒 Pack a 'survival bag' with 5 things you'd take to Mars!"),
    ('34', "🔦 Use a flashlight to make signals on the ceiling!"),
    ('35', "🧤 Put on gloves and try to pick up coins like an astronaut in a spacesuit!"),
    ('36', "🌞 Stand in a sunny spot for 2 minutes to solar-charge your batteries!"),
    ('37', "⏲️ Set a timer for 60 seconds and sit perfectly still like a frozen comet!"),
    ('38', "🧊 Watch an ice cube melt and imagine it's a comet passing the sun!"),
    ('39', "🎵 Compose a 3-note 'alien language' greeting!"),
    ('40', "🧹 Sweep the stardust off the floor in one room!"),
    ('41', "📖 Find a word in a book that starts with 'Z' for Zenith!"),
    ('42', "🧘 Do a tree pose to maintain balance in zero gravity!"),
    ('43', "🥛 Mix a 'nebula swirl' by adding a drop of juice to your water!"),
    ('44', "🤖 Talk like a robot for the next 5 minutes!"),
    ('45', "🌓 Draw the moon exactly as it looks in the sky tonight!"),
    ('46', "🧸 Organize your plushies into a 'crew photo'!"),
    ('47', "🔋 Lay flat on the floor for 5 minutes to let your systems recharge!"),
    ('48', "🧂 Sprinkle some 'space salt' (glitter or sand) on a craft project!"),
    ('49', "🔭 Peer through a cardboard tube to spot distant galaxies!"),
    ('50', "🛸 Hide an 'alien artifact' for someone else to find later!"),
    ('51', "📦 Build a moon rover using only items from your recycling bin!"),
    ('52', "🎈 Blow up a balloon and let it go to see 'rocket propulsion'!"),
    ('53', "👟 Tie your shoes tight for a safe 'spacewalk'!"),
    ('54', "🍎 Eat an 'asteroid' (a piece of fruit) to stay energized!"),
    ('55', "🤫 Whisper like you're sending a secret message to Mission Control!"),
    ('56', "🛸 Invent a dance that an alien from Saturn would do!"),
    ('57', "🌌 Name three things that are black like the deep void of space!"),
    ('58', "🖇️ Chain 10 paperclips together to make a 'space station' antenna!"),
    ('59', "🧥 Put on your 'spacesuit' (jacket) as fast as you can!"),
    ('60', "💤 Close your eyes and imagine what the Earth looks like from above!"),
    ('61', "🖼️ Draw a portrait of your favorite alien friend!"),
    ('62', "🥄 Balance a 'moon rock' (grape or marble) on a spoon while walking!"),
    ('63', "🛁 Take a 'galactic bath' or shower to wash off the cosmic dust!"),
    ('64', "🧦 Sort your socks into 'binary pairs'!"),
    ('65', "🕰️ Check the 'Stardate' (current time) and write it down!"),
    ('66', "🌡️ Check the temperature outside your space pod!"),
    ('67', "🥤 Blow bubbles in your drink to simulate a boiling star!"),
    ('68', "📝 Write a 'Captain's Log' entry about your day so far!"),
    ('69', "🏗️ Build the tallest tower possible with blocks or pillows!"),
    ('70', "👋 Wave at the sky to greet the astronauts on the ISS!"),
    ('71', "🎶 Hum the theme song to your favorite space movie!"),
    ('72', "🏃 Run in place for 30 seconds to test your thrusters!"),
    ('73', "🥨 Have a 'crunchy comet' (pretzel) for a snack!"),
    ('74', "🧱 Use LEGOs to build a communication dish!"),
    ('75', "🛑 Practice a 'manual override' by stopping whatever you're doing immediately!"),
    ('76', "🤸 Do a somersault or roll to simulate a tumbling asteroid!"),
    ('77', "🥛 Drink a glass of white milk or soy milk like 'star fuel'!"),
    ('78', "🎨 Paint a rock to look like a tiny planet!"),
    ('79', "🌿 Water a 'space plant' (houseplant) so it can grow!"),
    ('80', "🕶️ Put on sunglasses to protect your eyes from solar flares!"),
    ('81', "📎 Make a 'constellation' on your desk using paperclips!"),
    ('82', "💨 Blow a feather or piece of paper across the table using 'solar wind'!"),
    ('83', "🟡 Find something spherical like a planet in your room!"),
    ('84', "🔴 Find something red like the surface of Mars!"),
    ('85', "⚪ Find something white like the icy moon Europa!"),
    ('86', "🔵 Find something blue like the gas giant Neptune!"),
    ('87', "🟠 Find something orange like a glowing sun!"),
    ('88', "🔭 Look at a map and find a place you'd like to 'land'!"),
    ('89', "🛸 Use a frisbee or plate as a flying saucer!"),
    ('90', "👣 Walk heel-to-toe in a straight line to test your equilibrium!"),
    ('91', "✨ Count how many lights are in the room you're in!"),
    ('92', "🛌 Tightly tuck yourself into a blanket like a sleeping astronaut!"),
    ('93', "🔊 Make a 'whoosh' sound every time you walk through a door!"),
    ('94', "🧤 Try to tie your shoes while wearing thick mittens!"),
    ('95', "🥫 Organize the 'food rations' in your kitchen pantry!"),
    ('96', "🕯️ Watch a candle flame (with supervision) and think of star fire!"),
    ('97', "🛸 Practice your 'tractor beam' by picking up toys without using hands!"),
    ('98', "🪑 Sit under a table and pretend it's your cramped space capsule!"),
    ('99', "🪁 Make a small paper plane and see how far it 'glides'!"),
    ('100', "🌑 Paint your fingernails (or one nail) 'space black'!"),
    ('101', "🥛 Make a 'milky way' milkshake or smoothie!"),
    ('102', "🔔 Ring a bell or make a 'ding' sound for every successful task!"),
    ('103', "📸 Take a 'selfie' in your astronaut gear!"),
    ('104', "🗺️ Draw a map of your house as if it were a space station!"),
    ('105', "🧵 Use a string to measure the 'circumference' of your head!"),
    ('106', "🧠 Learn the names of the 8 planets in order!")
    ('107', "📣 Give a 10-second speech as if you just landed on the moon!")
    ('108', "💧 Use a dropper or straw to move 'liquid fuel' between two cups!")
    ('109', "🧺 Carry a laundry basket like it's a heavy moon-sample container!")
    ('110', "🛏️ Jump on the bed (carefully!) to feel 1 second of weightlessness!"), 
    ('111', "🍎 Eat a 'green giant' (a green grape or apple)!"), 
    ('112', "🔋 Check the battery level on one of your gadgets!")
    ('113', "🥤 Sip through a straw to practice drinking in zero-g!")
    ('114', "🛸 Spin a coin and see how long the 'galaxy' rotates!")
    ('115', "🔦 Shine a light through a colander to create stars on the wall!")
    ('116', "🧤 Put on socks on your hands and try to fold a piece of paper!"), 
    ('117', "🧼 Wash your hands for 20 seconds to remove 'space germs'!"), 
    ('118', "🚪 Close all the 'airlocks' (doors) in your house!"), 
    ('119', "💤 Take a 5-minute 'power nap' in your commander's chair!"), 
    ('120', "🧗 Climb onto a couch or chair to reach the 'summit' of a space cliff!"), 
    ('121', "🧮 Count backward from 20 to 0 for a perfect liftoff!"), 
    ('122', "🎭 Mimic the sound of a computer 'beep-boop'!"), 
    ('123', "🥣 Eat a bowl of 'cereal stars'!"), 
    ('124', "🥛 Make a 'black hole' by stirring chocolate into milk!"), 
    ('125', "📦 Create a 'space helmet' out of a paper bag!"), 
    ('126', "🎈 Rub a balloon on your hair to create 'static cosmic energy'!"), 
    ('127', "🥨 Make a 'space station' out of pretzels and marshmallows!"), 
    ('128', "🌠 Make a wish on the first 'star' you see (even if it's a lamp)!"), 
    ('129', "🧳 Pack a 'discovery kit' with a magnifying glass and a notebook!"), 
    ('130', "🎤 Record a message for future civilizations!"), 
    ('131', "🛸 Pretend a hula hoop is the rings of Saturn!"), 
    ('132', "🌌 Put on dark clothes to blend into the night sky!"), 
    ('133', "🧊 Put an ice cube in your drink and call it an 'asteroid fragment'!"), 
    ('134', "📜 Write a 'Peace Treaty' for an alien race!"), 
    ('135', "🚶 Walk backward for 10 steps to simulate a reverse thruster!"), 
    ('136', "🔭 Check the weather report for 'atmospheric conditions'!"), 
    ('137', "🌱 Plant a 'moon seed' (any seed) in a small pot or cup!"), 
    ('138', "🔋 Sit perfectly still for 1 minute to conserve power!"), 
    ('139', "🍪 Bake 'crater cookies' with thumbprint indentations!"), 
    ('140', "💧 Make sure your 'hydration pack' (water bottle) is full!"), 
    ('141', "🛰️ Spin around in a swivel chair like a satellite in orbit!"), 
    ('142', "🧤 Use a pair of tongs to pick up 'hazardous space waste' (trash)!"), 
    ('143', "🛸 Make a 'UFO' out of two paper plates stapled together!"), 
    ('144', "🌠 Draw a picture of a shooting star and give it to a friend!"), 
    ('145', "🥛 Use a straw to make 'craters' in a bowl of yogurt!"), 
    ('146', "🧱 Build a 'launch pad' for your favorite toy!"), 
    ('147', "💤 Practice 'deep space hibernation' by lying still for 3 minutes!"), 
    ('148', "🔦 Use a flashlight to find the 'darkest corner' of your room!"), 
    ('149', "🧼 Clean your 'viewscreen' (glasses or a window)!"), 
    ('150', "🚀 Do 10 lunges to strengthen your 'moon-walking' legs!"), 
    ('151', "📏 Measure how high you can jump in 'Earth gravity'!"), 
    ('152', "🍎 Eat a 'red dwarf' (a cherry or strawberry)!"), 
    ('153', "🛸 Call a friend and ask them what their 'coordinates' are!"), 
    ('154', "🌌 Draw a map of the stars you can see from your bed!"), 
    ('155', "🧶 Use yarn to create a 'laser grid' in a doorway!"), 
    ('156', "🥛 Drink 'comet juice' (ice water with a lemon slice)!"), 
    ('157', "🚀 Give a 'thumbs up' to the next plane you see flying by!"), 
    ('158', "🧩 Put together 5 pieces of a puzzle with your non-dominant hand!"), 
    ('159', "🛸 Toss a 'moon rock' (balled up sock) into a 'crater' (laundry basket)!"), 
    ('160', "📢 Announce 'T-minus 10 minutes to snack time'!"), 
    ('161', "🌑 Wear something completely black today!"), 
    ('162', "🧘 Balance on one leg for 15 seconds like a tripod lander!"), 
    ('163', "🧴 Apply 'sunshield' (lotion) to your arms!"), 
    ('164', "🛸 Make a 'flying saucer' sound with your mouth!"), 
    ('165', "🌌 Stare at a dark piece of paper and 'see' the stars!"), 
    ('166', "🛰️ 'Orbit' around your kitchen island or table 5 times!"), 
    ('167', "🔋 Check all the 'energy cells' (light switches) in your house!"), 
    ('168', "🧸 Tell your plushie a story about a trip to Jupiter!"), 
    ('169', "🧼 Scrub your 'flight deck' (fingernails)!"), 
    ('170', "📦 Turn a shoebox into a 'specimen container'!"), 
    ('171', "🥨 Eat some 'crunchy moon dust' (crackers)!"), 
    ('172', "🔭 Look up a picture of the Pillars of Creation!"), 
    ('173', "🛸 Pretend you're being beamed up while standing under a lamp!"), 
    ('174', "📝 Write your name using only dots (like stars)!"), 
    ('175', "🚪 Check that all 'cargo bay doors' (cabinets) are closed!"), 
    ('176', "🥛 Make 'galaxy toast' using food coloring in milk!"), 
    ('177', "🚀 Do 3 'rocket launches' (jump as high as you can)!"), 
    ('178', "🎒 Re-organize your 'mission supplies' (backpack)!"), 
    ('179', "💤 Listen to 'brown noise' to simulate the hum of a spacecraft!"), 
    ('180', "🔦 Shine a light through a glass of water to see a 'nebula'!"), 
    ('181', "🧤 Wear two pairs of socks to feel 'moon boots'!"), 
    ('182', "🪐 Draw the rings of Saturn using a crayon or marker!"), 
    ('183', "🧊 Put an ice cube down your back to feel the 'cold of space'!"), 
    ('184', "🔭 Find the North Star in a picture or the sky!"), 
    ('185', "🛸 Use a colander as a 'communication helmet'!"), 
    ('186', "🍪 Eat a 'round planet' cookie!"), 
    ('187', "🔊 Shout 'Blast off!' at the start of your next task!"), 
    ('188', "🧼 Wipe down your 'instrument panel' (keyboard or remote)!"), 
    ('189', "🛰️ Tape a 'sensor' (sticky note) to a wall to monitor the room!"), 
    ('190', "📏 Measure the 'distance' from your bed to the door in footsteps!"), 
    ('191', "🌌 Decorate your 'command center' with one new drawing!"), 
    ('192', "🧱 Build a 'stairway to the stars' with books!"), 
    ('193', "🛸 Use a pot lid as a 'shield' against space debris!"), 
    ('194', "📝 Write a letter to an astronaut and send it (or save it)!"), 
    ('195', "🧘 Stretch your arms out wide like a 'solar array'!"), 
    ('196', "🔋 Close your 'eye shutters' for 60 seconds to rest!"), 
    ('197', "🥛 Drink a glass of 'pulsar punch' (fruit juice)!"), 
    ('198', "🚀 Do 5 'zero-g' pushups (on your knees)!"), 
    ('199', "🛸 Pretend your bed is a 'stasis pod'!"), 
    ('200', "🌌 Paint a 'galaxy' on a piece of cardboard!"), 
    ('201', "🧼 Wash your 'specimen collection' (your favorite plastic toys)!"), 
    ('202', "📦 Use a toilet paper roll to make a 'rocket booster'!"), 
    ('203', "🥨 Use pretzel sticks to build a 'star' shape!"), 
    ('204', "🔭 Research what a 'Black Hole' actually is!"), 
    ('205', "🛸 Make a 'whirring' sound while you walk!"), 
    ('206', "📝 List 5 things you'd miss about Earth if you lived on Mars!"), 
    ('207', "🧳 Pack a 'lunar lunch' to eat later!"), 
    ('208', "🔋 Give yourself a 'reboot' by splashing water on your face!"), 
    ('209', "🥛 Drink 'neutron star' water (extra cold!)!"), 
    ('210', "🚀 Practice your 'landing' by jumping off a low step safely!"), 
    ('211', "🛸 Use a blanket as a 'solar sail' and run with it!"), 
    ('212', "🌌 Tell a 'space joke' to someone!"), 
    ('213', "🧼 Polish your 'helmet' (mirror) until it shines!"), 
    ('214', "📦 Hide inside a box and pretend you're in a 'cargo hold'!"), 
    ('215', "🥨 Eat 5 'asteroid bits' (nuts or seeds)!"), 
    ('216', "🔭 Find a constellation app and look at the sky!"), 
    ('217', "🛸 Spin a hula hoop on your arm like Saturn's rings!"), 
    ('218', "📝 Write a poem about the 'Man in the Moon'!"), 
    ('219', "🧘 Do a 'supernova' stretch (start small, then jump wide)!"), 
    ('220', "🔋 Sit in the 'recharging station' (your favorite chair)!"), 
    ('221', "🥛 Drink a glass of 'supernova soda' (sparkling water)!"), 
    ('222', "🚀 Do a 'lunar lap' around your house!"), 
    ('223', "🛸 Wear your clothes backward for 'opposite-day on Venus'!"), 
    ('224', "🌌 Create a 'galaxy jar' with water, glitter, and cotton balls!"), 
    ('225', "🧼 Scrub the 'landing gear' (your feet) in the shower!"), 
    ('226', "📦 Make a 'periscope' to look around corners!"), 
    ('227', "🥨 Eat 'space sticks' (carrot sticks)!"), 
    ('228', "🔭 Spot a 'satellite' (any moving light in the sky)!"), 
    ('229', "🛸 Imagine you're floating and move your arms slowly!"), 
    ('230', "📝 Write down one 'Mission Goal' for tomorrow!") 
    """)
def init_default_encouragments(cur):
    """Create default encouragements"""
    cur.execute("""
    INSERT INTO encouragements (message)
    VALUES 
    ("is sending you rocket fuel! 🚀✨"),
    ("is refueling your tank with cosmic energy! ⭐💫"),
    ("thinks you're doing stellar! 🌟🌙"),
    ("is beaming positive vibes your way! 🛸💖"),
    ("says you're out of this world! 🌍🪐"),
    ("is sending you galaxy-sized hugs! 🌌🤗"),
    ("believes you can reach the stars! ✨🌠"),
    ("is your co-pilot cheering you on! 🛰️💪"),
    ("sent you a care package from Mission Control! 📦💝"),
    ("thinks you shine brighter than a supernova! 💫⭐"),
    ("is sending you a cosmic handshake! 🤝🪐"),
    ("is calculating a perfect trajectory for you! 🛰️📈"),
    ("thinks you’re the brightest star in the cluster! ✨💎"),
    ("is fueling your boosters for a major breakthrough! 🚀🔥"),
    ("says your potential is as infinite as the void! 🌌♾️"),
    ("is sending a pulsar pulse of positivity! 💓📡"),
    ("believes you’re ready for deep-space exploration! 🧑‍🚀🧭"),
    ("is clearing a path through the asteroid belt for you! ☄️🛡️"),
    ("thinks you have the focus of a laser beam! 🔦🎯"),
    ("is cheering from the observation deck! 🏟️🔭"),
    ("says you’ve reached escape velocity! 🚀💨"),
    ("is tracking your glowing success from Earth! 🌍📡"),
    ("thinks you’re a total supernova of talent! 💥🌟"),
    ("is sending intergalactic high-fives! 🖐️👽"),
    ("says your orbit is looking stable and strong! 🔄💪"),
    ("is beaming up a supply drop of motivation! 📦⚡"),
    ("thinks you’re the MVP of the Milky Way! 🏆🌌"),
    ("is watching your star rise in the sky! 📈🌠"),
    ("says you’re a pioneer of the final frontier! 🚩🌑"),
    ("is refueling your spirit with liquid starlight! 🧪✨"),
    ("thinks you’re a cosmic phenomenon! 🪐😲"),
    ("is sending cosmic rays of confidence your way! ☀️⚡"),
    ("says you’re the commander of your own destiny! 🧑‍✈️🛰️"),
    ("is celebrating your successful docking maneuver! ⚓🚀"),
    ("thinks your ideas are revolutionary like a planet! 🔄💡"),
    ("is sending a meteor shower of luck! ☄️🍀"),
    ("says you’re shining through the dark matter! 🖤✨"),
    ("is calibrating your sensors for total success! ⚙️📡"),
    ("thinks you’re an absolute legend of the cosmos! 📜🌌"),
    ("is sending a gravity assist to speed you up! 🪐💨"),
    ("says you’re outshining the midday sun! ☀️😎"),
    ("is keeping your life-support systems at 100%! 🔋❤️"),
    ("thinks you’re a master of the universe! 👑🌌"),
    ("is sending a warp-speed wink your way! 😉🚀"),
    ("says your progress is a giant leap for mankind! 👣🌑"),
    ("is cheering for your mission’s success! 📣🚩"),
    ("thinks you’re a brilliant spark in the dark! ⚡🌑"),
    ("is sending a signal through the space-time continuum! ⏳🌀"),
    ("says you’re a force of nature—and space! 🌪️🪐"),
    ("is making sure your heat shield is holding strong! 🛡️🔥"),
    ("thinks you’re the most curious explorer in the fleet! 🕵️‍♂️🛰️"),
    ("is sending a galaxy-sized hug! 🌌🤗"),
    ("says your light takes 0 seconds to reach our hearts! ❤️✨"),
    ("is giving you a standing ovation from Mission Control! 👏🏛️"),
    ("thinks you’re a diamond in the cosmic dust! 💎☁️"),
    ("is sending a flare of encouragement! 🎇📢"),
    ("says you’re navigating the nebula like a pro! ☁️🧭"),
    ("is beaming over some extra rocket fuel! ⛽🚀"),
    ("thinks you’re the North Star of the team! 🧭⭐"),
    ("is shouting your name across the solar system! 🗣️☀️"),
    ("says you’ve got the right stuff! ✔️🛰️"),
    ("is sending a constellation of compliments! 🌌💬"),
    ("thinks your energy is more powerful than a quasar! ⚡🌀"),
    ("is tracking your trajectory to greatness! 📈🪐"),
    ("says you’re the hero of this space odyssey! 🦸‍♂️🚀"),
    ("is sending a gentle solar wind to push you forward! 🌬️☀️"),
    ("thinks you’re a celestial masterpiece! 🎨✨"),
    ("is making sure your comms are loud and clear! 🎙️📡"),
    ("says you’re a shooting star that never fades! 🌠⏳"),
    ("is sending a binary code for 'You Rock'! 01011 🤘"),
    ("thinks you’re the most luminous object in the sky! 💡🌌"),
    ("is preparing a hero’s welcome for your return! 🎊🛬"),
    ("says your drive is stronger than a rocket engine! ⚙️💪"),
    ("is sending a ripple of joy through the galaxy! 🌊💖"),
    ("thinks you’re the captain of cool! 😎🧑‍✈️"),
    ("is watching your mission with total awe! 🤩🛰️"),
    ("says you’re a beacon of light in the deep void! 🚨🌑"),
    ("is sending a cargo ship full of smiles! 🚢😊"),
    ("thinks you’re a total trailblazer of the stars! 🚜✨"),
    ("is transmitting 100% positive energy! 📶🔋"),
    ("says you’re the key to our cosmic success! 🔑🪐"),
    ("is giving you the green light for liftoff! 🟢🚀"),
    ("thinks you’re a rare moon-gem! 💎🌙"),
    ("is sending a magnetic pull toward your goals! 🧲🎯"),
    ("says your future is brighter than a binary star! ☀️☀️"),
    ("is keeping the stardust out of your eyes! 🧹✨"),
    ("thinks you’re an unstoppable force of gravity! 🌍⬇️"),
    ("is sending a secret message in the stars! 🤫🌌"),
    ("says you’re the architect of the future! 🏗️🪐"),
    ("is cheering as you break the sound barrier! 🔊💥"),
    ("thinks you’re a stellar individual! 🌟👤"),
    ("is sending a cloud of comfort from the nebula! ☁️🛋️"),
    ("says you’re the sun in our solar system! ☀️🏠"),
    ("is giving you a 10/10 on your landing! 🔟🛬"),
    ("thinks you’re a pioneer of possibilities! 🚀🌌"),
    ("is sending a warm glow from the corona! ☀️🔥"),
    ("says your potential is light-years ahead! 🏃‍♂️💨"),
    ("is keeping an eye on your cosmic compass! 🧭✨"),
    ("thinks you’re a gravity-defying genius! 🧠🆙"),
    ("is sending a meteor-sized dose of bravery! ☄️🛡️"),
    ("says you’re the pulse of the space station! 💓🛰️"),
    ("is beaming up some extra-strength coffee! ☕🚀"),
    ("thinks you’re a cosmic treasure! 🏴‍☠️🌌"),
    ("is sending a holographic high-five! 👤✋"),
    ("says you’re the navigator of your own nebula! 🧭☁️"),
    ("is keeping your oxygen levels high and steady! 🫁💨"),
    ("thinks you’re a star-born success! 👶⭐"),
    ("is sending a wave from the edge of the universe! 👋🌌"),
    ("says you’re a cosmic rockstar! 🎸🪐"),
    ("is clearing your landing pad of all worries! 🧹🚩"),
    ("thinks you’re the most brilliant spark in the dark! ⚡🌚"),
    ("is sending a satellite signal of support! 📡💖"),
    ("says you’re a marvel of the modern age! 🤖🌌"),
    ("is celebrating your interstellar achievements! 🎊🎖️"),
    ("thinks your spirit is as vast as the cosmos! 🌌🕊️"),
    ("is sending a moon-bounce of happiness! 🌕🆙"),
    ("says you’re the brightest object in our orbit! ☀️🛰️"),
    ("is keeping the space-time continuum safe for you! ⏳🪐"),
    ("thinks you’re an absolute sun-beam! ☀️😊"),
    ("is sending a solar flare of friendship! 🔥🤝"),
    ("says you’re the discovery of the century! 🔎🌟"),
    ("is keeping your thrusters in tip-top shape! 🔧🚀"),
    ("thinks you’re a giant among planets! 🪐🔝"),
    ("is sending a galaxy-sized thank you! 🌌🙏"),
    ("says you’re the light at the end of the wormhole! 🌀💡"),
    ("is cheering for your lunar achievements! 🌕🏆"),
    ("thinks you’re a visionary of the void! 👁️🌌"),
    ("is sending a rocket-powered hug! 🚀🤗"),
    ("says you’re a master of planetary motion! 🔄🪐"),
    ("is keeping your mission log full of wins! 📝✅"),
    ("thinks you’re a celestial superstar! 🌟🎭"),
    ("is sending a ray of hope from the sun! ☀️🌈"),
    ("says you’re the heartbeat of our crew! 💓🧑‍🚀"),
    ("is watching your star shine from afar! 🔭⭐"),
    ("thinks you’re a comet of creativity! ☄️🎨"),
    ("is sending a signal of pure pride! 📡😌"),
    ("says you’re a universe of talent yourself! 🌌🧠"),
    ("is keeping the solar flares away from you! 🛡️🔥"),
    ("thinks you’re a masterpiece of the Milky Way! 🌌🖼️"),
    ("is sending a cosmic cheer! 📣✨"),
    ("says you’re the pilot of your own dreams! 🧑‍✈️💭"),
    ("is making sure your stardust stays sparkly! 🧹✨"),
    ("thinks you’re an astronomical success! 📈🌌"),
    ("is sending a moon-pie of motivation! 🥧🌙"),
    ("says you’re the glue holding the galaxy together! 🧪🌌"),
    ("is watching your progress with a telescope! 🔭👀"),
    ("thinks you’re a wonder of the world—and space! 🌍🛸"),
    ("is sending a deep-space transmission of love! 📡❤️"),
    ("says you’re the captain of this mission! 🧑‍✈️🚩"),
    ("is keeping the aliens away so you can focus! 👽🚫"),
    ("thinks you’re a celestial treasure! 💎🪐"),
    ("is sending a burst of gamma-ray goodness! 💥🌈"),
    ("says you’re the brightest star in the night! 🌟🌃"),
    ("is keeping your internal clock on stardate! 🕰️🌌"),
    ("thinks you’re a pioneer of the future! 🚀📅"),
    ("is sending a cosmic wink! 😉✨"),
    ("says you’re the king/queen of the cosmos! 👑🌌"),
    ("is keeping the void filled with your laughter! 😂🌌"),
    ("thinks you’re a supernova of kindness! 💥❤️"),
    ("is sending a warp-drive boost! 🚀⚡"),
    ("says you’re the star-chart of our lives! 🗺️⭐"),
    ("is keeping your space-suit shiny and clean! 🧼🧑‍🚀"),
    ("thinks you’re a marvel of the multiverse! 🌀😲"),
    ("is sending a pulse of pure potential! 💓📈"),
    ("says you’re the explorer we’ve been waiting for! 🧑‍🚀🔭"),
    ("is keeping your orbit perfectly circular! 🔄⭕"),
    ("thinks you’re a legend in the making! 📜✨"),
    ("is sending a galaxy of good vibes! 🌌✨"),
    ("says you’re the sun-spot on our day! ☀️😊"),
    ("is keeping the dark matter at bay! 🛡️🖤"),
    ("thinks you’re a celestial high-achiever! 🥇🪐"),
    ("is sending a meteor shower of magic! ☄️✨"),
    ("says you’re the star of the show! 🌟🎭"),
    ("is keeping your mission on the right track! 🗺️🚀"),
    ("thinks you’re a giant leap ahead! 👣🆙"),
    ("is sending a supernova-sized salute! 🫡💥"),
    ("says you’re the commander of the clouds! ☁️🧑‍✈️"),
    ("is keeping your solar panels pointed at the light! ☀️🔋"),
    ("thinks you’re an intergalactic inspiration! 🌌💡"),
    ("is sending a shuttle-load of support! 🚀🤝"),
    ("says you’re the guardian of the galaxy! 🛡️🌌"),
    ("is keeping your starlight burning bright! 🔥⭐"),
    ("thinks you’re a cosmic creator! 🎨🪐"),
    ("is sending a radio wave of relief! 📡😌"),
    ("says you’re the explorer of the unknown! 🗺️❓"),
    ("is keeping your mission clock ticking! ⏱️🚀"),
    ("thinks you’re a star-dusted darling! ✨💖"),
    ("is sending a gravity-defying grin! 😁🌍"),
    ("says you’re the anchor in our asteroid belt! ⚓☄️"),
    ("is keeping your trajectory toward the top! 📈🔝"),
    ("thinks you’re a celestial celebratee! 🎊🌟"),
    ("is sending a wormhole to your happy place! 🌀🏠"),
    ("says you’re the pilot of our hearts! 🧑‍✈️❤️"),
    ("is keeping your energy levels at maximum! 🔋⚡"),
    ("thinks you’re a shooting star of success! 🌠🏆"),
    ("is sending a moon-lit message of peace! 🌙🕊️"),
    ("says you’re the star-lord of the crew! 👑⭐"),
    ("is keeping your flight path clear and bright! 🛣️✨"),
    ("thinks you’re an astronomical amazing person! 😲🌌"),
    ("is sending a solar flare of fun! 🔥🥳"),
    ("says you’re the center of our universe! ☀️🌀"),
    ("is keeping your cosmic spirits high! 🌌🆙"),
    ("thinks you’re the best thing since the Big Bang! 💥📈"),
    ("is sending a final transmission: YOU ARE AWESOME! 📡🙌")
    """)
def init_default_space_facts(cur):
    """Create default space facts"""
    cur.execute("""
    INSERT INTO space_facts (fact)
    VALUES 
    ('A day on Venus is longer than a year on Venus.'),
    ('There are more trees on Earth than stars in the Milky Way.'),
    ('Neutron stars can spin at a rate of 600 rotations per second.'),
    ('The largest volcano in the solar system is on Mars.'),
    ('Space is completely silent; there is no atmosphere to carry sound.'),
    ('A teaspoon of neutron star would weigh about 6 billion tons on Earth.'),
    ('The footprints left by astronauts on the Moon will remain for millions of years.'),
    ('Saturn is the least dense planet in our solar system; it could float in water.'),
    ('One million Earths could fit inside the Sun.'),
    ('The Hubble Space Telescope has helped discover that the universe is expanding.')
    ("A day on Venus is longer than its year! It takes 243 Earth days to rotate once."),
    ("Neutron stars can spin at 600 rotations per second!"),
    ("One teaspoon of a neutron star would weigh 6 billion tons!"),
    ("The Sun accounts for 99.86% of the mass in our solar system."),
    ("There are more stars in the universe than grains of sand on Earth!"),
    ("Saturn's rings are only about 30 feet thick!"),
    ("A year on Mercury is just 88 Earth days long."),
    ("The footprints on the Moon will be there for 100 million years."),
    ("The International Space Station orbits Earth every 90 minutes!"),
    ("Jupiter's Great Red Spot is a storm that's been raging for over 300 years!"),
    ("The coldest place in the universe is the Boomerang Nebula at -272°C!"),
    ("There's a planet made entirely of diamonds called 55 Cancri e."),
    ("The Milky Way galaxy is on a collision course with Andromeda in 4 billion years."),
    ("You can fit all the planets in our solar system between Earth and the Moon!"),
    ("The Sun loses 4 million tons of mass every second due to nuclear fusion."),
    ("Space is completely silent because there's no atmosphere to carry sound."),
    ("A full NASA spacesuit costs about $12 million dollars!"),
    ("The largest known star, UY Scuti, could fit 5 billion Suns inside it!"),
    ("On Mars, the sunset appears blue instead of red/orange."),
    ("There are more than 100 billion galaxies in the observable universe."),
    ("The hottest planet in our solar system is Venus, not Mercury!"),
    ("Astronauts grow about 2 inches taller in space due to lack of gravity."),
    ("One million Earths could fit inside the Sun!"),
    ("The Moon is moving away from Earth at about 3.8 cm per year."),
    ("A year on Pluto is 248 Earth years long!"),
    ("The Great Wall of China is NOT visible from space with the naked eye."),
    ("There's a water reservoir in space that holds 140 trillion times the water in Earth's oceans!"),
    ("Venus rotates backwards compared to most planets in our solar system."),
    ("The temperature in space can range from -270°C to millions of degrees!"),
    ("Halley's Comet won't be visible from Earth again until 2061."),
    ("There are volcanoes on Mars that are larger than Mount Everest!"),
    ("The center of the Milky Way smells like rum and tastes like raspberries!"),
    ("It takes light from the Sun 8 minutes and 20 seconds to reach Earth."),
    ("There's a planet where it rains glass sideways - HD 189733b!"),
    ("Black holes aren't actually holes - they're incredibly dense objects!"),
    ("Saturn could float in water because it's less dense!"),
    ("The largest volcano in our solar system is on Mars - Olympus Mons!"),
    ("Uranus rotates on its side, likely from a massive ancient collision."),
    ("There are more trees on Earth than stars in the Milky Way!"),
    ("The Parker Solar Probe is the fastest human-made object at 430,000 mph!"),
    ("Europa, Jupiter's moon, may have twice as much water as Earth!"),
    ("A spacesuit takes 45 minutes to put on properly."),
    ("The longest a person has lived in space continuously is 437 days!"),
    ("There's a massive canyon on Mars that's 10 times longer than the Grand Canyon."),
    ("The atmosphere on Venus is so thick it would crush you instantly!"),
    ("Astronauts can't burp in space - there's no gravity to separate gas from liquid!"),
    ("The International Space Station travels at 17,500 mph!"),
    ("Mars has the largest dust storms in the solar system - lasting for months!"),
    ("The universe is expanding faster than the speed of light!"),
    ("There's enough gold in Earth's core to coat the entire surface 1.5 feet deep!"),
    ("Io, a moon of Jupiter, is the most volcanically active body in the solar system."),
    ("A year on Neptune is 165 Earth years!"),
    ("The Andromeda Galaxy is heading towards us at 250,000 mph!"),
    ("Space smells like burnt steak and hot metal according to astronauts!"),
    ("Titan, Saturn's moon, has liquid methane lakes and rivers!"),
    ("The coldest temperature ever recorded in space was in the Boomerang Nebula."),
    ("Galaxies can collide and merge over millions of years."),
    ("The first meal eaten in space was applesauce!"),
    ("There are rogue planets floating in space not orbiting any star."),
    ("The asteroid belt between Mars and Jupiter contains millions of asteroids!"),
    ("Ganymede, Jupiter's largest moon, is bigger than Mercury!"),
    ("White dwarfs are so dense that a teaspoon would weigh as much as an elephant!"),
    ("The farthest human-made object is Voyager 1, over 14 billion miles away!"),
    ("Mars' Valles Marineris canyon is 4 times deeper than the Grand Canyon!"),
    ("There are storms on Jupiter that are larger than Earth!"),
    ("The Moon has moonquakes, just like Earth has earthquakes."),
    ("Comets are often called 'dirty snowballs' because they're made of ice and dust."),
    ("The Oort Cloud surrounds our solar system with trillions of icy objects!"),
    ("Neptune's winds can reach speeds of 1,200 mph - the fastest in the solar system!"),
    ("The Sun will eventually become a red giant and engulf Mercury, Venus, and possibly Earth."),
    ("Pluto was discovered in 1930 and demoted from planet status in 2006."),
    ("Saturn's moon Enceladus shoots geysers of water into space!"),
    ("The Kuiper Belt is home to thousands of icy worlds beyond Neptune."),
    ("Mars has a day length very similar to Earth - about 24 hours and 37 minutes!"),
    ("The first animal in space was a dog named Laika in 1957."),
    ("Jupiter protects Earth by deflecting many asteroids with its massive gravity!"),
    ("The speed of light is 186,282 miles per second!"),
    ("Astronauts lose bone density in space at a rate of 1% per month."),
    ("The Hubble Space Telescope has taken over 1.5 million observations!"),
    ("Betelgeuse could explode into a supernova at any time - and it might already have!"),
    ("The North Star (Polaris) won't always be the North Star due to Earth's wobble."),
    ("Mars appears red because its surface is covered in iron oxide (rust)!"),
    ("The largest known structure in the universe is the Hercules-Corona Borealis Great Wall."),
    ("Space radiation would give you a lethal dose without a spacesuit in minutes!"),
    ("The Sun is 4.6 billion years old and halfway through its life!"),
    ("There are brown dwarfs - objects too big to be planets but too small to be stars."),
    ("Olympus Mons on Mars is 16 miles high - 3 times taller than Mount Everest!"),
    ("The universe is estimated to be 13.8 billion years old."),
    ("Pulsars are rapidly spinning neutron stars that emit beams of radiation."),
    ("The first spacewalk was performed by Soviet cosmonaut Alexei Leonov in 1965."),
    ("Jupiter's moon Callisto is one of the most heavily cratered objects in the solar system!"),
    ("Some exoplanets orbit their stars in just a few hours!"),
    ("The Drake Equation estimates how many alien civilizations might exist."),
    ("Red giants can be 100 times larger than the Sun!"),
    ("The Wow! Signal from 1977 remains one of the strongest candidate signals for alien life."),
    ("Astronauts see 16 sunrises and sunsets every day on the ISS!"),
    ("The planet HD 189733b has winds of 5,400 mph and rains molten glass!"),
    ("Meteor showers happen when Earth passes through debris left by comets."),
    ("The Voyager Golden Records contain sounds and images representing Earth.")
    """)
def init_shop_items(cur):
    """Populate shop items table using global SHOP_ITEMS"""
    for item_id, item in SHOP_ITEMS.items():
        cur.execute("""
        INSERT INTO shop_items (item_id, name, description, price, emoji)
        VALUES (%s, %s, %s, %s, %s) ON CONFLICT (item_id) DO NOTHING
        """, (item['id'], item['name'], item['description'], item['price'], item['emoji']))

def init_ship_upgrades(cur):
    """Populate ship upgrades table using global SHIP_UPGRADES"""
    for upgrade_type, upgrade in SHIP_UPGRADES.items():
        cur.execute("""
        INSERT INTO ship_upgrades (upgrade_id, name, emoji, base_cost)
        VALUES (%s, %s, %s, %s) ON CONFLICT (upgrade_id) DO NOTHING
        """, (upgrade['upgrade_id'], upgrade['name'], upgrade['emoji'], upgrade['base_cost']))
def init_default_achievements(cur):
    """Create default space-themed achievements"""
    achievements = [
        # Mission achievements
        ("first_mission", "First Mission", "Complete your first space mission", "🎯", "explorer", "missions_completed", 1, 5, False, get_image_path(35,"Astronaut")),
        ("mission_specialist", "Mission Specialist", "Complete 25 missions", "🛸", "explorer", "missions_completed", 25, 50, False, get_image_path(36,"Astronaut")),
        ("veteran_pilot", "Veteran Pilot", "Complete 100 missions", "👨‍🚀", "explorer", "missions_completed", 100, 200, False, get_image_path(37,"Astronaut")),
        ("mission_master", "Mission Master", "Complete 250 missions", "🏅", "explorer", "missions_completed", 250, 500, False, get_image_path(41,"Astronaut")),

        # Encouragement achievements
        ("first_contact", "First Contact", "Send your first encouragement", "📡", "social", "encouragements_given", 1, 5, False, get_image_path(1, "Alien")),
        ("ambassador", "Ambassador", "Encourage 20 crew members", "🤝", "social", "encouragements_given", 20, 40, False, get_image_path(2, "Alien")),
        ("galactic_friend", "Galactic Friend", "Encourage 50 crew members", "💫", "social", "encouragements_given", 50, 100, False, get_image_path(3, "Alien")),
        ("beloved_crew", "Beloved Crew", "Receive 15 encouragements", "⭐", "social", "encouragements_received", 15, 30, False, get_image_path(4, "Alien")),

        # Plushie achievements
        ("first_companion", "First Companion", "Register your first plushie", "🧸", "collector", "plushies_registered", 1, 5, False, get_image_path(2,"Astronaut")),
        ("plushie_fleet", "Plushie Fleet", "Register 10 plushies", "🎪", "collector", "plushies_registered", 10, 50, False, get_image_path(8, "Astronaut")),
        ("curator", "Curator", "Register 25 plushies", "🛍️", "collector", "plushies_registered", 25, 100, False, get_image_path(10, "Astronaut")),
        
        # Knowledge achievements
        ("space_cadet", "Space Cadet", "Learn 10 space facts", "📚", "scholar", "facts_learned", 10, 20, False, get_image_path(12,"Astronaut")),
        ("astronomer", "Astronomer", "Learn 50 space facts", "🔭", "scholar", "facts_learned", 50, 100, False, get_image_path(19,"Astronaut")),
        ("astrophysicist", "Astrophysicist", "Learn 100 space facts", "👩‍🔬", "scholar", "facts_learned", 100, 200, False, get_image_path(60, "Astronaut")),
        
        # Exploration achievements
        ("planet_hunter", "Planet Hunter", "Discover 10 planets", "🪐", "explorer", "planets_discovered", 10, 20, False, get_image_path(63,"Astronaut")),
        ("spacewalker", "Spacewalker", "Take 15 spacewalks", "🧑‍🚀", "explorer", "spacewalks_taken", 15, 30, False, get_image_path(66,"Astronaut")),
        
        # Economy achievements
        ("first_purchase", "First Purchase", "Buy your first item", "💰", "merchant", "items_purchased", 1, 5, False, get_image_path(80,"Astronaut")),
        ("savvy_shopper", "Savvy Shopper", "Purchase 25 items", "🛍️", "merchant", "items_purchased", 25, 50, False, get_image_path(82, "Astronaut")),
        ("collector_supreme", "Collector Supreme", "Own 50+ items in inventory", "📦", "merchant", "total_items_owned", 50, 100, False, get_image_path(83, "Astronaut")),
        ("ship_engineer", "Ship Engineer", "Upgrade your ship 10 times", "🔧", "engineer", "ship_upgrades", 10, 75, False, get_image_path(85, "Astronaut")),
        ("master_engineer", "Master Engineer", "Upgrade your ship 25 times", "⚙️", "engineer", "ship_upgrades", 25, 150, False, get_image_path(87, "Astronaut")),
        
        # Hidden achievements
        ("secret_astronaut", "Secret Astronaut", "Mission Control knows your call sign", "🎖️", "hidden", "missions_completed", 500, 1000, True, get_image_path(39,"Astronaut")),
        ("cosmic_legend", "Cosmic Legend", "A true space pioneer", "🌌", "hidden", "encouragements_given", 100, 500, True, get_image_path(42,"Astronaut")),
        ("millionaire", "Space Millionaire", "Accumulate 10,000 credits", "💎", "hidden", "total_credits_earned", 10000, 2000, True, get_image_path(46, "Astronaut")),
    ]
    
    for ach in achievements:
        cur.execute("""INSERT INTO achievements (id, name, description, icon, category, requirement_type, requirement_count, credits, hidden, image_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""", ach)
def init_db():
    """Initialize all database tables (idempotent & safe)"""
    global _db_initialized
    if _db_initialized:
        return
    with DatabasePool.get_conn() as conn:
        conn.autocommit = True
        cur = conn.cursor()
        try:
            # (Keep all your existing CREATE TABLE calls here: plushies, saved_embeds, etc.)
            # Introductions table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS introductions (
                    user_id BIGINT PRIMARY KEY,
                    name TEXT NOT NULL,
                    pronouns TEXT,
                    age TEXT,
                    interests TEXT NOT NULL,
                    about TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Character sheets table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS character_sheets (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    char_name TEXT NOT NULL,
                    species TEXT NOT NULL,
                    appearance TEXT NOT NULL,
                    personality TEXT NOT NULL,
                    backstory TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, char_name)
                )
            """)
            # UPDATED User stats table
            
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
                    total_credits INTEGER DEFAULT 0,
                    salvages_completed INTEGER DEFAULT 0
                )
            """)

            # UPDATED Ships table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ships (
                    user_id BIGINT PRIMARY KEY,
                    name TEXT NOT NULL,
                    ship_class TEXT DEFAULT 'Scout',
                    engine_level INTEGER DEFAULT 1,
                    weapon_level INTEGER DEFAULT 1,
                    shield_level INTEGER DEFAULT 1,
                    health INTEGER DEFAULT 100,
                    max_health INTEGER DEFAULT 100,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Achievements table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS achievements (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    icon TEXT,
                    category TEXT,
                    requirement_type TEXT NOT NULL,
                    requirement_count INTEGER NOT NULL,
                    credits INTEGER DEFAULT 0,
                    hidden BOOLEAN DEFAULT FALSE,
                    image_id TEXT
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_achievements (
                    user_id BIGINT NOT NULL,
                    achievement_id TEXT NOT NULL REFERENCES achievements(id),
                    progress INTEGER DEFAULT 0,
                    unlocked BOOLEAN DEFAULT FALSE,
                    unlocked_at TIMESTAMPTZ,
                    PRIMARY KEY (user_id, achievement_id)
                )
            """)
            
            # Shop items table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS shop_items (
                    item_id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    price INTEGER NOT NULL,
                    emoji TEXT,
                    type TEXT DEFAULT 'consumable',
                    rarity INTEGER DEFAULT 1
                )
            """)
            
            # Ship upgrades table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS ship_upgrades (
                    upgrade_id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    emoji TEXT,
                    base_cost INTEGER NOT NULL
                )
            """)

            # Plushies table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS plushies (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    name TEXT NOT NULL,
                    species TEXT NOT NULL,
                    color TEXT NOT NULL,
                    personality TEXT NOT NULL,
                    description TEXT NOT NULL,
                    image_data BYTEA,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, name)
                )
            """)
            
            # Saved embeds table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS saved_embeds (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    name TEXT NOT NULL,
                    embed_data JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, name)
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
            
            # Missions table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS missions (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL
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
            
            # Encouragements table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS encouragements (
                    id SERIAL PRIMARY KEY,
                    message TEXT NOT NULL
                )
            """)
            
            # Space facts table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS space_facts (
                    id SERIAL PRIMARY KEY,
                    fact TEXT NOT NULL
                )
            """)
            
            # Inventory table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    user_id BIGINT NOT NULL,
                    item_id INTEGER NOT NULL,
                    quantity INTEGER DEFAULT 1,
                    PRIMARY KEY (user_id, item_id)
                )
            """)
            
            # Moderator applications table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS mod_applications (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username TEXT NOT NULL,
                    age TEXT,
                    timezone TEXT,
                    experience TEXT,
                    why_mod TEXT,
                    scenarios TEXT,
                    availability TEXT,
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
            init_ship_upgrades(cur)
        finally:
            cur.close()
    _db_initialized = True
    logger.info("Database initialized")

#Achievement System
class Achievement:
    @staticmethod
    async def check_and_award(user_id:int, stat_type:str, new_value:int, channel:Optional[Any]=None):
        """Check if the user's achievement should be awarded based on their progress."""
        unlocked = []
        with DatabasePool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("Select a.* From achievements a LEFT JOIN user_achievements ua ON a.id = ua.achievement_id AND ua.user_id = %s WHERE a.requirement_type = %s AND (ua.achievement_id IS NULL OR ua.awarded_at IS NULL)", (user_id, stat_type))
                achievements = cur.fetchall()
                for ach in achievements:
                    if new_value >= ach["requirement_count"]:
                        cur.execute("""INSERT INTO user_achievements (user_id, achievement_id, progress, unlocked, unlocked_at)
                                      VALUES (%s, %s, %s, TRUE, NOW())
                                      ON CONFLICT (user_id) DO UPDATE SET unlocked = TRUE, unlocked_at = NOW(), progress = EXCLUDED.progress""",
                                   (user_id, ach['id'], new_value))
                        
                        cur.execute("""INSERT INTO user_stats (user_id, total_credits) VALUES (%s, %s)
                                      ON CONFLICT (user_id) DO UPDATE SET total_credits = user_stats.total_credits + EXCLUDED.total_credits""",
                                   (user_id, ach['credits']))
                        cur.execute("""SELECT * FROM achievements WHERE id = %s""", (ach['id'],))
                        unlocked_ach = cur.fetchone()
                        if not unlocked_ach:
                            continue
                        cur.execute("""INSERT INTO user_stats (user_id, total_credits_earned) VALUES (%s, %s)
                                      ON CONFLICT (user_id) DO UPDATE SET total_credits_earned = user_stats.total_credits_earned + EXCLUDED.total_credits_earned""",
                                   (user_id, ach['credits']))
                        unlocked.append(ach)
                    else:
                        cur.execute("""INSERT INTO user_achievements (user_id, achievement_id) VALUES (%s, %s) ON CONFLICT (user_id, achievement_id) DO NOTHING""", (user_id, ach["id"]))
        if unlocked and channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
            for ach in unlocked:
                await Achievement.send_unlock_notification(user_id, ach, channel)
        if unlocked and stat_type != "total_credits_earned":
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    total_credits = sum(ach["credits"] for ach in unlocked)
                    cur.execute("""INSERT INTO user_stats (user_id, total_credits_earned, total_credits) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET total_credits = user_stats.total_credits + %s""", (user_id, total_credits, total_credits))
                    stats = cur.fetchone()
                    if stats:
                        await Achievement.check_and_award(user_id, "total_credits_earned", stats["total_credits_earned"], channel)
        return unlocked

    @staticmethod
    async def send_unlock_notification(user_id:int, ach:dict, channel:Union[discord.TextChannel, discord.Thread]):
        """Send achievement unlocked notification"""
        user = await channel.guild.fetch_member(user_id)
        embed = discord.Embed(
            title=f"Congratulations {user.display_name}!",
            description=f"You've unlocked the **{ach['name']}** achievement!\n\n{ach['description']}\n\nEarned credits: {ach['credits']}",
            color=discord.Colour.from_str(PALETTE['LB'])
        )
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        embed.add_field(name="Icon:", value=ach["icon"])
        embed.add_field(name="Category:", value=ach["category"].capitalize())
        embed.add_field(name="Requirement Type:", value=ach["requirement_type"])
        embed.add_field(name="Requirement Count:", value=ach["requirement_count"])
        embed.add_field(name="Credits:", value=ach["credits"])
        await channel.send(embed=embed)
        astro_image=get_image_path(ach.get("image_id", 1))
        if astro_image:
            embed.set_image(url=f"attachment://{os.path.basename(astro_image)}")
            with open(astro_image, 'rb') as img_file:
                file = discord.File(img_file, filename=os.path.basename(astro_image))
                await channel.send(file=file, embed=embed)
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
                
                # Also track total credits earned when credits are added
                if stat_name == "total_credits" and amount > 0:
                    cur.execute("""INSERT INTO user_stats (user_id, total_credits_earned) VALUES (%s, %s)
                                   ON CONFLICT (user_id) DO UPDATE SET total_credits_earned = user_stats.total_credits_earned + EXCLUDED.total_credits_earned""",
                               (user_id, amount))
                
                return new_value

# Space Economy System

def calculate_upgrade_cost(current_level: int, base_cost: int) -> int:
    """Calculate the cost of the next ship upgrade based on current level."""
    return base_cost * (current_level + 1)
class ShipManager:
    """Manages personal starship operations."""
    @staticmethod
    def create_ship(user_id: int, name: str) -> bool:
        try:
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""INSERT INTO ships (user_id, name) VALUES (%s, %s)""", (user_id, name))
                    return True
        except Exception as e:
            logger.error(f"Error creating ship: {e}")
            return False
    @staticmethod
    def get_ship(user_id: int) -> Optional[Dict]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT * FROM ships WHERE user_id = %s""", (user_id,))
                ship = cur.fetchone()
                return ship if ship else None
    @staticmethod
    def damage_ship(user_id: int, damage: int) -> Optional[int]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE ships SET health = GREATEST(health - %s, 0) WHERE user_id = %s RETURNING health""", (damage, user_id))
                result = cur.fetchone()
                return result[0] if result else None
    @staticmethod
    def repair_ship(user_id: int, repair_amount: int) -> Optional[int]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE ships SET health = LEAST(health + %s, max_health) WHERE user_id = %s RETURNING health""", (repair_amount, user_id))
                result = cur.fetchone()
                return result[0] if result else None
    @staticmethod
    def upgrade_ship(user_id: int, upgrade_type: str) -> Optional[tuple[str, int, int]]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT s.*, su.base_cost FROM ships s INNER JOIN ship_upgrades su ON s.ship_class = su.name WHERE s.user_id = %s""", (user_id,))
                ship = cur.fetchone()
                if not ship:
                    return None
                if upgrade_type == "engine":
                    current_level = ship["engine_level"]
                    base_cost = ship["engine_base_cost"]
                elif upgrade_type == "weapon":
                    current_level = ship["weapon_level"]
                    base_cost = ship["weapon_base_cost"]
                elif upgrade_type == "shield":
                    current_level = ship["shield_level"]
                    base_cost = ship["shield_base_cost"]
                else:
                    return None
                new_cost = calculate_upgrade_cost(current_level, base_cost)
                cur.execute("""UPDATE ships SET {}_level = {}_level + 1 WHERE user_id = %s RETURNING {}_level""".format(upgrade_type, upgrade_type, upgrade_type), (user_id,))
                new_level = cur.fetchone()[0]
                return upgrade_type.capitalize(), new_cost, new_level
    @staticmethod
    def get_all_ships() -> List[Dict]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT * FROM ships ORDER BY created_at DESC LIMIT 10""")
                return cur.fetchall()

class InventoryManager:
    """Manages user inventory operations."""
    @staticmethod
    def add_item(user_id: int, item_id: int, quantity: int = 1) -> bool:
        try:
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""INSERT INTO inventory (user_id, item_id, quantity) VALUES (%s, %s, %s)
                                   ON CONFLICT (user_id, item_id) DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity""",
                               (user_id, item_id, quantity))
                    return True
        except Exception as e:
            logger.error(f"Error adding item to inventory: {e}")
            return False
    @staticmethod
    def get_inventory(user_id: int) -> List[Dict]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT i.item_id, si.name, si.description, si.emoji, i.quantity
                               FROM inventory i
                               JOIN shop_items si ON i.item_id = si.item_id
                               WHERE i.user_id = %s""", (user_id,))
                return cur.fetchall()
    @staticmethod
    def remove_item(user_id: int, item_id: int, quantity: int = 1) -> bool:
        try:
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""UPDATE inventory SET quantity = GREATEST(quantity - %s, 0) WHERE user_id = %s AND item_id = %s RETURNING quantity""",
                               (quantity, user_id, item_id))
                    result = cur.fetchone()
                    return result[0] > 0 if result else False
        except Exception as e:
            logger.error(f"Error removing item from inventory: {e}")
            return False

# Plushie Management System
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

# Embed Manager
class EmbedManager:
    """Manages saved embed operations."""
    
    @staticmethod
    def save_embed(user_id: int, name: str, embed_data: Dict) -> bool:
        try:
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO saved_embeds (user_id, name, embed_data)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (user_id, name) 
                        DO UPDATE SET embed_data = EXCLUDED.embed_data
                    """, (user_id, name, json.dumps(embed_data)))
            return True
        except Exception as e:
            logger.error(f"Failed to save embed: {e}")
            return False

    @staticmethod
    def get_all_embeds(user_id: int) -> List[Dict]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT name, embed_data FROM saved_embeds 
                    WHERE user_id = %s ORDER BY name
                """, (user_id,))
                return cur.fetchall()
    
    @staticmethod
    def list_all(user_id: int) -> List[str]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT name FROM saved_embeds 
                    WHERE user_id = %s ORDER BY name
                """, (user_id,))
                return [row[0] for row in cur.fetchall()]
    
    @staticmethod
    def get_embed(user_id: int, name: str) -> Optional[Dict]:
        with DatabasePool.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT embed_data FROM saved_embeds 
                    WHERE user_id = %s AND LOWER(name) = LOWER(%s)
                """, (user_id, name))
                result = cur.fetchone()
                return json.loads(result["embed_data"]) if result else None
    @staticmethod
    def delete_embed(user_id: int, name: str) -> bool:
        try:
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM saved_embeds 
                        WHERE user_id = %s AND LOWER(name) = LOWER(%s)
                    """, (user_id, name))
            return True
        except Exception as e:
            logger.error(f"Failed to delete embed: {e}")
            return False
    @staticmethod
    def update_embed(user_id: int, name: str, embed_data: Dict) -> bool:
        try:
            with DatabasePool.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE saved_embeds SET embed_data = %s
                        WHERE user_id = %s AND LOWER(name) = LOWER(%s)
                    """, (json.dumps(embed_data), user_id, name))
            return True
        except Exception as e:
            logger.error(f"Failed to update embed: {e}")
            return False

# Backup Manager
class BackupManager:
    """Manages backup operations."""
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
                            if isinstance(existing_ch, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.ForumChannel)):
                                await existing_ch.edit(name=ch_name, category=new_cat, overwrites=ch_overwrites)
                            else:
                                await existing_ch.edit(name=ch_name, overwrites=ch_overwrites)
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

# Utilities

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
    color_hex = config.get("color", PALETTE.get("SB", "#7395cc"))
    embed = discord.Embed(
        description=config.get("description", ""),
        color=discord.Color(int(color_hex.replace("#", ""), 16))
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
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("⛔ This command can only be used in a server.", ephemeral=True)
            return False
            
        if interaction.user.guild_permissions.administrator:
            return True
        if STAFF_ROLE_ID and discord.utils.get(interaction.user.roles, id=STAFF_ROLE_ID):
            return True
        await interaction.response.send_message("⛔ Staff only.", ephemeral=True)
        return False
    return app_commands.check(predicate)

# bot setup
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
    migrate_db()
    logger.info(f"🚀 Starflight Pilot online as {bot.user}")
    logger.info(f"📋 Registered commands: {[cmd.name for cmd in bot.tree.get_commands()]}")

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Auto-disconnect if bot is alone in voice channel"""
    if bot.user and member.id != bot.user.id:
        return
    
    # If bot left a channel
    if before.channel and not after.channel:
        player = music_players.get(before.channel.guild.id)
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

# Music Player Management
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
        
    async def join(self, channel: discord.VoiceChannel | discord.StageChannel):
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

        try:
            source = discord.FFmpegPCMAudio(
                song.source,
                before_options="-nostdin -loglevel panic",
                options="-vn"
            )
            source = discord.PCMVolumeTransformer(source, volume=self.volume)

            loop = asyncio.get_running_loop()

            if self.voice_client:
                self.voice_client.play(
                    source,
                    after=lambda e: loop.call_soon_threadsafe(
                        asyncio.create_task, self.play_next()
                    )
                )
            else:
                logger.error("No voice client available for playback")
                await self.play_next()
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
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.source.volume = self.volume # type: ignore

# Global Music Players Dictionary
music_players: Dict[int, MusicPlayer] = {}

def get_music_player(guild: discord.Guild) -> MusicPlayer:
    """Get or create a music player for the guild"""
    if guild.id not in music_players:
        music_players[guild.id] = MusicPlayer(guild)
    return music_players[guild.id]

#Modal Classes
class EmbedBuilderModal(discord.ui.Modal, title="Create Embed"):
    embed_title = discord.ui.TextInput(label="Title", required=False)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph)
    image_url = discord.ui.TextInput(label="Image URL", required=False)
    footer = discord.ui.TextInput(label="Subtext", required=False)
    def __init__(self, name: str):
        super().__init__()
        self.name = name
    async def on_submit(self, interaction: discord.Interaction):
        embed_data = {
            "title": self.embed_title.value,
            "description": self.description.value,
            "image": self.image_url.value if self.image_url.value else None,
            "footer": self.footer.value if self.footer.value else None,
            "color": PALETTE["SB"],
            "fields": []
        }
        success = EmbedManager.save_embed(interaction.user.id, self.name, embed_data)
        if success:
            await interaction.response.send_message(f"✅ Embed '{self.name}' saved successfully.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Failed to save embed.", ephemeral=True)

class PlushieModal(discord.ui.Modal, title="Create Plushie"):
    name = discord.ui.TextInput(label="Name", max_length=50)
    species = discord.ui.TextInput(label="Species", max_length=50)
    color = discord.ui.TextInput(label="Color", max_length=30)
    personality = discord.ui.TextInput(label="Personality", style=discord.TextStyle.paragraph, max_length=200)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, max_length=300)
    def __init__(self, image: Optional[bytes] = None):
        super().__init__()
        self.image = image
    async def on_submit(self, interaction: discord.Interaction):
        data = {
            "name": self.name.value,
            "species": self.species.value,
            "color": self.color.value,
            "personality": self.personality.value,
            "description": self.description.value
        }
        if PlushieManager.create(interaction.user.id, data, self.image):
            await interaction.response.send_message("🧸 Plushie registered!", ephemeral=True)
            
            # Track stats and check achievements
            plushie_count = Achievement.increment_stat(interaction.user.id, "plushies_registered")
            channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None
            await Achievement.check_and_award(interaction.user.id, "plushies_registered", plushie_count, channel)
        else:
            await interaction.response.send_message("❌ Failed to register plushie.", ephemeral=True)
class PlushieEditModal(discord.ui.Modal, title="Edit Plushie"):
    species = discord.ui.TextInput(label="Species", required=False)
    color = discord.ui.TextInput(label="Color", required=False)
    personality = discord.ui.TextInput(label="Personality", style=discord.TextStyle.paragraph, required=False)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, required=False)
    def __init__(self, name: str, user_id: int, image: Optional[bytes] = None):
        super().__init__()
        self.name = name
        self.image = image
        self.user_id = user_id

        current = PlushieManager.get_one(user_id, name)
        if not current:
            return

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
        if self.image:
            image = ImageUtil.compress(self.image)        
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
                    await interaction.response.send_message(
                        "🚫 You already have a pending moderator application. Please wait for a response from staff.",
                        ephemeral=True
                    )
                    return
                
                # Save application
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
                    "See application details",
                    self.availability.value,
                    "N/A"
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
        
        # Notify staff in a staff channel
        if interaction.guild:
            staff_channel = discord.utils.get(interaction.guild.channels, name="staff-notifications")
        else:
            staff_channel = None
        if staff_channel and isinstance(staff_channel, discord.TextChannel):
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
class IntroductionModal(discord.ui.Modal, title="Create Introduction"):
    name = discord.ui.TextInput(
        label="Name/Callsign",
        placeholder="What should we call you?",
        max_length=50
    )
    pronouns = discord.ui.TextInput(
        label="Pronouns",
        placeholder="e.g., they/them, she/her, he/him",
        max_length=30,
        required=False
    )
    age = discord.ui.TextInput(
        label="Age",
        placeholder="Optional",
        max_length=3,
        required=False
    )
    interests = discord.ui.TextInput(
        label="Interests & Hobbies",
        placeholder="What do you enjoy? (gaming, art, space, etc.)",
        style=discord.TextStyle.paragraph,
        max_length=300
    )
    about = discord.ui.TextInput(
        label="About You",
        placeholder="Tell us about yourself!",
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self):
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        with DatabasePool.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO introductions (user_id, name, pronouns, age, interests, about)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) 
                    DO UPDATE SET 
                        name = EXCLUDED.name,
                        pronouns = EXCLUDED.pronouns,
                        age = EXCLUDED.age,
                        interests = EXCLUDED.interests,
                        about = EXCLUDED.about,
                        updated_at = NOW()
                """, (
                    interaction.user.id,
                    self.name.value,
                    self.pronouns.value or None,
                    self.age.value or None,
                    self.interests.value,
                    self.about.value
                ))
        
        embed = discord.Embed(
            title="✅ Introduction Saved!",
            description="Your introduction has been created/updated successfully!",
            color=discord.Color.green()
        )
        embed.add_field(
            name="📋 Next Steps",
            value="Use `/introduction_view` to see your introduction, or `/introduction_post` to share it with everyone!",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class CharacterSheetModal(discord.ui.Modal, title="Create Character Sheet"):
    char_name = discord.ui.TextInput(
        label="Character Name",
        placeholder="Your character's name",
        max_length=50
    )
    species = discord.ui.TextInput(
        label="Species/Race",
        placeholder="Human, Alien, Android, etc.",
        max_length=50
    )
    appearance = discord.ui.TextInput(
        label="Appearance",
        placeholder="Describe your character's appearance",
        style=discord.TextStyle.paragraph,
        max_length=300
    )
    personality = discord.ui.TextInput(
        label="Personality",
        placeholder="Describe your character's personality",
        style=discord.TextStyle.paragraph,
        max_length=300
    )
    backstory = discord.ui.TextInput(
        label="Backstory",
        placeholder="Your character's history and background",
        style=discord.TextStyle.paragraph,
        max_length=1000
    )

    def __init__(self, character_name: Optional[str] = None):
        super().__init__()
        self.editing_character = character_name

    async def on_submit(self, interaction: discord.Interaction):
        with DatabasePool.get_conn() as conn:
            with conn.cursor() as cur:
                if self.editing_character:
                    # Update existing character
                    cur.execute("""
                        UPDATE character_sheets 
                        SET species = %s, appearance = %s, personality = %s, 
                            backstory = %s, updated_at = NOW()
                        WHERE user_id = %s AND LOWER(char_name) = LOWER(%s)
                    """, (
                        self.species.value,
                        self.appearance.value,
                        self.personality.value,
                        self.backstory.value,
                        interaction.user.id,
                        self.editing_character
                    ))
                    message = f"✅ Character **{self.editing_character}** updated!"
                else:
                    # Create new character
                    cur.execute("""
                        INSERT INTO character_sheets 
                        (user_id, char_name, species, appearance, personality, backstory)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        interaction.user.id,
                        self.char_name.value,
                        self.species.value,
                        self.appearance.value,
                        self.personality.value,
                        self.backstory.value
                    ))
                    message = f"✅ Character **{self.char_name.value}** created!"
        
        await interaction.response.send_message(message, ephemeral=False)

# Commands
# Achievement Commands
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
    
    total_credits = stats['total_credits'] if stats else 0
    unlocked_count = len(unlocked)
    
    embed = discord.Embed(
        title=f"🏆 {target.display_name}'s Achievements",
        description=f"**Total credits:** {total_credits} 🌟\n**Unlocked:** {unlocked_count} achievements\n",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    
    # Show unlocked achievements
    if unlocked:
        unlocked_text = "\n".join([f"{a['icon']} **{a['name']}** - {a['description']} (+{a['credits']})" for a in unlocked[:5]])
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
            cur.execute("""SELECT user_id, total_credits FROM user_stats 
                          ORDER BY total_credits DESC LIMIT 10""")
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
    
    if not interaction.guild:
        return await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
    
    for i, leader in enumerate(leaders):
        try:
            user = await interaction.guild.fetch_member(leader['user_id'])
            medal = medals[i] if i < 3 else f"{i+1}."
            leaderboard_text += f"{medal} **{user.display_name}** - {leader['total_credits']} credits\n"
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
    embed.add_field(name="🌟 Total credits", value=str(stats['total_credits']), inline=True)
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
            cur.execute("SELECT total_credits FROM user_stats WHERE user_id = %s", (target.id,))
            stats = cur.fetchone()

    balance = stats['total_credits'] if stats else 0

    embed = discord.Embed(
        title=f"💰 {target.display_name}'s Credit Balance",
        description=f"You have **{balance}** credits.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    await interaction.response.send_message(embed=embed)

# Music Commands
@bot.tree.command(name="join")
async def join(interaction: discord.Interaction):
    """Join your voice channel"""
    if not interaction.guild:
        return await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
    if not isinstance(interaction.user, discord.Member) or not interaction.user.voice:
        return await interaction.response.send_message("❌ You need to be in a voice channel!", ephemeral=True)
    
    channel = interaction.user.voice.channel
    if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        return await interaction.response.send_message("❌ You must be in a voice or stage channel!", ephemeral=True)
    
    player = get_music_player(interaction.guild)
    await player.join(channel)
    await interaction.response.send_message(f"🎵 Joined {channel.mention}")

@bot.tree.command(name="leave")
async def leave(interaction: discord.Interaction):
    """Leave the voice channel"""
    if not interaction.guild:
        return await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
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
    
    if not interaction.guild:
        return await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
    if not isinstance(interaction.user, discord.Member) or not interaction.user.voice:
        return await interaction.response.send_message("❌ You need to be in a voice channel!", ephemeral=True)
    
    await interaction.response.defer()
    
    player = get_music_player(interaction.guild)
    
    # Join voice channel if not connected
    if not player.voice_client:
        channel = interaction.user.voice.channel
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            return await interaction.followup.send("❌ You must be in a voice or stage channel!")
        await player.join(channel)
    
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
            temp_path = Path(temp_dir) / f"{interaction.id}_{file.filename}"
            
            # Download the file
            await file.save(temp_path)
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                return await interaction.followup.send("❌ Failed to save audio file.")

            song = Song(
                source=str(temp_path),
                title=file.filename,
                requester=interaction.user,
                is_file=True
            )
        else:
            # Use URL directly
            if not url:
                return await interaction.followup.send("❌ URL cannot be empty!")
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
    if not interaction.guild:
        return await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
    player = get_music_player(interaction.guild)
    if not player.voice_client or not player.voice_client.is_playing():
        return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)
    
    player.pause()
    await interaction.response.send_message("⏸️ Paused playback")

@bot.tree.command(name="resume")
async def resume(interaction: discord.Interaction):
    """Resume the current song"""
    if not interaction.guild:
        return await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
    player = get_music_player(interaction.guild)
    if not player.voice_client or not player.voice_client.is_paused():
        return await interaction.response.send_message("❌ Nothing is paused!", ephemeral=True)
    
    player.resume()
    await interaction.response.send_message("▶️ Resumed playback")

@bot.tree.command(name="stop")
async def stop(interaction: discord.Interaction):
    """Stop playback and clear the queue"""
    if not interaction.guild:
        return await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
    player = get_music_player(interaction.guild)
    if not player.voice_client:
        return await interaction.response.send_message("❌ Not playing anything!", ephemeral=True)
    
    player.queue.clear()
    player.stop()
    await interaction.response.send_message("⏹️ Stopped playback and cleared queue")

@bot.tree.command(name="skip")
async def skip(interaction: discord.Interaction):
    """Skip the current song"""
    if not interaction.guild:
        return await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
    player = get_music_player(interaction.guild)
    if not player.voice_client or not player.voice_client.is_playing():
        return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)
    
    player.skip()
    await interaction.response.send_message("⏭️ Skipped to next song")

@bot.tree.command(name="queue")
async def queue(interaction: discord.Interaction):
    """View the current music queue"""
    if not interaction.guild:
        return await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
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
    if not interaction.guild:
        return await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
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
    
    if not interaction.guild:
        return await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
    player = get_music_player(interaction.guild)
    player.set_volume(level / 100)
    await interaction.response.send_message(f"🔊 Volume set to {level}%")

@bot.tree.command(name="loop")
async def loop(interaction: discord.Interaction):
    """Toggle loop mode for current song"""
    if not interaction.guild:
        return await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
    player = get_music_player(interaction.guild)
    player.loop = not player.loop
    
    status = "enabled" if player.loop else "disabled"
    emoji = "🔁" if player.loop else "➡️"
    await interaction.response.send_message(f"{emoji} Loop mode {status}")

# Embed Commands
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
    embed_data = EmbedManager.get_embed(interaction.user.id, name)
    if not embed_data:
        return await interaction.response.send_message("❌ Embed not found.", ephemeral=True)
    
    target = channel or interaction.channel
    if not isinstance(target, discord.TextChannel):
        return await interaction.response.send_message("❌ Can only post to text channels.", ephemeral=True)
    
    await target.send(embed=build_announcement_embed("header"))
    await target.send(embed=build_embed_from_data(embed_data))
    await target.send(embed=build_announcement_embed("footer"))
    await interaction.response.send_message("✅ Posted with header and footer.", ephemeral=True)

@bot.tree.command(name="embed_list")
@is_staff()
async def embed_list(interaction: discord.Interaction):
    """List all saved embed templates"""
    embeds = EmbedManager.list_all(interaction.user.id)
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
    if EmbedManager.delete_embed(interaction.user.id, name):
        await interaction.response.send_message(f"✅ Deleted embed **{name}**.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Embed not found.", ephemeral=True)
@bot.tree.command(name="embed_edit")
@is_staff()
async def embed_edit(interaction: discord.Interaction, name: str):
    """Edit an embed template"""
    await interaction.response.send_modal(EmbedBuilderModal(name))

# Server Backup Commands
@bot.tree.command(name="backup_ship")
@is_staff()
async def backup_ship(interaction: discord.Interaction):
    """Create a backup and save it to the database"""
    await interaction.response.defer(ephemeral=True)
    if not interaction.guild:
        return await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
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
    if not interaction.guild:
        return await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
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

@bot.tree.command(name="export_backup")
@is_staff()
async def export_backup(interaction: discord.Interaction):
    """Export the latest backup to a JSON file"""
    await interaction.response.defer(ephemeral=True)
    if not interaction.guild:
        return await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
    data = BackupManager.load_from_db(interaction.guild.id)
    if not data:
        return await interaction.followup.send("⚠️ No ship backup found.", ephemeral=True)
    json_data_bytes = json.dumps(data, indent=4).encode('utf-8')
    file = discord.File(fp=io.BytesIO(json_data_bytes), filename="ship_backup.json")
    await interaction.followup.send(file=file, ephemeral=True)

@bot.tree.command(name="import_backup")
@is_staff()
async def import_backup(interaction: discord.Interaction, file: discord.Attachment):
    """Import a backup from a JSON file"""
    await interaction.response.defer(ephemeral=True)
    if not interaction.guild:
        return await interaction.followup.send("❌ This command can only be used in a server.", ephemeral=True)
    if file.content_type != "application/json":
        return await interaction.followup.send("❌ Invalid file type. Only JSON files are allowed.", ephemeral=True),

# Plushie Commands
@bot.tree.command(name="plushie_scan")
async def plushie_scan(interaction: discord.Interaction, photo: Optional[discord.Attachment] = None):
    """Register a new plushie to your collection"""
    await interaction.response.send_modal(PlushieModal(await photo.read() if photo else None))

@bot.tree.command(name="plushie_edit")
async def plushie_edit(interaction: discord.Interaction, name: str, photo: Optional[discord.Attachment] = None):
    """Edit an existing plushie in your collection"""
    plushie = PlushieManager.get_one(interaction.user.id, name)
    if not plushie:
        return await interaction.response.send_message("❌ You don't have a plushie with that name.", ephemeral=True) # type: ignore
    await interaction.response.send_modal(PlushieEditModal(name, interaction.user.id, await photo.read() if photo else None))

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

    await interaction.response.send_message(embed=embed, file=file if file else discord.utils.MISSING)

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

# Mission & Encouragement Commands
@bot.tree.command(name="mission")
async def mission(interaction: discord.Interaction):
    """Get a random space mission to complete!"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT message FROM missions ORDER BY RANDOM() LIMIT 1")
            mission_data = cur.fetchone()
            mission_text = mission_data['message'] if mission_data else "🚀 Take a break and stretch for 30 seconds!"
    
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
    
    # Mission rewards
    credits_earned = random.randint(10, 25)  # Random reward between 10-25 credits
    
    # Award credits
    with DatabasePool.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO user_stats (user_id, total_credits) 
                VALUES (%s, %s)
                ON CONFLICT (user_id) 
                DO UPDATE SET total_credits = user_stats.total_credits + EXCLUDED.total_credits
            """, (interaction.user.id, credits_earned))
    
    embed = discord.Embed(
        title="✅ Mission Complete!",
        description=f"**Mission:** {active['mission_text']}\n\n*Excellent work, pilot!*\n\n**Reward:** +{credits_earned} credits 💰",
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Completed by {interaction.user.display_name}")
    await interaction.response.send_message(embed=embed)
    
    # Track stats and check achievements
    mission_count = Achievement.increment_stat(interaction.user.id, "missions_completed")
    channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None
    await Achievement.check_and_award(interaction.user.id, "missions_completed", mission_count, channel)

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
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT message FROM encouragements ORDER BY RANDOM() LIMIT 1")
            encouragement_data = cur.fetchone()
            encouragement = encouragement_data['message'] if encouragement_data else "is sending you positive vibes! ✨"
    target = member or interaction.user
    
    embed = discord.Embed(
        title="✨ Cosmic Encouragement",
        description=f"**{interaction.user.display_name}** {encouragement}",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.set_footer(text=f"To: {target.display_name}")
    await interaction.response.send_message(embed=embed)
    
    # Track stats and check achievements
    given_count = Achievement.increment_stat(interaction.user.id, "encouragements_given")
    received_count = Achievement.increment_stat(target.id, "encouragements_received")
    
    channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None

    await Achievement.check_and_award(interaction.user.id, "encouragements_given", given_count, channel)
    await Achievement.check_and_award(target.id, "encouragements_received", received_count, channel)

@bot.tree.command(name="daily_mission")
@is_staff()
async def daily_mission(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    """Post a daily mission with header and footer (Staff only)"""
    target = channel or interaction.channel
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT message FROM missions ORDER BY RANDOM() LIMIT 1")
            mission_data = cur.fetchone()
            mission_text = mission_data['message'] if mission_data else "Complete a task today!"
    
    if isinstance(target, discord.TextChannel):
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
    else:
        await interaction.response.send_message("❌ Daily mission can only be posted to a text channel.", ephemeral=True)

@bot.tree.command(name="encourage_post")
@is_staff()
async def encourage_post(interaction: discord.Interaction, member: discord.Member, channel: Optional[discord.TextChannel] = None):
    """Post an encouragement announcement with header and footer (Staff only)"""
    target = channel or interaction.channel
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT message FROM encouragements ORDER BY RANDOM() LIMIT 1")
            encouragement_data = cur.fetchone()
            encouragement = encouragement_data['message'] if encouragement_data else "is being appreciated! ✨"
    
    if isinstance(target, discord.TextChannel):
        await target.send(embed=build_announcement_embed("header"))
        encourage_embed = discord.Embed(
            title="✨ Cosmic Encouragement",
            description=f"**{member.display_name}** {encouragement}",
            color=discord.Color.gold()
        )
        encourage_embed.set_thumbnail(url=member.display_avatar.url)
        encourage_embed.set_footer(text=f"Posted by {interaction.user.display_name}")
        await target.send(embed=encourage_embed)
        
        await target.send(embed=build_announcement_embed("footer"))
        await interaction.response.send_message(f"✅ Encouragement posted for {member.display_name}!", ephemeral=True)

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
    else:
        await interaction.response.send_message("❌ Encouragement can only be posted to a text channel.", ephemeral=True)

# FUN Commands
@bot.tree.command(name="space_fact")
async def space_fact(interaction: discord.Interaction):
    """Learn a random space fact!"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT fact FROM space_facts ORDER BY RANDOM() LIMIT 1")
            fact_data = cur.fetchone()
            fact_text = fact_data['fact'] if fact_data else "The universe is vast and full of wonders!"
    
    embed = discord.Embed(
        title="🌌 Space Fact!",
        description=fact_text,
        color=discord.Color.purple()
    )
    embed.set_footer(text="Knowledge is power, pilot!")
    await interaction.response.send_message(embed=embed)
@bot.tree.command(name="launch")
async def launch(interaction: discord.Interaction):
    """Launch a rocket with a countdown!"""
    embed = discord.Embed(
        title="🚀 Rocket Launch Sequence",
        description="Preparing for liftoff...",
        color=discord.Color(int(PALETTE['PB'].replace("#", ""), 16))
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

@bot.tree.command(name="orbit", description="Check how many pilots are currently in orbit")
async def orbit(interaction: discord.Interaction):
    """
    Revised Orbit Command: 
    Fetches the actual count of registered ships from the database.
    """
    try:
        with DatabasePool.get_conn() as conn:
            with conn.cursor() as cur:
                # We count how many unique users have registered a ship
                cur.execute("SELECT COUNT(*) FROM ships")
                count = cur.fetchone()[0]
                
                # Optional: Count users with an 'active' mission in the last hour
                cur.execute("SELECT COUNT(*) FROM active_missions WHERE started_at > NOW() - INTERVAL '12 hours'")
                active_now = cur.fetchone()[0]

        embed = discord.Embed(
            title="🛰️ Orbital Status Report",
            description=f"There are currently **{count}** registered ships in the sector.",
            color=discord.Color.blue()
        )
        
        if active_now > 0:
            embed.add_field(name="Current Activity", value=f"⚡ **{active_now}** pilots are currently on active missions!")
        else:
            embed.add_field(name="Current Activity", value="🌌 The sector is currently quiet.")

        # Add the themed footer you use for other commands
        embed.set_footer(text="Safe flying, pilot! 🚀")
        
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        logger.error(f"Error in orbit command: {e}")
        await interaction.response.send_message("❌ Failed to retrieve orbital data from Mission Control.", ephemeral=True)

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
    planets_count = Achievement.increment_stat(interaction.user.id, "planets_discovered")
    await Achievement.check_and_award(interaction.user.id, "planets_discovered", planets_count, interaction.channel)

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
    spacewalks_count = Achievement.increment_stat(interaction.user.id, "spacewalks_taken")
    await Achievement.check_and_award(interaction.user.id, "spacewalks_taken", spacewalks_count, interaction.channel)

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
    if not interaction.guild:
        return await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
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
    if not interaction.guild:
        return await interaction.response.send_message("❌ This command can only be used in a server!", ephemeral=True)
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
    
    if interaction.guild:
        # In a guild, target is always a Member
        target = member if member else interaction.user
        if not isinstance(target, discord.Member):
            return await interaction.response.send_message(
                "❌ Cannot fetch member information.",
                ephemeral=True
            )
        
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
    else:
        # In a DM, can only show info about the command user
        if member:
            return await interaction.response.send_message(
                "❌ Cannot get member information in DMs.",
                ephemeral=True
            )
        
        target = interaction.user
        
        embed = discord.Embed(title=f"👤 {target.display_name}", color=discord.Color.blue())
        embed.set_thumbnail(url=target.display_avatar.url)
        
        embed.add_field(name="Username", value=str(target), inline=True)
        embed.add_field(name="ID", value=str(target.id), inline=True)
        embed.add_field(name="Account Created", value=f"<t:{int(target.created_at.timestamp())}:R>", inline=False)
        
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
            value=f'{item["description"]}\n*ID: `{item_id}`*',
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="buy")
async def buy(interaction: discord.Interaction, item_id: int, quantity: int = 1):
    """Buy an item from the shop"""
    # Convert int to string for dictionary lookup
    item = SHOP_ITEMS.get(str(item_id))
    if not item:
        return await interaction.response.send_message("❌ Item not found.", ephemeral=True)

    cost = item["price"] * max(1, quantity)

    with DatabasePool.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT total_credits FROM user_stats WHERE user_id = %s",
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
                """INSERT INTO user_stats (user_id, total_credits)
                   VALUES (%s, %s)
                   ON CONFLICT (user_id)
                   DO UPDATE SET total_credits = user_stats.total_credits - %s""",
                (interaction.user.id, balance - cost, cost)
            )

    # Use item_id as integer for database
    InventoryManager.add_item(interaction.user.id, item_id, quantity)

    # Fix: Use Achievement, not Achievement
    purchased = Achievement.increment_stat(
        interaction.user.id, "items_purchased", quantity
    )
    channel = interaction.channel if isinstance(interaction.channel, discord.TextChannel) else None
    await Achievement.check_and_award(
        interaction.user.id, "items_purchased", purchased, channel
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

@bot.tree.command(name="ship", description="Check your ship's current status and health")
async def ship_status(interaction: discord.Interaction):
    ship = ShipManager.get_ship(interaction.user.id)
    if not ship:
        return await interaction.response.send_message("You don't own a ship yet!", ephemeral=True)
    
    # Calculate health percentage for a visual bar
    percent = (ship['health'] / ship['max_health']) * 10
    health_bar = "🟩" * int(percent) + "🟥" * (10 - int(percent))

    embed = discord.Embed(title=f"🚀 Starship: {ship['name']}", color=discord.Color.blue())
    embed.add_field(name="Hull Integrity", value=f"{health_bar}\n{ship['health']} / {ship['max_health']} HP", inline=False)
    embed.add_field(name="Ship Class", value=ship['ship_class'], inline=True)
    embed.add_field(name="Engine Level", value=ship['engine_level'], inline=True)
    embed.add_field(name="Shield Level", value=ship['shield_level'], inline=True)
    
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
                "SELECT total_credits FROM user_stats WHERE user_id = %s",
                (interaction.user.id,)
            )
            balance = cur.fetchone()[0]

            if balance < cost:
                return await interaction.response.send_message(
                    f"❌ Upgrade costs {cost}, you have {balance}.",
                    ephemeral=True
                )

            cur.execute(
                "UPDATE user_stats SET total_credits = total_credits - %s WHERE user_id = %s",
                (cost, interaction.user.id)
            )

    if ShipManager.upgrade_ship(interaction.user.id, component):
        upgraded = Achievement.increment_stat(
            interaction.user.id, "ship_upgrades"
        )
        await Achievement.check_and_award(
            interaction.user.id, "ship_upgrades", upgraded, interaction.channel
        )

        await interaction.response.send_message(
            f"⚙️ {upgrade['emoji']} **{upgrade['name']} upgraded to Level {level + 1}!**"
        )
    else:
        await interaction.response.send_message("❌ Failed to upgrade ship.")

# Moderator application commands
@bot.tree.command(name="apply_mod")
async def apply_mod(interaction: discord.Interaction):
    """Apply to become a moderator for the Starflight Pilot crew"""
    await interaction.response.send_modal(ModApplicationModal())

# In the /mod_applications command (around line 2650), add this near the top after checking status:

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
    
    # Define status emoji mapping
    status_emoji_map = {"pending": "⏳", "accepted": "✅", "rejected": "❌"}
    
    for app in applications[:10]:  # Show first 10
        try:
            if interaction.guild:
                user = await interaction.guild.fetch_member(app['user_id'])
                status_emoji = status_emoji_map.get(app['status'], "❓")
                
                embed.add_field(
                    name=f"{status_emoji} {user.display_name} (ID: {app['id']})",
                    value=f"Submitted: <t:{int(app['submitted_at'].timestamp())}:R>\nUse `/mod_application_view {app['id']}` to review",
                    inline=False
                )
        except:
            status_emoji = status_emoji_map.get(app['status'], "❓")
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
    if not interaction.guild:
        return await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
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
    }.get(app['status'], discord.Color.pink())
    
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
    if not interaction.guild:
        return await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
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
    if not interaction.guild:
        return await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
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
    }.get(app['status'], discord.Color.pink())
    
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
# INTRODUCTION COMMANDS
# =========================

@bot.tree.command(name="introduction_create")
async def introduction_create(interaction: discord.Interaction):
    """Create or update your introduction"""
    await interaction.response.send_modal(IntroductionModal())


@bot.tree.command(name="introduction_view")
async def introduction_view(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    """View your or another member's introduction"""
    target = member or interaction.user
    
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM introductions WHERE user_id = %s
            """, (target.id,))
            intro = cur.fetchone()
    
    if not intro:
        if target == interaction.user:
            return await interaction.response.send_message(
                "📋 You haven't created an introduction yet! Use `/introduction_create` to make one.",
                ephemeral=True
            )
        else:
            return await interaction.response.send_message(
                f"📋 {target.display_name} hasn't created an introduction yet.",
                ephemeral=True
            )
    
    embed = discord.Embed(
        title=f"👋 {intro['name']}'s Introduction",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    
    if intro['pronouns']:
        embed.add_field(name="Pronouns", value=intro['pronouns'], inline=True)
    if intro['age']:
        embed.add_field(name="Age", value=intro['age'], inline=True)
    
    embed.add_field(name="🎮 Interests", value=intro['interests'], inline=False)
    embed.add_field(name="💬 About", value=intro['about'], inline=False)
    
    embed.set_footer(text=f"Last updated: {intro['updated_at'].strftime('%Y-%m-%d')}")
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="introduction_post")
async def introduction_post(interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
    """Post your introduction to a channel"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM introductions WHERE user_id = %s
            """, (interaction.user.id,))
            intro = cur.fetchone()
    
    if not intro:
        return await interaction.response.send_message(
            "📋 You haven't created an introduction yet! Use `/introduction_create` first.",
            ephemeral=True
        )
    
    target = channel or interaction.channel
    if not isinstance(target, discord.TextChannel):
        return await interaction.response.send_message(
            "❌ Can only post to text channels.",
            ephemeral=True
        )
    
    embed = discord.Embed(
        title=f"👋 New Crew Member: {intro['name']}",
        description="Welcome aboard the station!",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    
    if intro['pronouns']:
        embed.add_field(name="Pronouns", value=intro['pronouns'], inline=True)
    if intro['age']:
        embed.add_field(name="Age", value=intro['age'], inline=True)
    
    embed.add_field(name="🎮 Interests", value=intro['interests'], inline=False)
    embed.add_field(name="💬 About", value=intro['about'], inline=False)
    
    embed.set_footer(text=f"Pilot: {interaction.user.display_name}")
    
    await target.send(embed=embed)
    await interaction.response.send_message(
        f"✅ Introduction posted to {target.mention}!",
        ephemeral=True
    )


@bot.tree.command(name="introduction_delete")
async def introduction_delete(interaction: discord.Interaction):
    """Delete your introduction"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM introductions WHERE user_id = %s
            """, (interaction.user.id,))
            deleted = cur.rowcount > 0
    
    if deleted:
        await interaction.response.send_message("✅ Your introduction has been deleted.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ You don't have an introduction to delete.", ephemeral=True)


# =========================
# CHARACTER SHEET COMMANDS
# =========================

@bot.tree.command(name="character_create")
async def character_create(interaction: discord.Interaction):
    """Create a new character sheet for roleplay"""
    await interaction.response.send_modal(CharacterSheetModal())


@bot.tree.command(name="character_edit")
async def character_edit(interaction: discord.Interaction, character_name: str):
    """Edit an existing character sheet"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM character_sheets 
                WHERE user_id = %s AND LOWER(char_name) = LOWER(%s)
            """, (interaction.user.id, character_name))
            char = cur.fetchone()
    
    if not char:
        return await interaction.response.send_message(
            f"❌ You don't have a character named **{character_name}**.",
            ephemeral=True
        )
    
    await interaction.response.send_modal(CharacterSheetModal(character_name))


@bot.tree.command(name="character_view")
async def character_view(interaction: discord.Interaction, owner: discord.Member, character_name: str):
    """View a character sheet"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM character_sheets 
                WHERE user_id = %s AND LOWER(char_name) = LOWER(%s)
            """, (owner.id, character_name))
            char = cur.fetchone()
    
    if not char:
        return await interaction.response.send_message(
            f"❌ {owner.display_name} doesn't have a character named **{character_name}**.",
            ephemeral=True
        )
    
    embed = discord.Embed(
        title=f"📜 {char['char_name']}",
        color=discord.Color.purple()
    )
    embed.set_thumbnail(url=owner.display_avatar.url)
    
    embed.add_field(name="🧬 Species", value=char['species'], inline=True)
    embed.add_field(name="👤 Owner", value=owner.mention, inline=True)
    embed.add_field(name="👁️ Appearance", value=char['appearance'], inline=False)
    embed.add_field(name="✨ Personality", value=char['personality'], inline=False)
    embed.add_field(name="📖 Backstory", value=char['backstory'], inline=False)
    
    embed.set_footer(text=f"Created: {char['created_at'].strftime('%Y-%m-%d')}")
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="character_list")
async def character_list(interaction: discord.Interaction, owner: Optional[discord.Member] = None):
    """List all characters owned by you or another user"""
    target = owner or interaction.user
    
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT char_name, species FROM character_sheets 
                WHERE user_id = %s 
                ORDER BY created_at DESC
            """, (target.id,))
            characters = cur.fetchall()
    
    if not characters:
        if target == interaction.user:
            return await interaction.response.send_message(
                "📋 You don't have any characters yet! Use `/character_create` to make one.",
                ephemeral=True
            )
        else:
            return await interaction.response.send_message(
                f"📋 {target.display_name} doesn't have any characters yet.",
                ephemeral=True
            )
    
    embed = discord.Embed(
        title=f"📜 {target.display_name}'s Characters",
        description="\n".join(
            f"• **{char['char_name']}** - {char['species']}"
            for char in characters
        ),
        color=discord.Color.purple()
    )
    embed.set_footer(text=f"Total: {len(characters)} character(s)")
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="character_delete")
async def character_delete(interaction: discord.Interaction, character_name: str):
    """Delete one of your character sheets"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM character_sheets 
                WHERE user_id = %s AND LOWER(char_name) = LOWER(%s)
            """, (interaction.user.id, character_name))
            deleted = cur.rowcount > 0
    
    if deleted:
        await interaction.response.send_message(
            f"✅ Character **{character_name}** has been deleted.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"❌ You don't have a character named **{character_name}**.",
            ephemeral=True
        )


@bot.tree.command(name="character_post")
async def character_post(interaction: discord.Interaction, character_name: str, channel: Optional[discord.TextChannel] = None):
    """Post a character sheet to a channel"""
    with DatabasePool.get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM character_sheets 
                WHERE user_id = %s AND LOWER(char_name) = LOWER(%s)
            """, (interaction.user.id, character_name))
            char = cur.fetchone()
    
    if not char:
        return await interaction.response.send_message(
            f"❌ You don't have a character named **{character_name}**.",
            ephemeral=True
        )
    
    target = channel or interaction.channel
    if not isinstance(target, discord.TextChannel):
        return await interaction.response.send_message(
            "❌ Can only post to text channels.",
            ephemeral=True
        )
    
    embed = discord.Embed(
        title=f"📜 {char['char_name']}",
        color=discord.Color.purple()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    
    embed.add_field(name="🧬 Species", value=char['species'], inline=True)
    embed.add_field(name="👤 Player", value=interaction.user.mention, inline=True)
    embed.add_field(name="👁️ Appearance", value=char['appearance'], inline=False)
    embed.add_field(name="✨ Personality", value=char['personality'], inline=False)
    embed.add_field(name="📖 Backstory", value=char['backstory'], inline=False)
    
    embed.set_footer(text=f"Character by {interaction.user.display_name}")
    
    await target.send(embed=embed)
    await interaction.response.send_message(
        f"✅ Character sheet posted to {target.mention}!",
        ephemeral=True
    )
@bot.tree.command(name="salvage", description="Scavenge deep space wreckage for loot (risk of ship damage!)")
@app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
async def salvage(interaction: discord.Interaction):
    ship = ShipManager.get_ship(interaction.user.id)
    if not ship:
        return await interaction.response.send_message("❌ You don't have a ship! Use `/ship_create` first.", ephemeral=True)
    
    if ship['health'] <= 0:
        return await interaction.response.send_message("⚠️ Your ship is too damaged to fly! Use `/repair_ship` first.", ephemeral=True)

    await interaction.response.defer()
    roll = random.random()
    
    # 25% chance of taking damage
    if roll < 0.25:
        damage = random.randint(15, 35)
        new_hp = ShipManager.damage_ship(interaction.user.id, damage)
        embed = discord.Embed(
            title="💥 Collision during Salvage!",
            description=f"You navigated a debris field but hit a bulkhead! Took **{damage}** damage.\n\n**Hull Integrity:** {new_hp}/{ship['max_health']} HP",
            color=discord.Color.red()
        )
    # 45% chance of finding an item
    elif roll < 0.70:
        # Use integer item IDs that match the database
        loot_pool = [1, 2, 3]  # Fuel Cell, Repair Kit, Stardust
        item_id = random.choice(loot_pool)
        InventoryManager.add_item(interaction.user.id, item_id)
        
        # Fix: Use Achievement, not Achievement
        Achievement.increment_stat(interaction.user.id, "salvages_completed")
        
        # Get item name from SHOP_ITEMS
        item_name = SHOP_ITEMS[str(item_id)]["name"]
        
        embed = discord.Embed(
            title="📦 Successful Salvage",
            description=f"You successfully recovered 1x **{item_name}** from the wreckage!",
            color=discord.Color.green()
        )
    # 30% chance of finding nothing
    else:
        embed = discord.Embed(
            title="🌌 Empty Wreckage",
            description="You searched the floating remains but found nothing of value.",
            color=discord.Color.blue()
        )
    
    await interaction.followup.send(embed=embed)

# Replace the /repair_ship command (around line 2955):

@bot.tree.command(name="repair_ship", description="Use a repair kit to fix your ship's hull")
async def repair_ship_cmd(interaction: discord.Interaction):
    ship = ShipManager.get_ship(interaction.user.id)
    if not ship:
        return await interaction.response.send_message("❌ You don't have a ship.", ephemeral=True)
        
    if ship['health'] >= ship['max_health']:
        return await interaction.response.send_message("✅ Your ship is already at full health!", ephemeral=True)

    # Use integer item_id (2 is Repair Kit)
    has_kit = InventoryManager.remove_item(interaction.user.id, 2, 1)
    if not has_kit:
        return await interaction.response.send_message("❌ You don't have any **Repair Kits** in your inventory! Buy one from the `/shop`.", ephemeral=True)
    
    new_hp = ShipManager.repair_ship(interaction.user.id, 50)
    await interaction.response.send_message(f"🔧 **Repairs Complete!** Your ship has been restored to **{new_hp}/{ship['max_health']} HP**.")

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