import os
import time
import asyncio
import random
import logging
import re
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.functions.channels import InviteToChannelRequest
from telethon.tl.types import SendMessageTypingAction, User
from telethon.errors import FloodWaitError
from pyrogram import Client as PyroClient
from pyrogram.raw.functions.phone import LeaveGroupCall
from pyrogram.raw.types import InputGroupCall
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
TELE_SESS = os.getenv("SESSION_STRING_1", "").strip()
PYRO_SESS = os.getenv("PYRO_SESSION", "").strip()

RAW_TOKENS = os.getenv("BOT_TOKENS", "").strip()
BOT_TOKENS = [t.strip() for t in RAW_TOKENS.split(",") if t.strip()]

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit()]

TARGET_GROUP_ID = "@CARI_CRUSH_ONLINE"
AUTO_CHAT_INTERVAL = 600

LINK_REGEX = r'(https?://[^\s]+|t\.me/[^\s]+|www\.[^\s]+|\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b)'
MENTION_REGEX = r'@\w+'

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

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

logging.getLogger("telethon.extensions.html").setLevel(logging.WARNING)
logging.getLogger("telethon.network.mtprotosender").setLevel(logging.WARNING)
logging.getLogger("pyrogram.client").setLevel(logging.WARNING)
logging.getLogger("pyrogram.session").setLevel(logging.WARNING)

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


@tele.on(events.NewMessage(incoming=True))
async def auto_blacklist_gcast_handler(event):
    if not event.is_group:
        return

    try:
        chat = await event.get_chat()
        chat_username = f"@{chat.username}" if hasattr(chat, 'username') and chat.username else ""

        if TARGET_GROUP_ID.lower() != chat_username.lower():
            return

        if event.out:
            return

        text = event.raw_text.strip() if event.raw_text else ""
        text_lower = text.lower()

        # 1. SCAN LINK DI ISI PESAN
        if re.search(LINK_REGEX, text, re.IGNORECASE):
            await event.delete()
            logger.info(f"🗑️ [LINK-LOCKDOWN] Pesan berisi link dari {event.sender_id} DIHAPUS!")
            return

        # 2. SCAN GCAST / FORWARD / KEYWORDS
        is_forwarded = event.message.fwd_from is not None
        gcast_keywords = ["gcast", "gikes", "broadcast", "ready p", "bantu up", "pm panel", "open bo"]
        has_keyword = any(kw in text_lower for kw in gcast_keywords)

        if is_forwarded or has_keyword:
            await event.delete()
            logger.info(f"🗑️ [GCAST-BL] Pesan gikes dari {event.sender_id} DIHAPUS!")
            return

        # 3. SCAN PROFIL PENGGUNA (USERNAME & BIO)
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
            logger.info(f"🗑️ [BIO-LOCKDOWN] Pesan dari {sender.first_name} ({sender.id}) dihapus karena bio mengandung link/mention: {bio[:100]}")
            return

    except Exception as e:
        logger.error(f"❌ [AUTO-MOD-ERROR] Gagal eksekusi pengawasan grup: {e}")


@tele.on(events.NewMessage(incoming=True))
async def admin_command_handler(event):
    if event.sender_id not in ADMIN_IDS:
        return

    if not event.raw_text:
        return

    text = event.raw_text.strip()

    if text.startswith(".invite"):
        parts = text.split(" ", 1)
        if len(parts) < 2:
            await event.respond("❌ Format: `.invite @user1 @user2 123456789`")
            return

        targets_raw = parts[1].strip().split()
        total = len(targets_raw)
        hasil = []

        sent = await event.respond(f"⏳ Memproses invite {total} user...")

        for i, target_raw in enumerate(targets_raw, start=1):
            try:
                if target_raw.lstrip("-").isdigit():
                    target = int(target_raw)
                else:
                    target = target_raw

                user_entity = await tele.get_entity(target)
                await tele(InviteToChannelRequest(
                    channel=TARGET_GROUP_ID,
                    users=[user_entity]
                ))
                hasil.append(f"✅ `{target_raw}`")
                logger.info(f"✅ [INVITE] Admin {event.sender_id} invite {target_raw} ke grup")

            except FloodWaitError as flood:
                wait_secs = flood.seconds + 2
                hasil.append(f"⏳ `{target_raw}` — cooldown {wait_secs} detik, menunggu...")
                logger.warning(f"⚠️ [INVITE] FloodWait {wait_secs}s untuk {target_raw}")
                try:
                    await sent.edit(f"⏳ Progress {i}/{total}\n" + "\n".join(hasil))
                except Exception:
                    pass
                await asyncio.sleep(wait_secs)
                try:
                    user_entity = await tele.get_entity(target)
                    await tele(InviteToChannelRequest(
                        channel=TARGET_GROUP_ID,
                        users=[user_entity]
                    ))
                    hasil[-1] = f"✅ `{target_raw}` (retry berhasil)"
                except Exception as retry_err:
                    hasil[-1] = f"❌ `{target_raw}` — {retry_err}"

            except Exception as e:
                hasil.append(f"❌ `{target_raw}` — {e}")
                logger.error(f"❌ [INVITE ERROR] {target_raw}: {e}")

            await asyncio.sleep(2)

            if i % 5 == 0 or i == total:
                try:
                    await sent.edit(f"⏳ Progress {i}/{total}\n" + "\n".join(hasil))
                except Exception:
                    pass

        sukses = sum(1 for h in hasil if h.startswith("✅"))
        gagal = total - sukses
        await sent.edit(
            f"📋 **Hasil Invite Selesai**\n"
            f"✅ Berhasil: `{sukses}` | ❌ Gagal: `{gagal}` | Total: `{total}`\n\n"
            + "\n".join(hasil)
        )


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

    # PING
    if text == ".ping":
        start = time.monotonic()
        sent = await event.respond("🏓 Mengukur...")
        ms = round((time.monotonic() - start) * 1000)
        await sent.edit(f"🏓 Pong! `{ms}ms`")

    # JOIN VC
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

    # LEAVE VC
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

    # INFO
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
                f"├─ Premium: {is_premium}\n"
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

    # BROADCAST GRUP
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
            f"✅ **BROADCAST GRUP SELESAI LENGKAP**\n"
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
