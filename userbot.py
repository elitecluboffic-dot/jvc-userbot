import os
import time
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import Dialog, Channel, Chat, User
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

    # ==================== PERINTAH INFO (SUPER DETAIL - FORCE SYNC CHAT MURNI) ====================
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

    # ==================== PERINTAH BROADCAST KHUSUS GRUP (FIX ONLY GROUPS + SAFELOG) ====================
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
        
        # JALUR AMAN REPORT AKHIR: Anti rpcerrorlist.MessageIdInvalidError
        try:
            await sent.edit(report_text)
        except Exception:
            await event.respond(report_text)
            
        logger.info("👉 [BROADCAST GROUP COMPLETE] Selesai sebar grup.")

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
