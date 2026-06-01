import os
import time
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.users import GetFullUserRequest
from pyrogram import Client as PyroClient
# 🔥 FIX IMPORT: Menggunakan fungsi raw API Pyrogram yang benar
from pyrogram.raw.functions.phone import LeaveGroupCall
from pyrogram.raw.types import InputGroupCall
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

API_ID    = int(os.environ["API_ID"])
API_HASH  = os.environ["API_HASH"]
TELE_SESS = os.getenv("SESSION_STRING_1", "").strip()
PYRO_SESS = os.getenv("PYRO_SESSION", "").strip()

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

tele = TelegramClient(StringSession(TELE_SESS), API_ID, API_HASH)
pyro = None
call = None

# Filter ketat: Hanya merespon pesan keluar (outgoing) dari akun lu sendiri
@tele.on(events.NewMessage(outgoing=True))
async def handler(event):
    text = event.raw_text.strip() if event.raw_text else ""
    if not text:
        return
        
    if text.startswith("👋 Berhasil") or text.startswith("✅ Berhasil") or text.startswith("🏓") or text.startswith("ℹ️ **DETAILED USER INFORMATION**"):
        return

    if not text.startswith("."):
        return

    logger.info(f"Perintah Diterima: {text!r} | chat={event.chat_id}")

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
            # 1. Coba leave lewat cara normal pytgcalls
            await call.leave_call(chat_id)
            await asyncio.sleep(0.5)
            await event.respond("👋 Berhasil keluar dari obrolan suara!")
            logger.info(f"👉 [LEAVE SUCCESS] Keluar normal dari {chat_id}")
            
        except Exception as e:
            logger.warning(f"Pytgcalls leave error ({e}). Menjalankan FORCE DISCONNECT...")
            
            # 2. 🔥 FORCE DISCONNECT: Tembak server Telegram langsung pakai LeaveGroupCall
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
                    # Putus paksa koneksi stream di group call tersebut
                    await pyro.invoke(
                        LeaveGroupCall(
                            call=input_call,
                            source=0 # 0 berarti disconnect total dari sisi client
                        )
                    )
                    await event.respond("👋 Force Disconnect: Berhasil dipaksa keluar via raw API Telegram!")
                    logger.info(f"🔥 [FORCE LEAVE] Sukses paksa keluar dari call chat {chat_id}")
                else:
                    await event.respond("👋 Bot sudah tidak ada di dalam call (UI Telegram Anda mungkin sedang ghosting).")
            except Exception as ex:
                logger.error(f"Force leave fatal error: {ex}")
                await event.respond(f"❌ Gagal total untuk leave: `{ex}`")
        
        finally:
            # Bersihkan sisa-sisa tracking cache biar ga memicu auto-reconnect
            for cache_attr in ['_active_calls', 'active_calls']:
                if hasattr(call, cache_attr):
                    try: getattr(call, cache_attr).remove(chat_id)
                    except: pass

    # ==================== 🔥 PERINTAH INFO (SUPER DETAIL) 🔥 ====================
    elif text.startswith(".info"):
        parts = text.split(" ", 1)
        target = None
        
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            target = reply_msg.sender_id
        elif len(parts) > 1:
            target = parts[1].strip()
            if target.isdigit():
                target = int(target)
        else:
            target = "me"
            
        sent = await event.respond("🔍 Membongkar database profil target...")
        try:
            # 1. Ambil data dasar, data penuh, dan foto profil dari Telegram API
            user_obj = await tele.get_entity(target)
            full_user = await tele(GetFullUserRequest(id=user_obj.id))
            photos = await tele.get_profile_photos(user_obj.id, limit=0)
            
            # 2. Parsing Data Dasar
            first_name = user_obj.first_name or ""
            last_name  = user_obj.last_name or ""
            full_name  = f"{first_name} {last_name}".strip()
            username   = f"@{user_obj.username}" if user_obj.username else "Tidak Ada"
            bio        = full_user.full_user.about or "Kosong"
            
            # 3. Parsing Status Akun & Keamanan
            is_premium = "Iya (Premium) ✨" if user_obj.premium else "Tidak (Gratisan)"
            is_bot     = "Iya 🤖" if user_obj.bot else "Bukan (User Biasa) 👤"
            is_scam    = "⚠️ YA (Terdeteksi Penipu!)" if user_obj.scam else "Aman (Bersih) ✅"
            is_fake    = "⚠️ YA (Akun Palsu!)" if user_obj.fake else "Asli ✅"
            dc_id      = user_obj.photo.dc_id if user_obj.photo else "Tidak Diketahui"
            
            # 4. Cek Status Last Seen / Online
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

            # 5. Cek Hak Akses / Jabatan Target di Grup Ini
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

            # 6. Susun Tampilan Output Teks Rapi
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
