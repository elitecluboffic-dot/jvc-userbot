import os
import time
import asyncio
import random
import logging
import re
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.messages import SetTypingRequest, DeleteMessagesRequest
from telethon.tl.types import SendMessageTypingAction, Dialog, Channel, Chat, User
from telethon.errors import FloodWaitError
from pyrogram import Client as PyroClient
from pyrogram.raw.functions.phone import LeaveGroupCall
from pyrogram.raw.types import InputGroupCall
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

# Ambil Config Utama dari Railway Env
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
TELE_SESS = os.getenv("SESSION_STRING_1", "").strip()
PYRO_SESS = os.getenv("PYRO_SESSION", "").strip()

# Ambil list token bot klonengan (Dipisahkan pakai tanda koma di Railway Env)
RAW_TOKENS = os.getenv("BOT_TOKENS", "").strip()
BOT_TOKENS = [t.strip() for t in RAW_TOKENS.split(",") if t.strip()]

# =====================================================================
# ⚠️ PENGATURAN GRUP & BACOTAN SUPER RANDOM (NO CRYPTO)
# =====================================================================
TARGET_GROUP_ID = "@CARI_CRUSH_ONLINE"  # ID/Username grup tujuan lu
AUTO_CHAT_INTERVAL = 600          # Jeda kirim chat (600 detik = 10 menit sekali)

# Regex untuk mencium keberadaan link di bio profil pengguna
LINK_REGEX = r'(https?://[^\s]+|t\.me/[^\s]+|www\.[^\s]+)'

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
# =====================================================================

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

logging.getLogger("telethon.extensions.html").setLevel(logging.WARNING)
logging.getLogger("telethon.network.mtprotosender").setLevel(logging.WARNING)
logging.getLogger("pyrogram.client").setLevel(logging.WARNING)
logging.getLogger("pyrogram.session").setLevel(logging.WARNING)

# Klien Utama (Userbot Akun Lu @bitcoinbim)
tele = TelegramClient(StringSession(TELE_SESS), API_ID, API_HASH)
pyro = None
call = None
bot_clients = []

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
        sukses = False
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
                        logger.warning(f"⚠️ [AUTO-CHAT] Bot Clone mati/banned saat mengetik ({tx}). Menghapus bot!")
                        if bot_terpilih in bot_clients:
                            bot_clients.remove(bot_terpilih)
                        percobaan += 1
                        continue
                    else:
                        logger.warning(f"⚠️ Gagal memicu status typing (kendala ringan): {tx}")
                
                await asyncio.sleep(durasi_typing)
                await bot_terpilih.send_message(TARGET_GROUP_ID, pesan_acak)
                logger.info(f"🤖 [AUTO-CHAT] Bot Clone sukses ngirim teks: '{pesan_acak}'")
                sukses = True
                break 
                
            except Exception as e:
                err_msg = str(e).lower()
                if any(x in err_msg for x in ["banned", "private", "permission", "chat_write_forbidden", "write in this chat"]):
                    logger.warning(f"⚠️ [AUTO-CHAT] Bot Clone mati/banned saat kirim chat ({e}). Menghapus bot!")
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


# ==================== 🔥 HANDLER AUTO BLACKLIST GCAST & LINK BIO 🔥 ====================
@tele.on(events.NewMessage(incoming=True))
async def auto_blacklist_gcast_handler(event):
    if not event.is_group:
        return
        
    try:
        chat = await event.get_chat()
        chat_username = f"@{chat.username}" if hasattr(chat, 'username') and chat.username else ""
        
        if TARGET_GROUP_ID.lower() != chat_username.lower():
            return # Skip kalau bukan di grup @CARI_CRUSH_ONLINE
            
        if event.out:
            return

        # -------------------------------------------------------------
        # 1. AKSI DETEKSI GCAST / GIKES JAHANAM
        # -------------------------------------------------------------
        text = event.raw_text.strip().lower() if event.raw_text else ""
        is_forwarded = event.message.fwd_from is not None
        gcast_keywords = ["gcast", "gikes", "broadcast", "ready p", "bantu up", "pm panel", "open bo"]
        has_keyword = any(kw in text for kw in gcast_keywords)
        
        if is_forwarded or has_keyword:
            await tele(DeleteMessagesRequest(id=[event.message.id], revoke=True))
            logger.info(f"🗑️ [AUTO-BL-GCAST] Berhasil menghapus pesan gikes dari Sender ID: {event.sender_id}")
            return # Selesai, ga perlu lanjut cek bio lagi kalau chatnya udah tewas

        # -------------------------------------------------------------
        # 2. AKSI DETEKSI LINK DI BIO PROFIL PENGGUNA (SILENT DELETE)
        # -------------------------------------------------------------
        sender = await event.get_sender()
        if sender and hasattr(sender, 'id') and isinstance(sender, User):
            # Ambil data profil lengkap sang pengirim untuk dibongkar bionya
            full_user = await tele(GetFullUserRequest(id=sender.id))
            bio = full_user.full_user.about
            
            # Jika user punya bio dan bionya terbukti memuat link aktif
            if bio and re.search(LINK_REGEX, bio, re.IGNORECASE):
                await tele(DeleteMessagesRequest(id=[event.message.id], revoke=True))
                logger.info(f"🗑️ [AUTO-DEL-BIO] Pesan dari {sender.first_name} ({sender.id}) dihapus senyap karena ada link di bio: {bio}")

    except Exception as e:
        logger.error(f"❌ [AUTO-MOD-ERROR] Gagal eksekusi pengawasan grup: {e}")


# ==================== HANDLER COMMAND USERBOT LU (@bitcoinbim) ====================
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

    # ==================== PERINTAH PING ====================
    if text == ".ping":
        start = time.monotonic()
        sent = await event.respond("🏓 Mengukur...")
        ms = round((time.monotonic() - start) * 1000)
        await sent.edit(f"🏓 Pong! `{ms}ms`")

    # ==================== PERINTAH JOIN VC ====================
    elif text == ".jvc":
        chat_id = event.chat_id
        try:
            await resolve_peer_pyro(chat_id)
            await call.play(
                chat_id,
                MediaStream("anullsrc", ffmpeg_parameters="-f lavfi"),
            )
            await event.respond("✅ Berhasil join ke obrolan suara!")
        except Exception as e:
            logger.error(f"join error: {e}")
            await event.respond(f"❌ Gagal join: `{e}`")

    # ==================== PERINTAH LEAVE VC ====================
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

    # ==================== PERINTAH INFO (SUPER DETAIL) ====================
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
                logger.info(f"🔄 Sinkronisasi ulang member grup {event.chat_id} untuk memancing ID {target_id}...")
                try: await tele.get_participants(event.chat_id, limit=200)
                except Exception as sync_err: logger.warning(f"Gagal sinkronisasi grup: {sync_err}")

            if not user_obj:
                try: user_obj = await tele.get_entity(target_id)
                except Exception:
                    try:
                        pyro_user = await pyro.get_users(target_id)
                        user_obj = await tele.get_entity(pyro_user.id)
                    except Exception: user_obj = None

            if not user_obj:
                await sent.edit("❌ **Gagal mengambil entitas target!**")
                return

            full_user = await tele(GetFullUserRequest(id=user_obj.id))
            photos = await tele.get_profile_photos(user_obj.id, limit=0)
            
            full_name = f"{user_obj.first_name or ''} {user_obj.last_name or ''}".strip()
            username = f"@{user_obj.username}" if user_obj.username else "Tidak Ada"
            bio = full_user.full_user.about or "Kosong"
            is_premium = "Iya (Premium) ✨" if user_obj.premium else "Tidak (Gratisan)"
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
                "ℹ️ **DETAILED USER INFORMATION**\n"
                "──────────────────────────────\n"
                "👤 **Nama Lengkap:** `{full_name}`\n"
                "🆔 **User ID:** `{user_obj.id}`\n"
                "🏷️ **Username:** {username}\n"
                "🌐 **Data Center (DC):** `DC-{dc_id}`\n"
                "──────────────────────────────\n"
                "📊 **Jabatan di Grup Ini:**\n"
                "└─ `{group_status}`\n\n"
                "⏱️ **Status Keaktifan:**\n"
                "└─ `{status_text}`\n\n"
                "🔒 **Aspek Keamanan & Fitur:**\n"
                "├─ Premium: {is_premium}\n"
                "├─ Akun Bot: {is_bot}\n"
                "├─ Status Scam: {is_scam}\n"
                "└─ Status Fake: {is_fake}\n\n"
                f"📸 **Jumlah Foto Profil:** `{len(photos)} foto`\n"
                "📝 **Bio/About:**\n"
                f"`{bio}`\n"
                "──────────────────────────────\n"
                f"🔗 **Link DM Instan:** [Klik Disini](tg://user?id={user_obj.id})"
            )
            await sent.edit(info_text, link_preview=False)
        except Exception as e:
            await sent.edit(f"❌ **Gagal membongkar info detil:** `{e}`")

    # ==================== PERINTAH BROADCAST KHUSUS GRUP ====================
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
        
        try: dialogs = await tele.get_dialogs()
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
            "✅ **BROADCAST GRUP SELESAI LENGKAP**\n"
            f"📊 **Total Target:** `{total_targets} grup`\n"
            f"✨ **Berhasil:** `{success_count}` | ❌ **Gagal:** `{fail_count}`\n"
            f"⏱️ **Waktu:** `{duration} detik`"
        )
        try: await sent.edit(report_text)
        except Exception: await event.respond(report_text)


async def main():
    global call, pyro, bot_clients
    logger.info("🚀 Starting Engines...")
    
    for idx, token in enumerate(BOT_TOKENS, start=1):
        try:
            b_client = TelegramClient(f'bot_session_{idx}', API_ID, API_HASH)
            await b_client.start(bot_token=token)
            bot_clients.append(b_client)
            logger.info(f"✅ Bot Clone Ke-{idx} Sukses Terkoneksi!")
        except Exception as e:
            logger.error(f"❌ Gagal menyalakan Bot Clone ke-{idx}: {e}")
            
    if bot_clients:
        asyncio.create_task(multi_bot_chat_loop())
        
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
    
    await tele.start()
    me = await tele.get_me()
    logger.info(f"🤖 Login Terverifikasi: {me.first_name} (@{me.username})")
    await tele.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
