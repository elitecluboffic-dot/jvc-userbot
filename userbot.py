import os
import time
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.users import GetFullUserRequest
from pyrogram import Client as PyroClient
from pyrogram.raw.functions.phone import LeaveGroupCall
from pyrogram.raw.types import InputGroupCall
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
TELE_SESS = os.getenv("SESSION_STRING_1", "").strip()
PYRO_SESS = os.getenv("PYRO_SESSION", "").strip()

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

tele = TelegramClient(StringSession(TELE_SESS), API_ID, API_HASH)
pyro = None
call = None

# Ambil perintah murni yang keluar dari akun kita sendiri
@tele.on(events.NewMessage(outgoing=True))
async def handler(event):
    if not event.raw_text:
        return
        
    text = event.raw_text.strip()
    
    # Supaya bot ga ngerespon balik hasil editannya sendiri
    if text.startswith("ℹ️ **DETAILED") or text.startswith("🏓 Pong!") or text.startswith("👋 Berhasil") or text.startswith("✅ Berhasil"):
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
        try:
            await call.play(
                event.chat_id,
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

    # ==================== PERINTAH INFO (SUPER DETAIL - PYROGRAM HYBRID FIX) ====================
    elif text.startswith(".info"):
        parts = text.split(" ", 1)
        user_obj = None
        target_id = None
        
        sent = await event.respond("🔍 Membongkar database profil target...")
        try:
            # 1. Tentukan target ID dari Reply atau Teks tambahan
            if event.is_reply:
                reply_msg = await event.get_reply_message()
                target_id = reply_msg.sender_id
            elif len(parts) > 1:
                target_raw = parts[1].strip()
                if target_raw.isdigit():
                    target_id = int(target_raw)
                else:
                    try:
                        # Kalau inputnya username (@orang), ubah dulu jadi objek lewat Telethon biasa
                        user_obj = await tele.get_entity(target_raw)
                        target_id = user_obj.id
                    except Exception:
                        target_id = target_raw
            else:
                user_obj = await tele.get_me()
                target_id = user_obj.id

            # 2. Eksekusi Pembongkaran Menggunakan Jalur Hybrid (Telethon + Pyrogram Fallback)
            if not user_obj:
                try:
                    # Coba jalur Telethon dulu
                    user_obj = await tele.get_entity(target_id)
                except Exception:
                    # JIKA TELETHON BUTA, PAKSA PYROGRAM BUAT NYARI SEBAGAI BACKUP!
                    logger.info(f"🔄 Telethon buta entity. Mengalihkan pencarian ID {target_id} ke Pyrogram...")
                    try:
                        pyro_user = await pyro.get_users(target_id)
                        # Daftarkan entitasnya secara paksa ke dalam memori Telethon supaya tidak rewel
                        user_obj = await tele.get_entity(pyro_user.id)
                    except Exception as py_err:
                        logger.error(f"Pyrogram backup search pun gagal: {py_err}")
                        user_obj = None

            if not user_obj:
                await sent.edit("❌ **Gagal total mengambil entitas target!** User terlalu asing bagi Telethon & Pyrogram.")
                return

            # Tarik detail data bio dan jumlah foto profil
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
                        group_status = f"Admin Grup 🛠️ (Custom Title: {participant.title or 'Ga ada'})"
                    else:
                        group_status = "Member Biasa 👤"
                except Exception:
                    group_status = "Gagal mendeteksi status grup"

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

async def main():
    global call, pyro
    logger.info("🚀 Starting...")
    pyro = PyroClient(
        name="voice",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=PYRO_SESS,
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
