import os
import time
import asyncio
import random
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.messages import SetTypingRequest
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
TARGET_GROUP_ID = "@CARI_CRUSH_ONLINE"  # ID grup tujuan lu (CARI_CRUSH_ONLINE)
AUTO_CHAT_INTERVAL = 600          # Jeda kirim chat (600 detik = 10 menit sekali)

LIST_OBROLAN = [
    # --- Sapaan / Absen / Nyari Temen Chat ---
    "p",
    "P",
    "gimana gess? aman semua kan?",
    "sepi amat dah wkwk pada ke mana nih orang-orang",
    "gess absen dulu dong yang lagi online jam segini 👋",
    "hadir gess, baru mantau lagi nih",
    "ada yang lagi free gak? nemenin ngobrol sini",
    "halo semuanya, selamat beraktivitas ya gess",
    "ooii bro, lagi pada sibuk ya?",
    "yuk ramein yuk, jangan biarkan grup ini mati suri 😂",
    "turu kabeeh ta iki? 😴",
    
    # --- Topik Game / Main Bareng (Mabar) ---
    "mabar gak nih gess? gabut bener gua asli",
    "ada yang main ml gak? login lah gass full team",
    "bntr lagi reset season ya? pusing gua dapet tim publik ampas mulu",
    "ada rekomendasi game offline yang seru gak di HP? mau nyoba",
    "pubg gass lah, ketik 1 yang mau ikut ngerush",
    "hoki bener gua tadi malem main game wkwk",
    "lagi males main game kompetitif, bikin emosi doang wkwk",
    
    # --- Topik Film / Netflix / Sosmed ---
    "ada rekomendasi film bagus gak di netflix? yang genrenya thriller/horor",
    "eh beneran film yang kemarin rame itu seru? mau nonton tapi mager",
    "lagi rame banget ya di tiktok masalah itu, ada yang ngikutin?",
    "rekomendasi series yang sekali duduk langsung tamat dong gess",
    "capek banget scrol sosmed isinya drama mulu wkwk",
    
    # --- Topik Kopi / Makan / Nongkrong / Cuaca ---
    "ngopi dulu gess biar ga panik batin☕",
    "cuaca di tempat kalian gimana? tempat gua ujan deras bener",
    "enaknya jam segini makan apa ya? rekomendasi kuliner dong",
    "rekomendasi tempat nongkrong yang free wifi dan kopinya enak dong gess",
    "laper bener bjir, padahal tadi udah makan",
    "es teh manis emang paling juara sih kalau cuaca lagi panas gini",
    "pada suka kopi hitam apa kopi susu nih gess?",
    
    # --- Respon Pendek / Khas Anak Tongkrongan ---
    "wkwk gokil sih emang",
    "gas lah ga pake lama",
    "yoii bro santai aja haha",
    "seriusan lu? wkwk",
    "skip dulu deh kalo itu wkwk",
    "mantap jaya 🔥",
    "up dulu lah biar ga tenggelam nih grup 🚀",
    "males ngetik panjang, intinya gas aja lah wkwk",
    "bisa gitu ya wkwkwk",
    "nah eta!",
    "aman aman aman 👍",
    "oke siap gas",
    "wkwkwk joss lah",
    "bener juga sih",
    "lah iya kah?",
    "wkwk parah sih",
    "bisa jadi, bisa jadi 🤔",
    "walah wkwk",
    "gasskeun!",
    
    # --- Topik Gabut / Random Banget ---
    "enaknya jam segini ngapain ya? gabut bener asli",
    "jaringan lagi rada ngadat nih tempat gua, pantesan agak telat bales",
    "ada yang lagi dengerin musik gak? bagi judul lagu yang enak dong",
    "ngantuk bener bjir, padahal semalem tidur cepet",
    "capek-capek kerja, ujung-undunya duitnya habis buat jajan doang wkwk",
    "random bener pikiran gua jam segini wkwk",
    "hidup lagi capek-capeknya, malah nemu ginian wkwk"
]
# =====================================================================

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Membungkam log update internal Telethon & Pyrogram agar log Railway mulus
logging.getLogger("telethon.extensions.html").setLevel(logging.WARNING)
logging.getLogger("telethon.network.mtprotosender").setLevel(logging.WARNING)
logging.getLogger("pyrogram.client").setLevel(logging.WARNING)
logging.getLogger("pyrogram.session").setLevel(logging.WARNING)

# Klien Utama (Userbot Akun Lu @bitcoinbim)
tele = TelegramClient(StringSession(TELE_SESS), API_ID, API_HASH)
pyro = None
call = None

# List untuk menampung semua bot klonengan yang aktif
bot_clients = []

# Loop Otomatis - DIKENDALIKAN OLEH BOT-BOT CLONE SECARA ACAK
async def multi_bot_chat_loop():
    if not bot_clients:
        logger.warning("⚠️ [AUTO-CHAT] List BOT_TOKENS kosong! Fitur peramai grup dinonaktifkan.")
        return
        
    await asyncio.sleep(20) # Jeda aman nunggu semua mesin nyala sempurna
    logger.info(f"🤖 [AUTO-CHAT] Sukses mengaktifkan {len(bot_clients)} Bot Klonengan untuk meramaikan grup!")
    
    while True:
        if not bot_clients:
            logger.warning("⚠️ [AUTO-CHAT] Semua bot klonengan telah ter-banned atau tidak memiliki akses grup! Menghentikan loop.")
            break
            
        bot_terpilih = None
        sukses = False
        percobaan = 0
        max_percobaan = len(bot_clients)
        
        # Lakukan pencarian bot clone sehat sampai berhasil mengirim pesan
        while percobaan < max_percobaan and bot_clients:
            try:
                bot_terpilih = random.choice(bot_clients)
                pesan_acak = random.choice(LIST_OBROLAN)
                durasi_typing = random.randint(3, 6)
                
                # Coba kirim typing
                try:
                    await bot_terpilih(SetTypingRequest(
                        peer=TARGET_GROUP_ID,
                        action=SendMessageTypingAction()
                    ))
                    logger.info(f"⏳ [TYPING] Bot Clone sukses memicu status mengetik selama {durasi_typing} detik...")
                except Exception as tx:
                    err_msg = str(tx).lower()
                    if "banned" in err_msg or "private" in err_msg or "permission" in err_msg or "chat_write_forbidden" in err_msg or "write in this chat" in err_msg:
                        logger.warning(f"⚠️ [AUTO-CHAT] Bot Clone terdeteksi mati/banned saat mengetik ({tx}). Menghapus bot dari antrean aktif!")
                        if bot_terpilih in bot_clients:
                            bot_clients.remove(bot_terpilih)
                        percobaan += 1
                        continue # Langsung cari bot lain tanpa sleep panjang
                    else:
                        logger.warning(f"⚠️ Gagal memicu status typing (kendala ringan): {tx}")
                
                # Tahan proses selama durasi mengetik biar terlihat natural
                await asyncio.sleep(durasi_typing)
                
                # Kirim pesan asli setelah efek typing selesai
                await bot_terpilih.send_message(TARGET_GROUP_ID, pesan_acak)
                logger.info(f"🤖 [AUTO-CHAT] Bot Clone sukses ngirim teks: '{pesan_acak}'")
                sukses = True
                break # Sukses! Keluar dari loop pencarian bot
                
            except Exception as e:
                err_msg = str(e).lower()
                if "banned" in err_msg or "private" in err_msg or "permission" in err_msg or "chat_write_forbidden" in err_msg or "write in this chat" in err_msg:
                    logger.warning(f"⚠️ [AUTO-CHAT] Bot Clone terdeteksi mati/banned saat kirim chat ({e}). Menghapus bot dari antrean aktif!")
                    if bot_terpilih in bot_clients:
                        bot_clients.remove(bot_terpilih)
                else:
                    logger.error(f"❌ [AUTO-CHAT ERROR] Gagal kirim chat lewat bot clone: {e}")
                
                percobaan += 1
                await asyncio.sleep(1) # Jeda kilat sebelum rolling ke bot selanjutnya
                
        # Kasih bumbu jeda acak harian biar waktunya bervariasi
        jeda_acak = random.randint(10, 60)
        total_jeda = AUTO_CHAT_INTERVAL + jeda_acak
        logger.info(f"💤 Cooldown loop... tidur selama {total_jeda} detik. (Sisa bot klonengan aktif: {len(bot_clients)})")
        await asyncio.sleep(total_jeda)


# ==================== HANDLER COMMAND USERBOT LU (@bitcoinbim) ====================
@tele.on(events.NewMessage(outgoing=True))
async def handler(event):
    if not event.raw_text:
        return
        
    text = event.raw_text.strip()
    
    # Supaya bot ga ngerespon balik hasil editannya sendiri
    if text.startswith("ℹ️ **DETAILED") or text.startswith("🏓 Pong!") or text.startswith("👋 Berhasil") or text.startswith("✅ Berhasil") or text.startswith("📢 **[BROADCAST PROGRESS]**") or text.startswith("📢 **[BROADCAST GRUP PROGRESS]**"):
        return

    # Bot HANYA memproses pesan yang diawali tanda titik
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
            # === TRIK JITU: Pancing entitas ke database lokal Pyrogram saat runtime ===
            try:
                # Dapatkan entitas grup menggunakan Telethon (yang cachenya lengkap)
                input_entity = await tele.get_input_entity(chat_id)
                # Paksa masukkan entitas tersebut ke SQLite Pyrogram agar di-resolve instan
                await pyro.storage.save_peer(
                    chat_id,
                    input_entity.access_hash,
                    "channel" if str(chat_id).startswith("-100") else "chat"
                )
                logger.info(f"✅ [PEER-RESOLVER] Berhasil mendaftarkan ID {chat_id} ke database Pyrogram.")
            except Exception as pe:
                logger.warning(f"⚠️ [PEER-RESOLVER] Gagal sinkronisasi otomatis entitas grup: {pe}")

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
                try:
                    await tele.get_participants(event.chat_id, limit=200)
                except Exception as sync_err:
                    logger.warning(f"Gagal melakukan sinkronisasi otomatis grup: {sync_err}")

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
                await sent.edit("❌ **Gagal mengambil entitas target!** Akun target tidak merespon sistem sinkronisasi grup.")
                return

            full_user = await tele(GetFullUserRequest(id=user_obj.id))
            photos = await tele.get_profile_photos(user_obj.id, limit=0)
            
            first_name = user_obj.first_name or ""
            last_name = user_obj.last_name or ""
            full_name = f"{first_name} {last_name}".strip()
            username = f"@{user_obj.username}" if user_obj.username else "Tidak Ada"
            bio = full_user.full_user.about or "Kosong"
            
            is_premium = "Iya (Premium) ✨" if user_obj.premium else "Tidak (Gratisan)"
            is_bot = "Iya 🤖" if user_obj.bot else "Bukan (User Biasa) 👤"
            is_scam = "⚠️ YA (Terdeteksi Penipu!)" if user_obj.scam else "Aman (Bersih) ✅"
            is_fake = "⚠️ YA (Akun Palsu!)" if user_obj.fake else "Asli ✅"
            dc_id = user_obj.photo.dc_id if user_obj.photo else "Tidak Diketahui"
            
            from telethon.tl.types import UserStatusOnline, UserStatusOffline, UserStatusRecently, UserStatusLastWeek
            status_text = "Disembunyikan 🔒"
            if isinstance(user_obj.status, UserStatusOnline):
                status_text = "Online Sekarang 🟢"
            elif isinstance(user_obj.status, UserStatusOffline):
                status_text = f"Offline sejak {user_obj.status.was_online.strftime('%Y-%m-%d %H:%M:%S')} UTC 🔴"
            elif isinstance(user_obj.status, UserStatusRecently):
                status_text = "Baru-baru ini online 🟡"
            elif isinstance(user_obj.status, UserStatusLastWeek):
                status_text = "Terakhir online seminggu lalu ⚪"

            group_status = "Bukan di dalam grup"
            if not event.is_private:
                try:
                    participant = await tele.get_permissions(event.chat_id, user_obj.id)
                    if participant.is_creator:
                        group_status = "Pemilik Grup (Creator) 👑"
                    elif participant.is_admin:
                        title = participant.title if hasattr(participant, 'title') else None
                        group_status = f"Admin Grup 🛠️ (Custom Title: {title or 'Ga ada'})"
                    else:
                        group_status = "Member Biasa 👤"
                except Exception as perm_err:
                    logger.warning(f"Gagal get_permissions standar: {perm_err}. Mencoba fallback channel...")
                    try:
                        from telethon.tl.functions.channels import GetParticipantRequest
                        from telethon.tl.types import ChannelParticipantCreator, ChannelParticipantAdmin
                        
                        channel_part = await tele(GetParticipantRequest(channel=event.chat_id, participant=user_obj.id))
                        if isinstance(channel_part.participant, ChannelParticipantCreator):
                            group_status = "Pemilik Grup (Creator) 👑"
                        elif isinstance(channel_part.participant, ChannelParticipantAdmin):
                            title = channel_part.participant.rank or "Ga ada"
                            group_status = f"Admin Grup 🛠️ (Custom Title: {title})"
                        else:
                            group_status = "Member Biasa 👤"
                    except Exception as final_err:
                        logger.error(f"Gagal total deteksi jabatan: {final_err}")
                        group_status = "Member Biasa / Hidden Admin 👤"

            info_text = (
                "ℹ️ **DETAILED USER INFORMATION**\n"
                "──────────────────────────────\n"
                f"👤 **Nama Lengkap:** `{full_name}`\n"
                f"🆔 **User ID:** `{user_obj.id}`\n"
                f"🏷️ **Username:** {username}\n"
                f"🌐 **Data Center (DC):** `DC-{dc_id}`\n"
                "──────────────────────────────\n"
                f"📊 **Jabatan di Grup Ini:**\n"
                f"└─ `{group_status}`\n\n"
                f"⏱️ **Status Keaktifan:**\n"
                f"└─ `{status_text}`\n\n"
                f"🔒 **Aspek Keamanan & Fitur:**\n"
                f"├─ Premium: {is_premium}\n"
                f"├─ Akun Bot: {is_bot}\n"
                f"├─ Status Scam: {is_scam}\n"
                f"└─ Status Fake: {is_fake}\n\n"
                f"📸 **Jumlah Foto Profil:** `{len(photos)} foto`\n"
                f"📝 **Bio/About:**\n"
                f"`{bio}`\n"
                "──────────────────────────────\n"
                f"🔗 **Link DM Instan:** [Klik Disini](tg://user?id={user_obj.id})"
            )
            
            await sent.edit(info_text, link_preview=False)
            logger.info(f"👉 [DETAIL INFO SUCCESS] Sukses membongkar ID: {user_obj.id}")
        except Exception as e:
            logger.error(f"Detailed Info error: {e}")
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
            if bc_msg:
                broadcast_content.message = bc_msg
        else:
            if not bc_msg:
                await event.respond("❌ **Gagal:** Masukkan pesan setelah perintah atau reply ke media!\nContoh: `.bc Halo Semua Grup!`")
                return
            broadcast_content = bc_msg

        sent = await event.respond("📢 **[BROADCAST GRUP]** Mengumpulkan daftar grup aktif...")
        
        success_count = 0
        fail_count = 0
        start_time = time.monotonic()
        
        try:
            dialogs = await tele.get_dialogs()
        except Exception as e:
            logger.error(f"Gagal memuat dialog list: {e}")
            try: await sent.edit(f"❌ **Gagal memuat daftar chat:** `{e}`")
            except Exception: await event.respond(f"❌ **Gagal memuat daftar chat:** `{e}`")
            return

        # FILTER KHUSUS: Hanya masukkan tipe dialog yang berwujud Grup atau Supergroup (Skip DM / Channel)
        targets = [d for d in dialogs if d.is_group]
        total_targets = len(targets)
        
        if total_targets == 0:
            try: await sent.edit("❌ **Gagal:** Akun lo tidak terdeteksi berada di dalam grup manapun saat ini.")
            except Exception: await event.respond("❌ **Gagal:** Akun lo tidak terdeteksi berada di dalam grup manapun saat ini.")
            return

        try:
            await sent.edit(f"📢 **[BROADCAST PROGRESS]**\nMemulai pengiriman khusus ke `{total_targets}` Grup...")
        except Exception:
            sent = await event.respond(f"📢 **[BROADCAST PROGRESS]**\nMemulai pengiriman khusus ke `{total_targets}` Grup...")

        for index, target in enumerate(targets, start=1):
            try:
                if is_media:
                    await tele.send_message(target.id, broadcast_content)
                else:
                    await tele.send_message(target.id, broadcast_content, link_preview=False)
                
                success_count += 1
                logger.info(f"🚀 [BC GROUP SUCCESS] Terkirim ke grup -> {target.name} (ID: {target.id})")
                
                # Update status log berkala setiap kelipatan 3 grup (DIBUNGKUS PROTEKSI AMAN)
                if index % 3 == 0 or index == total_targets:
                    progress_text = (
                        f"📢 **[BROADCAST GRUP PROGRESS]**\n"
                        f"───────────────────\n"
                        f"🔄 Progress: `{index}/{total_targets}` grup\n"
                        f"✅ Sukses: `{success_count}`\n"
                        f"❌ Gagal: `{fail_count}`\n"
                        f"───────────────────\n"
                        f"⚡ *Sedang menyebar ke grup-grup, tunggu sebentar...*"
                    )
                    try:
                        await sent.edit(progress_text)
                    except Exception:
                        sent = await event.respond(progress_text)
                
                # Jeda aman anti muting Telegram
                await asyncio.sleep(0.6)

            except FloodWaitError as flood:
                logger.warning(f"⚠️ Terkena FloodWait! Istirahat {flood.seconds} detik...")
                await asyncio.sleep(flood.seconds + 2)
                try:
                    if is_media: await tele.send_message(target.id, broadcast_content)
                    else: await tele.send_message(target.id, broadcast_content, link_preview=False)
                    success_count += 1
                except Exception:
                    fail_count += 1

            except Exception as err:
                logger.debug(f"❌ [BC GROUP SKIPPED] Lewati grup {target.name}: {err}")
                fail_count += 1
                continue

        duration = round(time.monotonic() - start_time)
        
        report_text = (
            "✅ **BROADCAST GRUP SELESAI LENGKAP**\n"
            "──────────────────────────────\n"
            f"📊 **Total Target Grup:** `{total_targets} grup`\n"
            f"✨ **Berhasil Terkirim:** `{success_count} grup`\n"
            f"❌ **Gagal/Dilewati:** `{fail_count} grup`\n"
            f"⏱️ **Total Waktu Kerja:** `{duration} detik`\n"
            "──────────────────────────────\n"
            "📢 *Semua pesan khusus grup telah disebarkan bersih tanpa masuk DM personal.*"
        )
        
        try:
            await sent.edit(report_text)
        except Exception:
            await event.respond(report_text)
            
        logger.info("👉 [BROADCAST GROUP COMPLETE] Selesai sebar grup.")

async def main():
    global call, pyro, bot_clients
    logger.info("🚀 Starting Engines...")
    
    # Menyalakan semua Bot Clone yang didaftarkan di BOT_TOKENS
    for idx, token in enumerate(BOT_TOKENS, start=1):
        try:
            b_client = TelegramClient(f'bot_session_{idx}', API_ID, API_HASH)
            await b_client.start(bot_token=token)
            bot_clients.append(b_client)
            logger.info(f"✅ Bot Clone Ke-{idx} Sukses Terkoneksi!")
        except Exception as e:
            logger.error(f"❌ Gagal menyalakan Bot Clone ke-{idx}: {e}")
            
    # Aktifkan loop chat otomatis jika ada bot clone yang ready
    if bot_clients:
        asyncio.create_task(multi_bot_chat_loop())
        
    # INISIALISASI PYROCLIENT + ANTI EROR PEER INVALID (NO UPDATES)
    pyro = PyroClient(
        name="voice",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=PYRO_SESS,
        no_updates=True  # <-- Mematikan update chat masuk agar log clean
    )
    call = PyTgCalls(pyro)
    await pyro.start()
    await call.start()
    logger.info("✅ PyTgCalls Engine ready")
    
    await tele.start()
    me = await tele.get_me()
    logger.info(f"🤖 Login Terverifikasi: {me.first_name} (@{me.username})")
    await tele.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
