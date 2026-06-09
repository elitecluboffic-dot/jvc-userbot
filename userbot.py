import os
import time
import asyncio
import random
import logging
import re
import json
import shutil
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.functions.contacts import BlockRequest
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import SendMessageTypingAction, User, MessageActionChatAddUser, MessageActionChatJoinedByLink, MessageActionChatJoinedByRequest
from telethon.tl.custom import Button
from telethon.errors import FloodWaitError
from pyrogram import Client as PyroClient
from pyrogram.raw.functions.phone import LeaveGroupCall
from pyrogram.raw.types import InputGroupCall
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

# ─────────────────────────────────────────────────────────
# ENV & CONFIG
# ─────────────────────────────────────────────────────────
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
TELE_SESS = os.getenv("SESSION_STRING_1", "").strip()
PYRO_SESS = os.getenv("PYRO_SESSION", "").strip()

RAW_TOKENS = os.getenv("BOT_TOKENS", "").strip()
BOT_TOKENS = [t.strip() for t in RAW_TOKENS.split(",") if t.strip()]

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()]

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").strip().lstrip("@")
PAP_BOT_TOKEN = os.getenv("PAP_BOT_TOKEN", "").strip()
PAP_CHANNEL = os.getenv("PAP_CHANNEL", "@pap_clean").strip()

TARGET_GROUP_ID = "@CARI_CRUSH_ONLINE"
AUTO_CHAT_INTERVAL = 600

LINK_REGEX = r'(https?://[^\s]+|t\.me/[^\s]+|www\.[^\s]+|\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b)'
MENTION_REGEX = r'@\w+'

last_welcome_msg_id = None
_welcome_lock = asyncio.Lock()

# ─────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("telethon.extensions.html").setLevel(logging.WARNING)
logging.getLogger("telethon.network.mtprotosender").setLevel(logging.WARNING)
logging.getLogger("pyrogram.client").setLevel(logging.WARNING)
logging.getLogger("pyrogram.session").setLevel(logging.WARNING)

# ─────────────────────────────────────────────────────────
# DATABASE JSON (PAP SYSTEM)
# ─────────────────────────────────────────────────────────
DB_PATH = "pap_database.json"
BACKUP_DIR = "backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

DEFAULT_DB = {
    "users": {},
    "queue_free": [],
    "queue_premium": [],
    "stats": {
        "total_post": 0,
        "total_users": 0
    },
    "settings": {
        "free_daily_limit": 3,
        "premium_daily_limit": 20,
        "watermark_text": "@PAP_AUTOPOST",
        "post_interval_free": 60,
        "post_interval_premium": 10
    }
}

def load_db() -> dict:
    if not os.path.exists(DB_PATH):
        save_db(DEFAULT_DB)
        return DEFAULT_DB.copy()
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in DEFAULT_DB:
            if key not in data:
                data[key] = DEFAULT_DB[key]
        return data
    except Exception as e:
        logger.error(f"❌ [DB] Gagal load DB: {e}")
        return DEFAULT_DB.copy()

def save_db(data: dict):
    try:
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"❌ [DB] Gagal save DB: {e}")

def backup_db():
    try:
        if not os.path.exists(DB_PATH):
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"pap_database_{timestamp}.json")
        shutil.copy2(DB_PATH, backup_path)
        logger.info(f"✅ [DB-BACKUP] Backup tersimpan: {backup_path}")
        backups = sorted([
            f for f in os.listdir(BACKUP_DIR) if f.startswith("pap_database_")
        ])
        while len(backups) > 10:
            os.remove(os.path.join(BACKUP_DIR, backups.pop(0)))
    except Exception as e:
        logger.error(f"❌ [DB-BACKUP] Gagal backup: {e}")

def get_user(db: dict, user_id: int) -> dict:
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {
            "user_id": user_id,
            "username": None,
            "display_name": None,
            "is_premium": False,
            "premium_expiry": None,
            "daily_post_count": 0,
            # ── UPDATED: simpan timestamp ISO post pertama hari ini ──
            "quota_reset_time": None,
            "total_posts": 0,
            "joined_at": datetime.now().isoformat(),
            "is_banned": False
        }
        db["stats"]["total_users"] += 1
        save_db(db)
    # ── Migrasi user lama yang belum punya quota_reset_time ──
    if "quota_reset_time" not in db["users"][uid]:
        db["users"][uid]["quota_reset_time"] = None
    return db["users"][uid]

def update_user(db: dict, user_id: int, **kwargs):
    uid = str(user_id)
    if uid in db["users"]:
        db["users"][uid].update(kwargs)
        save_db(db)

def is_premium(db: dict, user_id: int) -> bool:
    user = get_user(db, user_id)
    if not user["is_premium"]:
        return False
    if user["premium_expiry"]:
        expiry = datetime.fromisoformat(user["premium_expiry"])
        if datetime.now() > expiry:
            update_user(db, user_id, is_premium=False, premium_expiry=None)
            return False
    return True

def get_daily_limit(db: dict, user_id: int) -> int:
    if is_premium(db, user_id):
        return db["settings"]["premium_daily_limit"]
    return db["settings"]["free_daily_limit"]

# ─────────────────────────────────────────────────────────
# ── UPDATED: Reset kuota 24 jam sejak post pertama ──
# ─────────────────────────────────────────────────────────
def reset_daily_if_needed(db: dict, user_id: int):
    """
    Kuota di-reset 24 jam setelah post pertama dilakukan.
    Bukan midnight reset — tapi rolling 24 jam.
    """
    user = get_user(db, user_id)
    reset_time_str = user.get("quota_reset_time")

    if reset_time_str is None:
        # Belum pernah post sama sekali, atau sudah di-reset
        return

    reset_time = datetime.fromisoformat(reset_time_str)
    now = datetime.now()

    if now >= reset_time:
        # Sudah lewat 24 jam → reset kuota
        update_user(db, user_id,
            daily_post_count=0,
            quota_reset_time=None
        )
        logger.info(f"🔄 [QUOTA-RESET] Kuota user {user_id} di-reset (24 jam terpenuhi)")

def get_quota_reset_remaining(db: dict, user_id: int) -> str:
    """
    Kembalikan string sisa waktu sampai kuota reset.
    Contoh: '5 jam 30 menit' atau '45 menit' atau '23 detik'
    """
    user = get_user(db, user_id)
    reset_time_str = user.get("quota_reset_time")

    if reset_time_str is None:
        return "Sekarang"

    reset_time = datetime.fromisoformat(reset_time_str)
    now = datetime.now()
    delta = reset_time - now

    if delta.total_seconds() <= 0:
        return "Sekarang"

    total_seconds = int(delta.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if hours > 0:
        return f"{hours} jam {minutes} menit"
    elif minutes > 0:
        return f"{minutes} menit {seconds} detik"
    else:
        return f"{seconds} detik"

def can_post_today(db: dict, user_id: int) -> bool:
    reset_daily_if_needed(db, user_id)
    user = get_user(db, user_id)
    limit = get_daily_limit(db, user_id)
    return user["daily_post_count"] < limit

def remaining_posts(db: dict, user_id: int) -> int:
    reset_daily_if_needed(db, user_id)
    user = get_user(db, user_id)
    limit = get_daily_limit(db, user_id)
    return max(0, limit - user["daily_post_count"])

def record_post_usage(db: dict, user_id: int):
    """
    Catat 1 post dipakai. Kalau ini post pertama hari ini,
    set quota_reset_time = sekarang + 24 jam.
    """
    reset_daily_if_needed(db, user_id)
    user = get_user(db, user_id)
    new_count = user["daily_post_count"] + 1

    update_kwargs = {
        "daily_post_count": new_count,
        "total_posts": user["total_posts"] + 1
    }

    # Set reset time hanya saat post pertama (count sebelumnya = 0)
    if user["daily_post_count"] == 0 or user.get("quota_reset_time") is None:
        reset_at = (datetime.now() + timedelta(hours=24)).isoformat()
        update_kwargs["quota_reset_time"] = reset_at
        logger.info(f"⏰ [QUOTA] User {user_id} mulai kuota baru, reset dijadwalkan 24 jam lagi")

    update_user(db, user_id, **update_kwargs)

# ─────────────────────────────────────────────────────────
# DM SPAM WARNING SYSTEM
# ─────────────────────────────────────────────────────────
dm_warning_count = {}
DM_MAX_WARNING = 5
DM_GCAST_KEYWORDS = [
    "gcast", "gikes", "broadcast", "ready p", "bantu up",
    "pm panel", "open bo", "join sini", "join dong", "masuk sini"
]

WELCOME_TEMPLATES = [
    "🎉 Heyy, **{name}** baru aja masuk ke grup!\nSalam kenal ya, semoga betah dan aktif di sini 😄\n\n📌 Jangan lupa baca rules grup ya kak~",
    "👋 Selamat datang **{name}**!\nSenang banget ada anggota baru nih 🥳\nYuk langsung gabung ngobrol, jangan malu-malu~",
    "🌟 Welcome to the fam, **{name}**! 🎊\nKita baik-baik kok di sini, santai aja ya~\nKalau ada yang mau ditanyain, langsung gas aja 😊",
    "🚀 Ada yang baru nih!\n**{name}** resmi bergabung ke grup kita 🎉\nHope you enjoy it here, feel free to say hi!",
    "💫 Yeay, **{name}** udah join!\nWelcome welcome~ Jangan jadi silent reader aja ya, yuk rame-ramein grup 😁",
    "🎈 Halo **{name}**, selamat datang!\nMudah-mudahan betah ya di sini 🙏\nGrup ini friendly kok, jadi jangan sungkan~",
    "🌈 **{name}** baru aja landing di grup kita! ✈️\nWelcome on board~ Yuk kenalan dulu sama anak-anak sini 👋",
    "🎁 Member baru alert! 🚨\n**{name}** resmi jadi bagian dari kita sekarang 😎\nSelamat datang, semoga kerasan!",
    "✨ Heyy **{name}**! Akhirnya kesasar juga ke sini wkwk 😂\nWelcome! Gas langsung aktif ya, jangan lurker doang hehe~",
    "🏠 **{name}** udah masuk, anggap aja rumah sendiri ya! 😄\nWelcome to the squad~ Jangan pelit komentar loh!",
]

LIST_OBROLAN = [
    "p", "P", "gimana gess? aman semua kan?", "sepi amat dah wkwk pada ke mana nih orang-orang",
    "gess absen dulu dong yang lagi online jam segini 👋", "hadir gess, baru mantau lagi nih",
    "ada yang lagi free gak? nemenin ngobrol sini", "halo semuanya, selamat beraktivitas ya gess",
    "ooii bro, lagi pada sibuk ya?", "yuk ramein yuk, jangan biarkan grup ini mati suri 😂", "turu kabeeh ta iki? 😴",
    "mabar gak nih gess? gabut bener gua asli", "ada yang main ml gak? login lah gass full team",
    "bntr lagi reset season ya? pusing gua dapet tim publik ampas mulu", "ada rekomendasi game offline yang seru gak di HP? mau nyoba",
    "pubg gass lah, ketik 1 yang mau ikut ngerush", "hoki bener gua tadi malem main game wkwk",
    "lagi males main game kompetitif, bikin emosi doang wkwk", "ada rekomendasi film bagus gak di netflix? yang genrenya thriller/horor",
    "eh beneran film yang kemarin rame itu seru? mau nonton tapi mager", "lagi rame banget ya di tiktok masalah itu, ada yang ngikutin?",
    "rekomendasi series yang sekali duduk langsung tamat dong gess", "capek banget scrol sosmed isinya drama mulu wkwk",
    "ngopi dulu gess biar ga panik batin☕", "cuaca di tempat kalian gimana? tempat gua ujan deras bener",
    "enaknya jam segini makan apa ya? rekomendasi kuliner dong", "rekomendasi tempat nongkrong yang free wifi dan kopinya enak dong gess",
    "laper bener bjir, padahal tadi udah makan", "es teh manis emang paling juara sih kalau cuaca lagi panas gini",
    "pada suka kopi hitam apa kopi susu nih gess?", "wkwk gokil sih emang", "gas lah ga pake lama",
    "yoii bro santai aja haha", "seriusan lu? wkwk", "skip dulu deh kalo itu wkwk", "mantap jaya 🔥",
    "up dulu lah biar ga tenggelam nih grup 🚀", "males ngetik panjang, intinya gas aja lah wkwk",
    "bisa gitu ya wkwkwk", "nah eta!", "aman aman aman 👍", "oke siap gas", "wkwkwk joss lah",
    "bener juga sih", "lah iya kah?", "wkwk parah sih", "bisa jadi, bisa jadi 🤔", "walah wkwk", "gasskeun!",
    "enaknya jam segini ngapain ya? gabut bener asli", "jaringan lagi rada ngadat nih tempat gua, pantesan agak telat bales",
    "ada yang lagi dengerin musik gak? bagi judul lagu yang enak dong", "ngantuk bener bjir, padahal semalem tidur cepet",
    "capek-capek kerja, ujung-undunya duitnya habis buat jajan doang wkwk", "random bener pikiran gua jam segini wkwk",
    "hidup lagi capek-capeknya, malah nemu ginian wkwk"
]

# ─────────────────────────────────────────────────────────
# CLIENT INIT
# ─────────────────────────────────────────────────────────
tele = TelegramClient(StringSession(TELE_SESS), API_ID, API_HASH)
pyro = None
call = None
bot_clients = []
pap_bot: TelegramClient = None

# ─────────────────────────────────────────────────────────
# PAP AUTOPOST SYSTEM
# ─────────────────────────────────────────────────────────

def build_main_menu(user_id: int, db: dict) -> list:
    premium = is_premium(db, user_id)
    sisa = remaining_posts(db, user_id)
    badge = "💎 Premium" if premium else "🆓 Free"
    return [
        [Button.text(f"📤 Kirim PAP  |  {badge}  |  Sisa: {sisa}x", resize=True)],
        [Button.text("👤 Profil Saya"), Button.text("📊 Statistik")],
        [Button.text("💎 Upgrade Premium"), Button.text("📋 Cara Pakai")],
    ]

def build_admin_menu() -> list:
    return [
        [Button.text("👥 Daftar User"), Button.text("📊 Statistik Bot")],
        [Button.text("✅ Approve Premium"), Button.text("❌ Revoke Premium")],
        [Button.text("🚫 Ban User"), Button.text("✅ Unban User")],
        [Button.text("📤 Force Post"), Button.text("💾 Backup DB")],
        [Button.text("⚙️ Pengaturan"), Button.text("📢 Broadcast")],
        [Button.text("🗑️ Hapus Postingan"), Button.text("🔄 Reset Kuota User")],
    ]

async def pap_send_welcome(bot: TelegramClient, user_id: int, user_name: str, username: str, db: dict):
    premium = is_premium(db, user_id)
    badge = "💎 **PREMIUM**" if premium else "🆓 **FREE**"
    uname_display = f"@{username}" if username else "Tidak Ada"
    text = (
        f"✨ **SELAMAT DATANG DI PAP AUTOPOST** ✨\n\n"
        f"Halo **{user_name}** 👋\n\n"
        f"Bot ini digunakan untuk mengirim photo atau video anonymous "
        f"yang akan secara otomatis terposting ke channel {PAP_CHANNEL}.\n\n"
        f"──────────────────────────\n"
        f"👤 **INFORMASI AKUN**\n\n"
        f"🏷️ Display Name: **{user_name}**\n"
        f"👤 Username: {uname_display}\n"
        f"🆔 ID: `{user_id}`\n"
        f"🎖️ Status: {badge}\n"
        f"──────────────────────────\n\n"
        f"⚠️ Sebelum menggunakan bot, harap pahami aturan dan cara penggunaan.\n"
        f"Silakan tekan tombol di bawah untuk memulai."
    )
    await bot.send_message(user_id, text, buttons=build_main_menu(user_id, db), parse_mode='md')

async def pap_send_help(bot: TelegramClient, user_id: int, db: dict):
    sisa_free = db["settings"]["free_daily_limit"]
    sisa_prem = db["settings"]["premium_daily_limit"]
    wm = db["settings"]["watermark_text"]
    text = (
        f"📋 **CARA MENGGUNAKAN BOT**\n\n"
        f"**📤 Cara Kirim PAP:**\n"
        f"1. Tekan tombol **Kirim PAP**\n"
        f"2. Kirim foto atau video kamu\n"
        f"3. Wajib sertakan hashtag **#m** (cowok) atau **#f** (cewek)\n"
        f"4. Konten akan otomatis terposting ke {PAP_CHANNEL}\n\n"
        f"──────────────────────────\n"
        f"**🆓 User Free:**\n"
        f"• {sisa_free}x post per 24 jam\n"
        f"• Ada watermark `{wm}`\n"
        f"• Masuk antrian umum\n\n"
        f"**💎 User Premium:**\n"
        f"• {sisa_prem}x post per 24 jam\n"
        f"• Tanpa watermark\n"
        f"• Antrian prioritas (lebih cepat)\n"
        f"• Post langsung tanpa antre\n\n"
        f"──────────────────────────\n"
        f"**⏰ Sistem Kuota:**\n"
        f"• Kuota dihitung **24 jam** sejak post pertamamu\n"
        f"• Bukan reset tengah malam, tapi rolling 24 jam\n"
        f"• Cek sisa kuota di tombol **Kirim PAP** atau **Profil**\n\n"
        f"──────────────────────────\n"
        f"**⚠️ Larangan:**\n"
        f"• Dilarang spam / kirim berkali-kali\n"
        f"• Dilarang NSFW / konten dewasa\n"
        f"• Dilarang link, username di caption\n"
        f"• Video maksimal 20MB\n\n"
        f"Melanggar = **BAN PERMANEN** ‼️"
    )
    await bot.send_message(user_id, text, buttons=build_main_menu(user_id, db), parse_mode='md')

async def pap_send_profile(bot: TelegramClient, user_id: int, db: dict):
    user = get_user(db, user_id)
    premium = is_premium(db, user_id)
    reset_daily_if_needed(db, user_id)
    # Reload setelah mungkin di-reset
    user = get_user(db, user_id)
    badge = "💎 Premium" if premium else "🆓 Free"
    sisa = remaining_posts(db, user_id)
    limit = get_daily_limit(db, user_id)
    expiry_text = "Selamanya" if (premium and not user["premium_expiry"]) else (user["premium_expiry"][:10] if user["premium_expiry"] else "-")

    # Tampilkan info reset kuota
    reset_time_str = user.get("quota_reset_time")
    if reset_time_str and sisa == 0:
        sisa_waktu = get_quota_reset_remaining(db, user_id)
        quota_info = f"⏳ Kuota reset dalam: `{sisa_waktu}`"
    elif reset_time_str:
        sisa_waktu = get_quota_reset_remaining(db, user_id)
        quota_info = f"🔄 Reset kuota dalam: `{sisa_waktu}`"
    else:
        quota_info = f"✅ Kuota belum dipakai hari ini"

    text = (
        f"👤 **PROFIL KAMU**\n\n"
        f"🏷️ Nama: **{user['display_name'] or 'Unknown'}**\n"
        f"🆔 ID: `{user_id}`\n"
        f"🎖️ Status: **{badge}**\n"
        f"📅 Expired: `{expiry_text}`\n\n"
        f"──────────────────────────\n"
        f"📊 **STATISTIK POST:**\n"
        f"📤 Total Post: `{user['total_posts']}x`\n"
        f"📅 Post Periode Ini: `{user['daily_post_count']}/{limit}`\n"
        f"✅ Sisa Kuota: `{sisa}x`\n"
        f"{quota_info}\n"
        f"📆 Bergabung: `{user['joined_at'][:10]}`\n"
        f"──────────────────────────"
    )
    await bot.send_message(user_id, text, buttons=build_main_menu(user_id, db), parse_mode='md')

async def pap_send_stats(bot: TelegramClient, user_id: int, db: dict):
    stats = db["stats"]
    total_users = len(db["users"])
    premium_count = sum(1 for u in db["users"].values() if u.get("is_premium"))
    free_count = total_users - premium_count
    q_free = len(db["queue_free"])
    q_prem = len(db["queue_premium"])
    text = (
        f"📊 **STATISTIK BOT PAP AUTOPOST**\n\n"
        f"👥 Total User: `{total_users}`\n"
        f"💎 Premium: `{premium_count}` | 🆓 Free: `{free_count}`\n\n"
        f"📤 Total Post: `{stats.get('total_post', 0)}`\n"
        f"📥 Antrian Sekarang:\n"
        f"├ 💎 Premium: `{q_prem}` post\n"
        f"└ 🆓 Free: `{q_free}` post"
    )
    await bot.send_message(user_id, text, buttons=build_main_menu(user_id, db), parse_mode='md')

async def pap_send_premium_info(bot: TelegramClient, user_id: int, db: dict):
    first_admin = ADMIN_IDS[0] if ADMIN_IDS else None
    text = (
        f"💎 **UPGRADE KE PREMIUM**\n\n"
        f"Dapatkan akses penuh dengan fitur eksklusif:\n\n"
        f"✅ Post lebih banyak ({db['settings']['premium_daily_limit']}x/24 jam)\n"
        f"✅ Antrian prioritas (posting duluan)\n"
        f"✅ Tanpa watermark di konten\n"
        f"✅ Support langsung dari admin\n\n"
        f"──────────────────────────\n"
        f"💰 **Harga & Durasi:**\n"
        f"• 1 Bulan: Hubungi Admin\n"
        f"• 3 Bulan: Hubungi Admin\n"
        f"• Permanen: Hubungi Admin\n\n"
        f"📩 Tekan tombol di bawah untuk menghubungi admin:"
    )
    buttons = []
    if ADMIN_USERNAME:
        buttons.append([Button.url("📩 Hubungi Admin", f"https://t.me/{ADMIN_USERNAME}")])
    elif first_admin:
        buttons.append([Button.inline("📩 Info Admin", data=b"show_admin_id")])
    buttons.append([Button.inline("🔙 Kembali ke Menu", data=b"back_main_menu")])
    await bot.send_message(user_id, text, buttons=buttons, parse_mode='md')

# ─── State tracking untuk proses kirim PAP ───
pap_waiting_media = {}

async def check_user_joined(bot: TelegramClient, user_id: int) -> bool:
    try:
        channel = PAP_CHANNEL.lstrip("@")
        participant = await bot(GetParticipantRequest(channel=channel, participant=user_id))
        return participant is not None
    except Exception:
        return False

async def send_join_prompt(bot: TelegramClient, user_id: int):
    channel = PAP_CHANNEL.lstrip("@")
    await bot.send_message(
        user_id,
        f"📢 Kamu wajib join channel terlebih dahulu sebelum menggunakan bot.\n\n"
        f"1. Tekan **Join Channel** di bawah\n"
        f"2. Setelah join, tekan **Sudah Join** untuk verifikasi.",
        parse_mode='md',
        buttons=[
            [Button.inline("📢 Join Channel", data=f"open_channel_{channel}".encode())],
            [Button.inline("✅ Sudah Join", data=b"check_join")],
        ]
    )

async def process_pap_media(bot: TelegramClient, event, db: dict):
    user_id = event.sender_id
    sender = await event.get_sender()
    display_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
    username = sender.username or None

    update_user(db, user_id, display_name=display_name, username=username)

    user = get_user(db, user_id)
    if user.get("is_banned"):
        await event.reply("🚫 Kamu telah di-ban dari bot ini. Hubungi admin jika ada kesalahan.")
        pap_waiting_media.pop(user_id, None)
        return

    if not event.message.media:
        await event.reply(
            "❌ Kirim **foto atau video** ya, bukan teks biasa!\n\n"
            "Pastikan ada hashtag **#m** atau **#f** di caption.",
            parse_mode='md'
        )
        return

    caption = event.message.message or ""

    if "#m" not in caption.lower() and "#f" not in caption.lower():
        await event.reply(
            "❌ **Wajib pakai hashtag!**\n\n"
            "Tambahkan **#m** (cowok) atau **#f** (cewek) di caption kamu, lalu kirim ulang.",
            parse_mode='md'
        )
        return

    if re.search(LINK_REGEX, caption, re.IGNORECASE) or re.search(MENTION_REGEX, caption):
        await event.reply(
            "❌ **Dilarang menyertakan link atau username di caption!**\n"
            "Hapus link/username tersebut lalu kirim ulang.",
            parse_mode='md'
        )
        return

    # ── UPDATED: cek kuota dengan reset 24 jam ──
    reset_daily_if_needed(db, user_id)
    if not can_post_today(db, user_id):
        limit = get_daily_limit(db, user_id)
        premium = is_premium(db, user_id)
        sisa_waktu = get_quota_reset_remaining(db, user_id)

        if premium:
            await event.reply(
                f"⏰ **Kuota harianmu habis!**\n\n"
                f"💎 Premium limit: `{limit}x` per 24 jam\n"
                f"🔄 Kuota reset dalam: **{sisa_waktu}**\n\n"
                f"Sabar ya, sebentar lagi bisa post lagi!",
                parse_mode='md'
            )
        else:
            await event.reply(
                f"⏰ **Kuota habis!** ({limit}x per 24 jam untuk Free)\n\n"
                f"🔄 Kuota reset dalam: **{sisa_waktu}**\n\n"
                f"💎 Atau upgrade ke **Premium** untuk post lebih banyak!\n"
                f"Gunakan menu **Upgrade Premium** untuk info lebih lanjut.",
                parse_mode='md'
            )
        pap_waiting_media.pop(user_id, None)
        return

    premium = is_premium(db, user_id)
    queue_item = {
        "user_id": user_id,
        "display_name": display_name,
        "is_premium": premium,
        "caption": caption,
        "message_id": event.message.id,
        "chat_id": event.chat_id,
        "timestamp": datetime.now().isoformat()
    }

    if premium:
        db["queue_premium"].append(queue_item)
        pos_text = f"posisi #{len(db['queue_premium'])} (antrian premium)"
    else:
        db["queue_free"].append(queue_item)
        pos_text = f"posisi #{len(db['queue_free'])} (antrian umum)"

    save_db(db)

    await event.reply(
        f"✅ **Media berhasil masuk antrian!**\n\n"
        f"📍 Kamu di {pos_text}\n"
        f"⏳ Kontenmu akan segera diposting ke {PAP_CHANNEL}\n\n"
        f"{'💎 Prioritas premium aktif!' if premium else '💡 Upgrade Premium untuk antrian lebih cepat!'}",
        parse_mode='md'
    )

    pap_waiting_media.pop(user_id, None)
    logger.info(f"📥 [PAP-QUEUE] User {display_name} ({user_id}) masuk antrian {'premium' if premium else 'free'}")

async def post_from_queue(bot: TelegramClient, db: dict):
    if db["queue_premium"]:
        item = db["queue_premium"].pop(0)
    elif db["queue_free"]:
        item = db["queue_free"].pop(0)
    else:
        return False

    user_id = item["user_id"]
    premium = item["is_premium"]
    caption = item.get("caption", "")
    message_id = item["message_id"]
    chat_id = item["chat_id"]

    try:
        original_msg = await bot.get_messages(chat_id, ids=message_id)
        if not original_msg:
            logger.warning(f"⚠️ [PAP-POST] Pesan original tidak ditemukan untuk user {user_id}")
            save_db(db)
            return False

        clean_caption = caption.strip()

        if not premium:
            wm = db["settings"]["watermark_text"]
            if wm not in clean_caption:
                clean_caption = f"{clean_caption}\n\n{wm}"

        await bot.send_file(
            PAP_CHANNEL,
            file=original_msg.media,
            caption=clean_caption,
            parse_mode='md'
        )

        # ── UPDATED: pakai record_post_usage untuk tracking 24 jam ──
        reset_daily_if_needed(db, user_id)
        record_post_usage(db, user_id)

        # Reload user setelah update
        db = load_db()
        sisa = remaining_posts(db, user_id)
        db["stats"]["total_post"] = db["stats"].get("total_post", 0) + 1
        save_db(db)

        # Info reset waktu untuk notifikasi
        user = get_user(db, user_id)
        reset_info = ""
        if sisa == 0:
            sisa_waktu = get_quota_reset_remaining(db, user_id)
            reset_info = f"\n⏰ Kuota reset dalam: **{sisa_waktu}**"
        else:
            sisa_waktu = get_quota_reset_remaining(db, user_id)
            if sisa_waktu != "Sekarang":
                reset_info = f"\n🔄 Reset kuota dalam: `{sisa_waktu}`"

        await bot.send_message(
            user_id,
            f"✅ **PAP kamu berhasil diposting ke {PAP_CHANNEL}!**\n\n"
            f"📊 Sisa kuota: `{sisa}x`"
            f"{reset_info}\n"
            f"{'💎 Terima kasih sudah jadi member premium!' if premium else ''}",
            parse_mode='md',
            buttons=build_main_menu(user_id, db)
        )

        logger.info(f"✅ [PAP-POST] Berhasil post untuk user {user_id} ({'premium' if premium else 'free'})")
        return True

    except Exception as e:
        logger.error(f"❌ [PAP-POST-ERROR] Gagal post untuk user {user_id}: {e}")
        if premium:
            db["queue_premium"].insert(0, item)
        else:
            db["queue_free"].insert(0, item)
        save_db(db)
        return False

async def pap_queue_processor(bot: TelegramClient):
    await asyncio.sleep(15)
    logger.info("🚀 [PAP-QUEUE] Queue processor aktif!")
    while True:
        try:
            db = load_db()
            if db["queue_premium"] or db["queue_free"]:
                success = await post_from_queue(bot, db)
                if success:
                    db = load_db()
                    interval = db["settings"]["post_interval_premium"] if db["queue_premium"] else db["settings"]["post_interval_free"]
                    await asyncio.sleep(interval)
                else:
                    await asyncio.sleep(5)
            else:
                await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"❌ [PAP-QUEUE-LOOP] Error: {e}")
            await asyncio.sleep(10)

async def pap_backup_loop():
    while True:
        await asyncio.sleep(3600)
        backup_db()

# ─────────────────────────────────────────────────────────
# PAP BOT HANDLERS
# ─────────────────────────────────────────────────────────
def register_pap_handlers(bot: TelegramClient):

    @bot.on(events.NewMessage(pattern='/start', incoming=True, func=lambda e: e.is_private))
    async def pap_start(event):
        try:
            db = load_db()
            user_id = event.sender_id
            sender = await event.get_sender()
            display_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
            username = sender.username or None

            user = get_user(db, user_id)
            update_user(db, user_id, display_name=display_name, username=username)

            if user.get("is_banned"):
                await event.reply("🚫 Akun kamu di-ban dari bot ini.")
                raise events.StopPropagation

            joined = await check_user_joined(bot, user_id)
            if not joined:
                await send_join_prompt(bot, user_id)
                logger.info(f"👤 [PAP-START] User {display_name} ({user_id}) belum join channel")
                raise events.StopPropagation

            await pap_send_welcome(bot, user_id, display_name, username, db)
            logger.info(f"👤 [PAP-START] User {display_name} ({user_id}) start bot")
        except events.StopPropagation:
            raise
        except Exception as e:
            logger.error(f"❌ [PAP-START] {e}")
        raise events.StopPropagation

    @bot.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
    async def pap_message_handler(event):
        try:
            db = load_db()
            user_id = event.sender_id
            text = event.raw_text.strip() if event.raw_text else ""
            is_admin = user_id in ADMIN_IDS

            if text == "/start":
                return

            sender = await event.get_sender()
            display_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()

            # ── User sedang dalam mode kirim PAP ──
            if pap_waiting_media.get(user_id):
                if text in ["❌ Batal", "/cancel"]:
                    pap_waiting_media.pop(user_id, None)
                    await event.reply("❌ Pengiriman dibatalkan.", buttons=build_main_menu(user_id, db))
                    return
                if event.message.media or text not in [
                    "📤 Kirim PAP", "👤 Profil Saya", "📊 Statistik",
                    "💎 Upgrade Premium", "📋 Cara Pakai", "🔙 Kembali",
                    "👥 Daftar User", "✅ Approve Premium", "❌ Revoke Premium",
                    "🚫 Ban User", "✅ Unban User", "📤 Force Post",
                    "💾 Backup DB", "⚙️ Pengaturan", "📢 Broadcast",
                    "📊 Statistik Bot", "🗑️ Hapus Postingan", "🔄 Reset Kuota User"
                ]:
                    await process_pap_media(bot, event, db)
                    return

            # ── Menu Tombol ──
            if text.startswith("📤 Kirim PAP"):
                user = get_user(db, user_id)
                if user.get("is_banned"):
                    await event.reply("🚫 Akun kamu di-ban.")
                    return

                # Cek kuota dengan reset 24 jam
                reset_daily_if_needed(db, user_id)
                if not can_post_today(db, user_id):
                    limit = get_daily_limit(db, user_id)
                    sisa_waktu = get_quota_reset_remaining(db, user_id)
                    await event.reply(
                        f"⏰ **Kuota habis!**\n\n"
                        f"📊 Limit: `{limit}x` per 24 jam\n"
                        f"🔄 Kuota reset dalam: **{sisa_waktu}**\n\n"
                        f"{'Sabar ya kak! ✨' if is_premium(db, user_id) else '💎 Atau upgrade Premium untuk post lebih banyak!'}",
                        parse_mode='md',
                        buttons=build_main_menu(user_id, db)
                    )
                    return

                premium = is_premium(db, user_id)
                sisa = remaining_posts(db, user_id)
                pap_waiting_media[user_id] = True

                # Tampilkan info reset waktu
                user_data = get_user(db, user_id)
                reset_time_str = user_data.get("quota_reset_time")
                reset_hint = ""
                if reset_time_str:
                    sisa_waktu = get_quota_reset_remaining(db, user_id)
                    reset_hint = f"\n🔄 Reset kuota dalam: `{sisa_waktu}`"

                await event.reply(
                    f"📤 **KIRIM PAP**\n\n"
                    f"Kirim foto atau video kamu sekarang.\n\n"
                    f"⚠️ **Wajib** sertakan hashtag **#m** atau **#f** di caption!\n"
                    f"{'💎 Kamu pakai antrian premium (prioritas)' if premium else '🆓 Kamu pakai antrian free'}\n"
                    f"📊 Sisa kuota: **{sisa}x**"
                    f"{reset_hint}\n\n"
                    f"Ketik **❌ Batal** untuk membatalkan.",
                    parse_mode='md',
                    buttons=[[Button.text("❌ Batal")]]
                )

            elif text == "👤 Profil Saya":
                await pap_send_profile(bot, user_id, db)

            elif text == "📊 Statistik" or (is_admin and text == "📊 Statistik Bot"):
                await pap_send_stats(bot, user_id, db)

            elif text == "💎 Upgrade Premium":
                await pap_send_premium_info(bot, user_id, db)

            elif text == "📋 Cara Pakai":
                await pap_send_help(bot, user_id, db)

            elif text == "🔙 Kembali":
                await bot.send_message(user_id, "🏠 Menu Utama", buttons=build_main_menu(user_id, db))

            # ═══ ADMIN COMMANDS ═══
            elif is_admin and text == "👥 Daftar User":
                db = load_db()
                total = len(db["users"])
                lines = [f"👥 **DAFTAR USER** (Total: {total})\n"]
                for uid, u in list(db["users"].items())[:30]:
                    badge = "💎" if u.get("is_premium") else "🆓"
                    ban = "🚫" if u.get("is_banned") else ""
                    name = u.get("display_name") or "Unknown"
                    lines.append(f"{badge}{ban} `{uid}` — {name} | Post: {u.get('total_posts',0)}")
                if total > 30:
                    lines.append(f"\n... dan {total-30} user lainnya")
                await event.reply("\n".join(lines), parse_mode='md', buttons=build_admin_menu())

            elif is_admin and text == "💾 Backup DB":
                backup_db()
                backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith("pap_database_")])
                await event.reply(
                    f"✅ **Backup berhasil!**\n\n"
                    f"📁 Total backup tersimpan: `{len(backups)}`\n"
                    f"🕐 Terakhir: `{backups[-1] if backups else '-'}`",
                    parse_mode='md', buttons=build_admin_menu()
                )

            elif is_admin and text == "✅ Approve Premium":
                await event.reply(
                    "✅ **APPROVE PREMIUM**\n\nBalas dengan format:\n`/approve <user_id> <durasi_hari>`\n\nContoh: `/approve 123456789 30`",
                    parse_mode='md', buttons=build_admin_menu()
                )

            elif is_admin and text == "❌ Revoke Premium":
                await event.reply(
                    "❌ **REVOKE PREMIUM**\n\nBalas dengan format:\n`/revoke <user_id>`\n\nContoh: `/revoke 123456789`",
                    parse_mode='md', buttons=build_admin_menu()
                )

            elif is_admin and text == "🚫 Ban User":
                await event.reply(
                    "🚫 **BAN USER**\n\nBalas dengan format:\n`/ban <user_id>`\n\nContoh: `/ban 123456789`",
                    parse_mode='md', buttons=build_admin_menu()
                )

            elif is_admin and text == "✅ Unban User":
                await event.reply(
                    "✅ **UNBAN USER**\n\nBalas dengan format:\n`/unban <user_id>`\n\nContoh: `/unban 123456789`",
                    parse_mode='md', buttons=build_admin_menu()
                )

            elif is_admin and text == "📢 Broadcast":
                await event.reply(
                    "📢 **BROADCAST KE SEMUA USER**\n\nBalas dengan format:\n`/broadcast <pesan>`\n\nContoh: `/broadcast Halo semua! Ada update baru nih.`",
                    parse_mode='md', buttons=build_admin_menu()
                )

            elif is_admin and text == "⚙️ Pengaturan":
                db = load_db()
                s = db["settings"]
                await event.reply(
                    f"⚙️ **PENGATURAN BOT**\n\n"
                    f"🆓 Limit Free: `{s['free_daily_limit']}x/24 jam`\n"
                    f"💎 Limit Premium: `{s['premium_daily_limit']}x/24 jam`\n"
                    f"🏷️ Watermark: `{s['watermark_text']}`\n"
                    f"⏱️ Interval Free: `{s['post_interval_free']} detik`\n"
                    f"⏱️ Interval Premium: `{s['post_interval_premium']} detik`\n\n"
                    f"Gunakan command `/set <key> <value>` untuk mengubah.\n"
                    f"Key: `free_daily_limit`, `premium_daily_limit`, `watermark_text`, `post_interval_free`, `post_interval_premium`",
                    parse_mode='md', buttons=build_admin_menu()
                )

            elif is_admin and text == "📤 Force Post":
                db = load_db()
                q_total = len(db["queue_free"]) + len(db["queue_premium"])
                await event.reply(
                    f"📤 **FORCE POST**\n\n"
                    f"Antrian saat ini: `{q_total}` post\n"
                    f"└ 💎 Premium: `{len(db['queue_premium'])}`\n"
                    f"└ 🆓 Free: `{len(db['queue_free'])}`\n\n"
                    f"Gunakan `/forcepost` untuk memproses antrian sekarang.",
                    parse_mode='md', buttons=build_admin_menu()
                )

            elif is_admin and text == "🗑️ Hapus Postingan":
                await event.reply(
                    f"🗑️ **HAPUS POSTINGAN DARI CHANNEL**\n\n"
                    f"Gunakan command:\n`/delpost <message_id>`\n\n"
                    f"**Cara cari message_id:**\n"
                    f"1. Buka channel {PAP_CHANNEL}\n"
                    f"2. Klik kanan postingan → **Copy Link**\n"
                    f"3. Contoh link: `t.me/pap_clean/42` → ID-nya `42`\n\n"
                    f"Contoh penggunaan:\n`/delpost 42`\n\n"
                    f"⚠️ Hapus permanen, tidak bisa di-undo!",
                    parse_mode='md', buttons=build_admin_menu()
                )

            # ── BARU: Reset Kuota User ──
            elif is_admin and text == "🔄 Reset Kuota User":
                await event.reply(
                    f"🔄 **RESET KUOTA USER**\n\n"
                    f"Gunakan command:\n`/resetquota <user_id>`\n\n"
                    f"Untuk reset kuota semua user:\n`/resetquota all`\n\n"
                    f"Contoh:\n"
                    f"`/resetquota 123456789` — reset 1 user\n"
                    f"`/resetquota all` — reset semua user\n\n"
                    f"⚠️ Ini akan mengosongkan hitungan post dan menghapus timer reset kuota.",
                    parse_mode='md', buttons=build_admin_menu()
                )

            # ═══ ADMIN SLASH COMMANDS ═══
            elif is_admin and text.startswith("/approve "):
                parts = text.split()
                if len(parts) >= 3:
                    try:
                        target_id = int(parts[1])
                        days = int(parts[2])
                        db = load_db()
                        expiry = (datetime.now() + timedelta(days=days)).isoformat()
                        get_user(db, target_id)
                        update_user(db, target_id, is_premium=True, premium_expiry=expiry)
                        await event.reply(
                            f"✅ **Berhasil approve premium!**\n\n"
                            f"🆔 User ID: `{target_id}`\n"
                            f"📅 Durasi: `{days} hari`\n"
                            f"⏰ Expired: `{expiry[:10]}`",
                            parse_mode='md', buttons=build_admin_menu()
                        )
                        try:
                            await bot.send_message(
                                target_id,
                                f"🎉 **Selamat! Akun kamu telah di-upgrade ke PREMIUM!**\n\n"
                                f"💎 Masa aktif: **{days} hari**\n"
                                f"📅 Expired: `{expiry[:10]}`\n\n"
                                f"Nikmati fitur premium kamu!",
                                parse_mode='md', buttons=build_main_menu(target_id, db)
                            )
                        except Exception:
                            pass
                        logger.info(f"✅ [PAP-ADMIN] Approve premium user {target_id} selama {days} hari")
                    except Exception as e:
                        await event.reply(f"❌ Error: `{e}`")
                else:
                    await event.reply("❌ Format salah. Gunakan: `/approve <user_id> <durasi_hari>`")

            elif is_admin and text.startswith("/revoke "):
                parts = text.split()
                if len(parts) >= 2:
                    try:
                        target_id = int(parts[1])
                        db = load_db()
                        get_user(db, target_id)
                        update_user(db, target_id, is_premium=False, premium_expiry=None)
                        await event.reply(
                            f"✅ **Premium berhasil di-revoke!**\n🆔 User ID: `{target_id}`",
                            parse_mode='md', buttons=build_admin_menu()
                        )
                        try:
                            await bot.send_message(
                                target_id,
                                "ℹ️ Status premium kamu telah dicabut oleh admin.",
                                buttons=build_main_menu(target_id, db)
                            )
                        except Exception:
                            pass
                    except Exception as e:
                        await event.reply(f"❌ Error: `{e}`")
                else:
                    await event.reply("❌ Format salah. Gunakan: `/revoke <user_id>`")

            elif is_admin and text.startswith("/ban "):
                parts = text.split()
                if len(parts) >= 2:
                    try:
                        target_id = int(parts[1])
                        db = load_db()
                        get_user(db, target_id)
                        update_user(db, target_id, is_banned=True)
                        await event.reply(
                            f"🚫 **User berhasil di-ban!**\n🆔 User ID: `{target_id}`",
                            parse_mode='md', buttons=build_admin_menu()
                        )
                    except Exception as e:
                        await event.reply(f"❌ Error: `{e}`")
                else:
                    await event.reply("❌ Format salah. Gunakan: `/ban <user_id>`")

            elif is_admin and text.startswith("/unban "):
                parts = text.split()
                if len(parts) >= 2:
                    try:
                        target_id = int(parts[1])
                        db = load_db()
                        get_user(db, target_id)
                        update_user(db, target_id, is_banned=False)
                        await event.reply(
                            f"✅ **User berhasil di-unban!**\n🆔 User ID: `{target_id}`",
                            parse_mode='md', buttons=build_admin_menu()
                        )
                    except Exception as e:
                        await event.reply(f"❌ Error: `{e}`")
                else:
                    await event.reply("❌ Format salah. Gunakan: `/unban <user_id>`")

            elif is_admin and text.startswith("/broadcast "):
                bc_text = text[len("/broadcast "):].strip()
                if not bc_text:
                    await event.reply("❌ Tulis pesan broadcast setelah command.")
                    return
                db = load_db()
                sent_count = 0
                fail_count = 0
                prog_msg = await event.reply(f"📢 Mengirim broadcast ke {len(db['users'])} user...")
                for uid in db["users"]:
                    try:
                        await bot.send_message(int(uid), f"📢 **INFO dari Admin:**\n\n{bc_text}", parse_mode='md')
                        sent_count += 1
                        await asyncio.sleep(0.3)
                    except Exception:
                        fail_count += 1
                await prog_msg.edit(
                    f"✅ **Broadcast selesai!**\n✅ Terkirim: `{sent_count}` | ❌ Gagal: `{fail_count}`",
                    parse_mode='md'
                )

            elif is_admin and text.startswith("/forcepost"):
                db = load_db()
                q_total = len(db["queue_free"]) + len(db["queue_premium"])
                if q_total == 0:
                    await event.reply("📭 Antrian kosong, tidak ada yang perlu dipost.")
                    return
                await event.reply(f"⚡ Force posting {q_total} item dari antrian...")
                success = 0
                for _ in range(q_total):
                    db = load_db()
                    if not db["queue_free"] and not db["queue_premium"]:
                        break
                    result = await post_from_queue(bot, db)
                    if result:
                        success += 1
                    await asyncio.sleep(2)
                await event.reply(f"✅ Force post selesai! Berhasil: `{success}/{q_total}`", parse_mode='md')

            elif is_admin and text.startswith("/set "):
                parts = text.split(None, 2)
                if len(parts) == 3:
                    key, value = parts[1], parts[2]
                    db = load_db()
                    valid_keys = ["free_daily_limit", "premium_daily_limit", "watermark_text",
                                  "post_interval_free", "post_interval_premium"]
                    if key not in valid_keys:
                        await event.reply(f"❌ Key tidak valid. Pilihan: `{'`, `'.join(valid_keys)}`", parse_mode='md')
                        return
                    try:
                        if key != "watermark_text":
                            value = int(value)
                        db["settings"][key] = value
                        save_db(db)
                        await event.reply(f"✅ Pengaturan `{key}` diubah ke `{value}`", parse_mode='md')
                    except Exception as e:
                        await event.reply(f"❌ Error: `{e}`")
                else:
                    await event.reply("❌ Format: `/set <key> <value>`")

            elif is_admin and text.startswith("/delpost "):
                parts = text.split()
                if len(parts) >= 2:
                    try:
                        msg_id = int(parts[1])
                        await bot.delete_messages(PAP_CHANNEL, msg_id)
                        await event.reply(
                            f"✅ **Postingan berhasil dihapus!**\n\n"
                            f"🗑️ Message ID: `{msg_id}`\n"
                            f"📢 Channel: {PAP_CHANNEL}",
                            parse_mode='md', buttons=build_admin_menu()
                        )
                        logger.info(f"🗑️ [PAP-DEL] Admin {user_id} hapus msg_id={msg_id} dari {PAP_CHANNEL}")
                    except ValueError:
                        await event.reply("❌ Message ID harus berupa angka.\nContoh: `/delpost 42`")
                    except Exception as e:
                        await event.reply(
                            f"❌ **Gagal menghapus postingan!**\n\n"
                            f"Error: `{e}`\n\n"
                            f"Pastikan:\n"
                            f"• Message ID benar\n"
                            f"• Bot adalah admin channel {PAP_CHANNEL}\n"
                            f"• Postingan belum terlanjur dihapus manual",
                            parse_mode='md'
                        )
                else:
                    await event.reply(
                        "❌ Format salah!\n\n"
                        "Gunakan: `/delpost <message_id>`\n\n"
                        "Cara cari ID:\n"
                        "1. Buka channel, klik kanan postingan\n"
                        "2. Copy Link → ambil angka di akhir\n"
                        "Contoh: `t.me/pap_clean/42` → `/delpost 42`"
                    )

            # ── BARU: /resetquota command ──
            elif is_admin and text.startswith("/resetquota"):
                parts = text.split()
                db = load_db()

                if len(parts) < 2:
                    await event.reply(
                        "❌ Format salah!\n\nGunakan:\n"
                        "`/resetquota <user_id>` — reset 1 user\n"
                        "`/resetquota all` — reset semua user"
                    )
                    return

                target = parts[1].strip()

                if target.lower() == "all":
                    count = 0
                    for uid in db["users"]:
                        db["users"][uid]["daily_post_count"] = 0
                        db["users"][uid]["quota_reset_time"] = None
                        count += 1
                    save_db(db)
                    await event.reply(
                        f"✅ **Kuota semua user berhasil di-reset!**\n\n"
                        f"👥 Total user direset: `{count}`",
                        parse_mode='md', buttons=build_admin_menu()
                    )
                    logger.info(f"🔄 [PAP-ADMIN] Admin {user_id} reset kuota semua {count} user")
                else:
                    try:
                        target_id = int(target)
                        get_user(db, target_id)
                        update_user(db, target_id,
                            daily_post_count=0,
                            quota_reset_time=None
                        )
                        # Coba beritahu user
                        try:
                            await bot.send_message(
                                target_id,
                                "🔄 **Kuota post kamu telah di-reset oleh admin!**\n\n"
                                "Kamu bisa post lagi sekarang 🎉",
                                parse_mode='md',
                                buttons=build_main_menu(target_id, db)
                            )
                        except Exception:
                            pass
                        await event.reply(
                            f"✅ **Kuota user berhasil di-reset!**\n\n"
                            f"🆔 User ID: `{target_id}`\n"
                            f"📊 Post count dikosongkan, timer dihapus.",
                            parse_mode='md', buttons=build_admin_menu()
                        )
                        logger.info(f"🔄 [PAP-ADMIN] Admin {user_id} reset kuota user {target_id}")
                    except ValueError:
                        await event.reply("❌ User ID harus angka, atau gunakan `all` untuk semua user.")
                    except Exception as e:
                        await event.reply(f"❌ Error: `{e}`")

            elif is_admin:
                await bot.send_message(user_id, "🛠️ **Panel Admin**\nPilih menu:", parse_mode='md', buttons=build_admin_menu())

        except Exception as e:
            logger.error(f"❌ [PAP-HANDLER] {e}")

    @bot.on(events.CallbackQuery())
    async def pap_callback_handler(event):
        try:
            data = event.data
            user_id = event.sender_id
            db = load_db()

            if data == b"check_join":
                joined = await check_user_joined(bot, user_id)
                if joined:
                    await event.answer("✅ Verifikasi berhasil!", alert=False)
                    sender = await event.get_sender()
                    display_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip()
                    username = sender.username or None
                    update_user(db, user_id, display_name=display_name, username=username)
                    try:
                        await event.delete()
                    except Exception:
                        pass
                    await pap_send_welcome(bot, user_id, display_name, username, db)
                    logger.info(f"👤 [PAP-JOIN] User {display_name} ({user_id}) verified join channel")
                else:
                    await event.answer("❌ Kamu belum join channel!", alert=True)

            elif data == b"show_admin_id":
                first_admin = ADMIN_IDS[0] if ADMIN_IDS else None
                if first_admin:
                    await event.answer(f"ID Admin: {first_admin}\nCari manual di Telegram.", alert=True)
                else:
                    await event.answer("Tidak ada admin terdaftar.", alert=True)

            elif data.startswith(b"open_channel_"):
                channel = data.decode().replace("open_channel_", "")
                await event.answer(f"Buka Telegram dan join @{channel}", alert=True)

            elif data == b"back_main_menu":
                await event.answer()
                try:
                    await event.delete()
                except Exception:
                    pass
                await pap_send_welcome(bot, user_id,
                    db["users"].get(str(user_id), {}).get("display_name", "User"),
                    db["users"].get(str(user_id), {}).get("username"),
                    db
                )

        except Exception as e:
            logger.error(f"❌ [PAP-CALLBACK] {e}")

    logger.info("✅ [PAP] Semua handler PAP AUTOPOST terdaftar!")

# ─────────────────────────────────────────────────────────
# HELPER: cek apakah chat ini adalah TARGET_GROUP_ID
# ─────────────────────────────────────────────────────────
async def is_target_group(chat) -> bool:
    try:
        target = TARGET_GROUP_ID.lstrip("@").lower()
        if hasattr(chat, 'username') and chat.username:
            if chat.username.lower() == target:
                return True
        try:
            entity = await tele.get_entity(TARGET_GROUP_ID)
            if hasattr(entity, 'id') and chat.id == entity.id:
                return True
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"⚠️ [TARGET-CHECK] Error: {e}")
    return False

# ─────────────────────────────────────────────────────────
# CORE WELCOME FUNCTION
# ─────────────────────────────────────────────────────────
async def kirim_welcome(chat, user):
    global last_welcome_msg_id
    async with _welcome_lock:
        try:
            if not user:
                return
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Kawan Baru"
            template = random.choice(WELCOME_TEMPLATES)
            welcome_text = template.format(name=full_name)

            if last_welcome_msg_id is not None:
                try:
                    await tele.delete_messages(chat.id, last_welcome_msg_id)
                    logger.info(f"🗑️ [WELCOME] Welcome lama (id={last_welcome_msg_id}) dihapus.")
                except Exception as del_err:
                    logger.warning(f"⚠️ [WELCOME] Gagal hapus welcome lama: {del_err}")
                last_welcome_msg_id = None

            sent = await tele.send_message(chat.id, welcome_text, parse_mode='md')
            last_welcome_msg_id = sent.id
            logger.info(f"🎉 [WELCOME] Dikirim untuk {full_name} (msg_id={sent.id})")
        except Exception as e:
            logger.error(f"❌ [WELCOME-ERROR] {e}")

# ─────────────────────────────────────────────────────────
# HANDLER 1: Welcome via ChatAction
# ─────────────────────────────────────────────────────────
@tele.on(events.ChatAction())
async def welcome_via_chataction(event):
    try:
        if not event.user_joined and not event.user_added:
            return
        chat = await event.get_chat()
        logger.info(f"📥 [CHATACTION] user_joined={event.user_joined} | chat_id={chat.id} | username={getattr(chat, 'username', None)}")
        if not await is_target_group(chat):
            return
        user = await event.get_user()
        await kirim_welcome(chat, user)
    except Exception as e:
        logger.error(f"❌ [CHATACTION-ERROR] {e}")

# ─────────────────────────────────────────────────────────
# HANDLER 2: Welcome via NewMessage action (backup)
# ─────────────────────────────────────────────────────────
@tele.on(events.NewMessage(incoming=True))
async def welcome_via_newmessage(event):
    try:
        if not event.is_group:
            return
        action = event.message.action
        if not isinstance(action, (MessageActionChatAddUser, MessageActionChatJoinedByLink, MessageActionChatJoinedByRequest)):
            return
        chat = await event.get_chat()
        logger.info(f"📥 [NEWMSG-ACTION] action={type(action).__name__} | chat_id={chat.id}")
        if not await is_target_group(chat):
            return
        user = await event.get_sender()
        if not user and isinstance(action, MessageActionChatAddUser) and action.users:
            try:
                user = await tele.get_entity(action.users[0])
            except Exception:
                pass
        await kirim_welcome(chat, user)
    except Exception as e:
        logger.error(f"❌ [NEWMSG-ACTION-ERROR] {e}")

# ─────────────────────────────────────────────────────────
# HELPER: Kirim warning DM via bot clone
# ─────────────────────────────────────────────────────────
async def kirim_warning_via_bot(user_id: int, nama: str, count: int):
    warning_text = (
        f"Hai **{nama}** 👋. Jangan spam atau lu bakal diblokir!!\n\n"
        f"⚠️ Peringatan {count} dari {DM_MAX_WARNING} !!"
    )
    buttons = [
        [Button.inline("✅ Oke, Gak Akan Spam Lagi", data=f"agree_{user_id}"),
         Button.inline("❌ Gak Setuju", data=f"disagree_{user_id}")],
        [Button.inline("🚫 Blokir User Ini Sekarang", data=f"block_{user_id}")],
        [Button.inline(f"⚠️ Peringatan {count} dari {DM_MAX_WARNING}", data="warn_info")],
    ]

    from telethon.tl.types import InputPeerUser
    try:
        entity = await tele.get_input_entity(user_id)
        access_hash = entity.access_hash
    except Exception as e:
        logger.warning(f"⚠️ [DM-WARNING] Gagal resolve entity dari tele: {e}")
        return False

    for bot in bot_clients:
        try:
            peer = InputPeerUser(user_id=user_id, access_hash=access_hash)
            await bot.send_message(peer, warning_text, buttons=buttons, parse_mode='md')
            logger.info(f"✅ [DM-WARNING] Bot clone berhasil kirim warning ke {nama} ({user_id})")
            return True
        except Exception as e:
            logger.warning(f"⚠️ [DM-WARNING] Bot clone gagal kirim ke {user_id}: {e}")
            continue

    logger.warning(f"⚠️ [DM-WARNING] Semua bot clone gagal. Fallback ke tele tanpa tombol.")
    return False

# ─────────────────────────────────────────────────────────
# HANDLER 3: Auto DM Spam Warning
# ─────────────────────────────────────────────────────────
@tele.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def auto_dm_spam_handler(event):
    try:
        sender = await event.get_sender()
        if not sender or not isinstance(sender, User):
            return
        if sender.id in ADMIN_IDS:
            return

        text = event.raw_text.strip() if event.raw_text else ""
        is_spam = False

        if re.search(LINK_REGEX, text, re.IGNORECASE):
            is_spam = True
        if event.message.fwd_from is not None:
            is_spam = True
        if any(kw in text.lower() for kw in DM_GCAST_KEYWORDS):
            is_spam = True

        if not is_spam:
            return

        user_id = sender.id
        dm_warning_count[user_id] = dm_warning_count.get(user_id, 0) + 1
        count = dm_warning_count[user_id]
        nama = sender.first_name or "Kamu"

        logger.info(f"⚠️ [DM-SPAM] Spam dari {nama} ({user_id}) | Warning ke-{count}/{DM_MAX_WARNING}")

        if count < DM_MAX_WARNING:
            if bot_clients:
                success = await kirim_warning_via_bot(user_id, nama, count)
                if not success:
                    await event.reply(
                        f"Hai **{nama}** 👋. Jangan spam atau lu bakal diblokir!!\n\n"
                        f"⚠️ Peringatan {count} dari {DM_MAX_WARNING} !!"
                    )
            else:
                await event.reply(
                    f"Hai **{nama}** 👋. Jangan spam atau lu bakal diblokir!!\n\n"
                    f"⚠️ Peringatan {count} dari {DM_MAX_WARNING} !!"
                )
        else:
            await tele(BlockRequest(id=sender.id))
            await event.reply(
                f"🚫 **{nama}** telah diblokir otomatis karena terlalu banyak spam!\n"
                f"({DM_MAX_WARNING}/{DM_MAX_WARNING} peringatan tercapai)"
            )
            dm_warning_count.pop(user_id, None)
            logger.info(f"🚫 [DM-SPAM] {nama} ({user_id}) DIBLOKIR otomatis!")
    except Exception as e:
        logger.error(f"❌ [DM-SPAM-ERROR] {e}")

# ─────────────────────────────────────────────────────────
# HELPER: Daftarkan CallbackQuery handler ke semua bot clone
# ─────────────────────────────────────────────────────────
def register_bot_clone_handlers(bot: TelegramClient):
    @bot.on(events.CallbackQuery())
    async def bot_clone_callback_handler(event):
        try:
            data = event.data.decode()
            if data.startswith("agree_"):
                await event.answer("✅ Oke, makasih udah setuju! Jangan spam lagi ya.", alert=False)
                await event.edit(
                    event.message.text + "\n\n✅ _User menyetujui peringatan._",
                    parse_mode='md'
                )
            elif data.startswith("disagree_"):
                await event.answer("❌ Noted. Tapi tetap jangan spam ya!", alert=True)
            elif data.startswith("block_"):
                target_id = int(data.split("_")[1])
                try:
                    await tele(BlockRequest(id=target_id))
                    dm_warning_count.pop(target_id, None)
                    await event.answer("🚫 User berhasil diblokir oleh userbot!", alert=True)
                    await event.edit("🚫 User telah **diblokir manual** via tombol bot clone.")
                    logger.info(f"🚫 [DM-SPAM] User {target_id} diblokir manual via tombol bot clone.")
                except Exception as block_err:
                    await event.answer(f"❌ Gagal blokir: {block_err}", alert=True)
            elif data == "warn_info":
                await event.answer("⚠️ Ini adalah hitungan peringatan spam.", alert=True)
        except Exception as e:
            logger.error(f"❌ [BOT-CLONE-CALLBACK-ERROR] {e}")

# ─────────────────────────────────────────────────────────
# HANDLER 4: Callback tombol DM warning (fallback di tele userbot)
# ─────────────────────────────────────────────────────────
@tele.on(events.CallbackQuery())
async def dm_button_handler(event):
    try:
        data = event.data.decode()
        if data.startswith("agree_"):
            await event.answer("✅ Oke, makasih udah setuju!", alert=False)
        elif data.startswith("disagree_"):
            await event.answer("❌ Noted. Tapi tetap jangan spam ya!", alert=True)
        elif data.startswith("block_"):
            user_id = int(data.split("_")[1])
            await tele(BlockRequest(id=user_id))
            dm_warning_count.pop(user_id, None)
            await event.answer("🚫 User berhasil diblokir!", alert=True)
            await event.edit("🚫 User telah diblokir manual.")
            logger.info(f"🚫 [DM-SPAM] User {user_id} diblokir manual via tombol.")
        elif data == "warn_info":
            await event.answer("⚠️ Ini adalah hitungan peringatan spam kamu.", alert=True)
    except Exception as e:
        logger.error(f"❌ [CALLBACK-ERROR] {e}")

# ─────────────────────────────────────────────────────────
# PYROGRAM PEER RESOLVER
# ─────────────────────────────────────────────────────────
async def resolve_peer_pyro(chat_id):
    try:
        await pyro.get_chat(chat_id)
        logger.info(f"✅ [PEER-RESOLVER] Chat ID {chat_id} langsung dikenali RAM Pyrogram.")
        return True
    except Exception:
        logger.info(f"🔄 [PEER-RESOLVER] Chat ID {chat_id} belum dikenal. Memulai pemancingan dialog...")

    try:
        async for dialog in pyro.get_dialogs(limit=100):
            if dialog.chat.id == chat_id:
                logger.info(f"🎯 [PEER-RESOLVER] Sukses mendaftarkan {dialog.chat.title} ke RAM Pyrogram via dialog scan!")
                return True
    except Exception as e:
        logger.warning(f"⚠️ [PEER-RESOLVER] Gagal memancing dialog list: {e}")

    try:
        entity = await tele.get_entity(chat_id)
        if hasattr(entity, 'username') and entity.username:
            username_target = entity.username
            logger.info(f"🔗 [PEER-RESOLVER] Mengambil entitas via username @{username_target}...")
            await pyro.get_chat(username_target)
            logger.info(f"🎯 [PEER-RESOLVER] Sukses mendaftarkan @{username_target} ke RAM Pyrogram!")
            return True
    except Exception as e:
        logger.error(f"❌ [PEER-RESOLVER] Gagal total menyelesaikan peer ID: {e}")

    return False

# ─────────────────────────────────────────────────────────
# AUTO CHAT LOOP
# ─────────────────────────────────────────────────────────
async def multi_bot_chat_loop():
    if not bot_clients:
        logger.warning("⚠️ [AUTO-CHAT] List BOT_TOKENS kosong! Fitur peramai grup dinonaktifkan.")
        return

    await asyncio.sleep(20)
    logger.info(f"🤖 [AUTO-CHAT] Sukses mengaktifkan {len(bot_clients)} Bot Klonengan untuk meramaikan grup!")

    while True:
        if not bot_clients:
            logger.warning("⚠️ [AUTO-CHAT] Semua bot klonengan telah ter-banned! Menghentikan loop.")
            break

        bot_terpilih = None
        percobaan = 0
        max_percobaan = len(bot_clients)

        while percobaan < max_percobaan and bot_clients:
            try:
                bot_terpilih = random.choice(bot_clients)
                pesan_acak = random.choice(LIST_OBROLAN)
                durasi_typing = random.randint(3, 6)

                try:
                    await bot_terpilih(SetTypingRequest(
                        peer=TARGET_GROUP_ID,
                        action=SendMessageTypingAction()
                    ))
                    logger.info(f"⏳ [TYPING] Bot Clone sukses memicu status mengetik selama {durasi_typing} detik...")
                except Exception as tx:
                    err_msg = str(tx).lower()
                    if any(x in err_msg for x in ["banned", "private", "permission", "chat_write_forbidden", "write in this chat"]):
                        logger.warning(f"⚠️ [AUTO-CHAT] Bot Clone mati/banned ({tx}). Menghapus bot!")
                        if bot_terpilih in bot_clients:
                            bot_clients.remove(bot_terpilih)
                        percobaan += 1
                        continue
                    else:
                        logger.warning(f"⚠️ Gagal memicu status typing (kendala ringan): {tx}")

                await asyncio.sleep(durasi_typing)
                await bot_terpilih.send_message(TARGET_GROUP_ID, pesan_acak)
                logger.info(f"🤖 [AUTO-CHAT] Bot Clone sukses ngirim teks: '{pesan_acak}'")
                break

            except Exception as e:
                err_msg = str(e).lower()
                if any(x in err_msg for x in ["banned", "private", "permission", "chat_write_forbidden", "write in this chat"]):
                    logger.warning(f"⚠️ [AUTO-CHAT] Bot Clone mati/banned ({e}). Menghapus bot!")
                    if bot_terpilih in bot_clients:
                        bot_clients.remove(bot_terpilih)
                else:
                    logger.error(f"❌ [AUTO-CHAT ERROR] Gagal kirim chat lewat bot clone: {e}")

                percobaan += 1
                await asyncio.sleep(1)

        jeda_acak = random.randint(10, 60)
        total_jeda = AUTO_CHAT_INTERVAL + jeda_acak
        logger.info(f"💤 Cooldown loop... tidur selama {total_jeda} detik. (Sisa bot clone aktif: {len(bot_clients)})")
        await asyncio.sleep(total_jeda)

# ─────────────────────────────────────────────────────────
# HELPER: Ambil bio user
# ─────────────────────────────────────────────────────────
async def get_bio_safe(sender_id):
    try:
        full_user = await tele(GetFullUserRequest(id=sender_id))
        return full_user.full_user.about or ""
    except Exception as e:
        logger.warning(f"⚠️ [BIO-CHECK] Gagal ambil bio user {sender_id}: {e}")
        return ""

def bio_mengandung_bahaya(bio: str) -> bool:
    if not bio:
        return False
    if re.search(LINK_REGEX, bio, re.IGNORECASE):
        return True
    if re.search(MENTION_REGEX, bio):
        return True
    return False

# ─────────────────────────────────────────────────────────
# HANDLER 5: Auto Blacklist/Moderasi Grup
# ─────────────────────────────────────────────────────────
@tele.on(events.NewMessage(incoming=True))
async def auto_blacklist_gcast_handler(event):
    if not event.is_group:
        return
    try:
        chat = await event.get_chat()
        if not await is_target_group(chat):
            return
        if event.out:
            return
        if event.message.action is not None:
            return

        text = event.raw_text.strip() if event.raw_text else ""
        text_lower = text.lower()

        if re.search(LINK_REGEX, text, re.IGNORECASE):
            await event.delete()
            logger.info(f"🗑️ [LINK-LOCKDOWN] Pesan berisi link dari {event.sender_id} DIHAPUS!")
            return

        is_forwarded = event.message.fwd_from is not None
        gcast_keywords = ["gcast", "gikes", "broadcast", "ready p", "bantu up", "pm panel", "open bo"]
        has_keyword = any(kw in text_lower for kw in gcast_keywords)

        if is_forwarded or has_keyword:
            await event.delete()
            logger.info(f"🗑️ [GCAST-BL] Pesan gikes dari {event.sender_id} DIHAPUS!")
            return

        sender = await event.get_sender()
        if not sender or not hasattr(sender, 'id') or not isinstance(sender, User):
            return

        user_uname = sender.username.lower() if sender.username else ""
        if any(x in user_uname for x in ["http", "t.me", ".com", ".net", ".id", ".org", "bot"]):
            await event.delete()
            logger.info(f"🗑️ [USERNAME-BL] Pesan dari {sender.first_name} dihapus karena username mengandung link/bot!")
            return

        bio = await get_bio_safe(sender.id)
        if bio_mengandung_bahaya(bio):
            await event.delete()
            logger.info(f"🗑️ [BIO-LOCKDOWN] Pesan dari {sender.first_name} ({sender.id}) dihapus karena bio berbahaya: {bio[:100]}")
            return

    except Exception as e:
        logger.error(f"❌ [AUTO-MOD-ERROR] Gagal eksekusi pengawasan grup: {e}")

# ─────────────────────────────────────────────────────────
# HANDLER 6: Admin command (placeholder)
# ─────────────────────────────────────────────────────────
@tele.on(events.NewMessage(incoming=True))
async def admin_command_handler(event):
    if event.sender_id not in ADMIN_IDS:
        return
    if not event.raw_text:
        return

# ─────────────────────────────────────────────────────────
# HANDLER 7: Outgoing userbot commands (. prefix)
# ─────────────────────────────────────────────────────────
@tele.on(events.NewMessage(outgoing=True))
async def handler(event):
    if not event.raw_text:
        return

    text = event.raw_text.strip()

    if text.startswith("ℹ️ **DETAILED") or text.startswith("🏓 Pong!") or text.startswith("👋 Berhasil") or text.startswith("✅ Berhasil") or text.startswith("📢 **[BROADCAST PROGRESS]**") or text.startswith("📢 **[BROADCAST GRUP PROGRESS]**"):
        return

    if not text.startswith("."):
        return

    logger.info(f"🔥 Perintah Masuk: {text!r} | Chat ID: {event.chat_id}")

    if text == ".ping":
        start = time.monotonic()
        sent = await event.respond("🏓 Mengukur...")
        ms = round((time.monotonic() - start) * 1000)
        await sent.edit(f"🏓 Pong! `{ms}ms`")

    elif text == ".jvc":
        chat_id = event.chat_id
        try:
            await resolve_peer_pyro(chat_id)
            await call.play(chat_id, MediaStream("anullsrc", ffmpeg_parameters="-f lavfi"))
            await event.respond("✅ Berhasil join ke obrolan suara!")
        except Exception as e:
            logger.error(f"join error: {e}")
            await event.respond(f"❌ Gagal join: `{e}`")

    elif text == ".leave":
        chat_id = event.chat_id
        try:
            await call.leave_call(chat_id)
            await asyncio.sleep(0.5)
            await event.respond("👋 Berhasil keluar dari obrolan suara!")
            logger.info(f"👉 [LEAVE SUCCESS] Keluar normal dari {chat_id}")
        except Exception as e:
            logger.warning(f"Pytgcalls leave error ({e}). Menjalankan FORCE DISCONNECT...")
            try:
                import pyrogram
                peer = await pyro.resolve_peer(chat_id)
                full_chat = await pyro.invoke(
                    pyrogram.raw.functions.channels.GetFullChannel(channel=peer)
                    if chat_id < 0 and str(chat_id).startswith("-100")
                    else pyrogram.raw.functions.messages.GetFullChat(chat_id=abs(chat_id))
                )
                call_info = full_chat.full_chat.call
                if call_info:
                    input_call = InputGroupCall(id=call_info.id, access_hash=call_info.access_hash)
                    await pyro.invoke(LeaveGroupCall(call=input_call, source=0))
                    await event.respond("👋 Force Disconnect: Berhasil dipaksa keluar via raw API Telegram!")
                else:
                    await event.respond("👋 Bot sudah tidak ada di dalam call.")
            except Exception as ex:
                logger.error(f"Force leave fatal error: {ex}")
                await event.respond(f"❌ Gagal total untuk leave: `{ex}`")
        finally:
            for cache_attr in ['_active_calls', 'active_calls']:
                if hasattr(call, cache_attr):
                    try: getattr(call, cache_attr).remove(chat_id)
                    except: pass

    elif text.startswith(".info"):
        parts = text.split(" ", 1)
        user_obj = None
        target_id = None

        sent = await event.respond("🔍 Membongkar database profil target...")
        try:
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                target_id = reply_msg.sender_id
            elif len(parts) > 1:
                target_raw = parts[1].strip()
                if target_raw.isdigit():
                    target_id = int(target_raw)
                else:
                    try:
                        user_obj = await tele.get_entity(target_raw)
                        target_id = user_obj.id
                    except Exception:
                        target_id = target_raw
            else:
                user_obj = await tele.get_me()
                target_id = user_obj.id

            if not user_obj and not event.is_private:
                try:
                    await tele.get_participants(event.chat_id, limit=200)
                except Exception as sync_err:
                    logger.warning(f"Gagal sinkronisasi grup: {sync_err}")

            if not user_obj:
                try:
                    user_obj = await tele.get_entity(target_id)
                except Exception:
                    try:
                        pyro_user = await pyro.get_users(target_id)
                        user_obj = await tele.get_entity(pyro_user.id)
                    except Exception:
                        user_obj = None

            if not user_obj:
                await sent.edit("❌ **Gagal mengambil entitas target!**")
                return

            full_user = await tele(GetFullUserRequest(id=user_obj.id))
            photos = await tele.get_profile_photos(user_obj.id, limit=0)

            full_name = f"{user_obj.first_name or ''} {user_obj.last_name or ''}".strip()
            username = f"@{user_obj.username}" if user_obj.username else "Tidak Ada"
            bio = full_user.full_user.about or "Kosong"
            is_premium_tg = "Iya (Premium) ✨" if user_obj.premium else "Tidak (Gratisan)"
            is_bot = "Iya 🤖" if user_obj.bot else "Bukan (User Biasa) 👤"
            is_scam = "⚠️ YA (Terdeteksi Penipu!)" if user_obj.scam else "Aman (Bersih) ✅"
            is_fake = "⚠️ YA (Akun Palsu!)" if user_obj.fake else "Asli ✅"
            dc_id = user_obj.photo.dc_id if user_obj.photo else "Tidak Diketahui"

            from telethon.tl.types import UserStatusOnline, UserStatusOffline, UserStatusRecently, UserStatusLastWeek
            status_text = "Disembunyikan 🔒"
            if isinstance(user_obj.status, UserStatusOnline): status_text = "Online Sekarang 🟢"
            elif isinstance(user_obj.status, UserStatusOffline): status_text = f"Offline sejak {user_obj.status.was_online.strftime('%Y-%m-%d %H:%M:%S')} UTC 🔴"
            elif isinstance(user_obj.status, UserStatusRecently): status_text = "Baru-baru ini online 🟡"
            elif isinstance(user_obj.status, UserStatusLastWeek): status_text = "Terakhir online seminggu lalu ⚪"

            group_status = "Bukan di dalam grup"
            if not event.is_private:
                try:
                    participant = await tele.get_permissions(event.chat_id, user_obj.id)
                    if participant.is_creator: group_status = "Pemilik Grup (Creator) 👑"
                    elif participant.is_admin: group_status = f"Admin Grup 🛠️ (Custom Title: {participant.title or 'Ga ada'})"
                    else: group_status = "Member Biasa 👤"
                except Exception:
                    group_status = "Member Biasa / Hidden Admin 👤"

            info_text = (
                f"ℹ️ **DETAILED USER INFORMATION**\n"
                f"──────────────────────────────\n"
                f"👤 **Nama Lengkap:** `{full_name}`\n"
                f"🆔 **User ID:** `{user_obj.id}`\n"
                f"🏷️ **Username:** {username}\n"
                f"🌐 **Data Center (DC):** `DC-{dc_id}`\n"
                f"──────────────────────────────\n"
                f"📊 **Jabatan di Grup Ini:**\n"
                f"└─ `{group_status}`\n\n"
                f"⏱️ **Status Keaktifan:**\n"
                f"└─ `{status_text}`\n\n"
                f"🔒 **Aspek Keamanan & Fitur:**\n"
                f"├─ Premium: {is_premium_tg}\n"
                f"├─ Akun Bot: {is_bot}\n"
                f"├─ Status Scam: {is_scam}\n"
                f"└─ Status Fake: {is_fake}\n\n"
                f"📸 **Jumlah Foto Profil:** `{len(photos)} foto`\n"
                f"📝 **Bio/About:**\n"
                f"`{bio}`\n"
                f"──────────────────────────────\n"
                f"🔗 **Link DM Instan:** [Klik Disini](tg://user?id={user_obj.id})"
            )
            await sent.edit(info_text, link_preview=False)
        except Exception as e:
            await sent.edit(f"❌ **Gagal membongkar info detil:** `{e}`")

    elif text.startswith(".bc"):
        parts = text.split(" ", 1)
        bc_msg = parts[1].strip() if len(parts) > 1 else ""
        broadcast_content = None
        is_media = False

        if event.is_reply:
            broadcast_content = await event.get_reply_message()
            is_media = True
            if bc_msg: broadcast_content.message = bc_msg
        else:
            if not bc_msg:
                await event.respond("❌ **Gagal:** Masukkan pesan setelah perintah!")
                return
            broadcast_content = bc_msg

        sent = await event.respond("📢 **[BROADCAST GRUP]** Mengumpulkan daftar grup aktif...")
        success_count = 0
        fail_count = 0
        start_time = time.monotonic()

        try:
            dialogs = await tele.get_dialogs()
        except Exception as e:
            await sent.edit(f"❌ **Gagal memuat daftar chat:** `{e}`")
            return

        targets = [d for d in dialogs if d.is_group]
        total_targets = len(targets)

        if total_targets == 0:
            await sent.edit("❌ **Gagal:** Tidak ada grup terdeteksi.")
            return

        for index, target in enumerate(targets, start=1):
            try:
                if is_media: await tele.send_message(target.id, broadcast_content)
                else: await tele.send_message(target.id, broadcast_content, link_preview=False)
                success_count += 1

                if index % 3 == 0 or index == total_targets:
                    progress_text = (
                        f"📢 **[BROADCAST GRUP PROGRESS]**\n"
                        f"🔄 Progress: `{index}/{total_targets}` grup\n"
                        f"✅ Sukses: `{success_count}` | ❌ Gagal: `{fail_count}`"
                    )
                    try: await sent.edit(progress_text)
                    except Exception: pass
                await asyncio.sleep(0.6)
            except FloodWaitError as flood:
                await asyncio.sleep(flood.seconds + 2)
                success_count += 1
            except Exception:
                fail_count += 1
                continue

        duration = round(time.monotonic() - start_time)
        report_text = (
            f"✅ **BROADCAST GRUP SELESAI LENGKAP**\n"
            f"📊 **Total Target:** `{total_targets} grup`\n"
            f"✨ **Berhasil:** `{success_count}` | ❌ **Gagal:** `{fail_count}`\n"
            f"⏱️ **Waktu:** `{duration} detik`"
        )
        try: await sent.edit(report_text)
        except Exception: await event.respond(report_text)

# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────
async def main():
    global call, pyro, bot_clients, pap_bot
    logger.info("🚀 Starting Engines...")

    # ── Bot Clone untuk auto-chat & DM warning ──
    for idx, token in enumerate(BOT_TOKENS, start=1):
        try:
            b_client = TelegramClient(f'bot_session_{idx}', API_ID, API_HASH)
            await b_client.start(bot_token=token)
            register_bot_clone_handlers(b_client)
            bot_clients.append(b_client)
            logger.info(f"✅ Bot Clone Ke-{idx} Sukses Terkoneksi + Handler Terdaftar!")
        except Exception as e:
            logger.error(f"❌ Gagal menyalakan Bot Clone ke-{idx}: {e}")

    if bot_clients:
        asyncio.create_task(multi_bot_chat_loop())

    # ── PAP AUTOPOST Bot ──
    if PAP_BOT_TOKEN:
        try:
            pap_bot = TelegramClient('pap_bot_session', API_ID, API_HASH)
            await pap_bot.start(bot_token=PAP_BOT_TOKEN)
            register_pap_handlers(pap_bot)
            asyncio.create_task(pap_queue_processor(pap_bot))
            asyncio.create_task(pap_backup_loop())
            me_pap = await pap_bot.get_me()
            logger.info(f"✅ [PAP-BOT] Aktif sebagai @{me_pap.username}")
        except Exception as e:
            logger.error(f"❌ [PAP-BOT] Gagal menyalakan PAP bot: {e}")
    else:
        logger.warning("⚠️ [PAP-BOT] PAP_BOT_TOKEN tidak ditemukan, fitur PAP AUTOPOST dinonaktifkan.")

    # ── Pyrogram + PyTgCalls ──
    pyro = PyroClient(
        name="voice",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=PYRO_SESS,
        no_updates=True
    )
    call = PyTgCalls(pyro)
    await pyro.start()
    await call.start()
    logger.info("✅ PyTgCalls Engine ready")

    logger.info("🔄 Menyinkronkan daftar obrolan Pyrogram ke RAM...")
    try:
        async for dialog in pyro.get_dialogs(limit=100): pass
        logger.info("✅ Sinkronisasi RAM MemoryStorage sukses!")
    except Exception as e:
        logger.warning(f"⚠️ Gagal menyinkronkan obrolan di awal: {e}")

    # ── Userbot Telethon ──
    await tele.start()
    me = await tele.get_me()
    logger.info(f"🤖 Login Terverifikasi: {me.first_name} (@{me.username})")
    await tele.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
