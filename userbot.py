import os
import time
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from pyrogram import Client as PyroClient
from pyrogram.raw.functions.phone import DiscardGroupCallParticipant
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

@tele.on(events.NewMessage(func=lambda e: e.text))
async def handler(event):
    text = event.raw_text.strip() if event.raw_text else ""
    if not text:
        return
        
    if text.startswith("👋 Berhasil") or text.startswith("✅ Berhasil") or text.startswith("🏓"):
        return

    logger.info(f"Pesan: {text!r} | chat={event.chat_id}")

    if text == ".ping":
        start = time.monotonic()
        sent = await event.respond("🏓 Mengukur...")
        ms = round((time.monotonic() - start) * 1000)
        await sent.edit(f"🏓 Pong! `{ms}ms`")

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

    elif text == ".leave":
        chat_id = event.chat_id
        try:
            # 1. Coba leave lewat cara normal pytgcalls
            await call.leave_call(chat_id)
            await asyncio.sleep(0.5)
            await event.respond("👋 Berhasil keluar dari obrolan suara!")
            logger.info(f"👉 [LEAVE SUCCESS] Keluar normal dari {chat_id}")
            
        except Exception as e:
            logger.warning(f"Pytgcalls leave gantung/error: {e}. Menjalankan FORCE DISCONNECT...")
            
            # 2. 🔥 FORCE DISCONNECT ENGINE (Bypass "Not in a call" Bug)
            # Jika pytgcalls error/gantung, kita tembak langsung lewat raw Telegram API via Pyrogram
            try:
                # Ambil info full chat untuk nyari group call yang lagi aktif
                peer = await pyro.resolve_peer(chat_id)
                full_chat = await pyro.invoke(
                    pyrogram.raw.functions.channels.GetFullChannel(channel=peer) 
                    if chat_id < 0 and str(chat_id).startswith("-100") 
                    else pyrogram.raw.functions.messages.GetFullChat(chat_id=abs(chat_id))
                )
                
                # Ambil id group call-nya
                call_info = full_chat.full_chat.call
                if call_info:
                    input_call = InputGroupCall(id=call_info.id, access_hash=call_info.access_hash)
                    # Kick akun kita sendiri keluar dari obrolan suara secara paksa
                    await pyro.invoke(
                        DiscardGroupCallParticipant(
                            call=input_call,
                            participant=await pyro.resolve_peer("me")
                        )
                    )
                    await event.respond("👋 Force Disconnect: Berhasil keluar secara paksa dari server Telegram!")
                    logger.info(f"🔥 [FORCE LEAVE] Akun dipaksa keluar dari server untuk chat {chat_id}")
                else:
                    await event.respond("👋 Bot sudah tidak ada di dalam call (UI Telegram Anda mungkin Ghosting).")
            except Exception as ex:
                logger.error(f"Force leave fatal error: {ex}")
                await event.respond(f"❌ Gagal total untuk leave: `{ex}`")
        
        finally:
            # Bersihkan sisa cache tracker aktif
            for cache_attr in ['_active_calls', 'active_calls']:
                if hasattr(call, cache_attr):
                    try: getattr(call, cache_attr).remove(chat_id)
                    except: pass

async def main():
    global call, pyro
    logger.info("🚀 Starting...")

    import pyrogram  # Pastikan di-import secara lokal untuk raw functions
    pyro = PyroClient(
        name="voice",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=PYRO_SESS,
    )
    call = PyTgCalls(pyro)

    await pyro.start()
    await call.start()
    logger.info("✅ PyTgCalls & Pyrogram Raw Engine ready")
    
    await tele.start()
    me = await tele.get_me()
    logger.info(f"🤖 Login: {me.first_name} (@{me.username})")
    logger.info("✅ Siap! Perintah .leave sekarang dilengkapi Force-Kill")
    await tele.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
