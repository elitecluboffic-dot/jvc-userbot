import os
import time
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from pyrogram import Client as PyroClient
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

API_ID    = int(os.environ["API_ID"])
API_HASH  = os.environ["API_HASH"]
TELE_SESS = os.getenv("SESSION_STRING_1", "").strip()
PYRO_SESS = os.getenv("PYRO_SESSION", "").strip()

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

tele = TelegramClient(StringSession(TELE_SESS), API_ID, API_HASH)
call = None

# Gunakan filter fungsi biar menangkap incoming & outgoing dengan bersih
@tele.on(events.NewMessage(func=lambda e: e.text))
async def handler(event):
    text = event.raw_text.strip() if event.raw_text else ""
    if not text:
        return
        
    # Mengabaikan respon dari bot itu sendiri supaya tidak terjadi loop/race condition
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
        try:
            chat_id = event.chat_id
            
            # 1. Kirim sinyal leave ke telegram voice chat
            await call.leave_call(chat_id)
            
            # 2. HARD RESET: Hapus paksa chat_id dari cache internal pytgcalls
            # Ini buat matiin paksa fitur "Auto-Reconnect" bawaan pytgcalls yang suka keras kepala
            if hasattr(call, '_active_calls') and chat_id in call._active_calls:
                try:
                    call._active_calls.remove(chat_id)
                except:
                    pass
            elif hasattr(call, 'active_calls') and chat_id in call.active_calls:
                try:
                    call.active_calls.remove(chat_id)
                except:
                    pass
                    
            # 3. Kasih jeda dikit sebelum kirim text biar state network bener-bener close dulu
            await asyncio.sleep(1)
            await event.respond("👋 Berhasil keluar dari obrolan suara secara permanen!")
            logger.info(f"👉 [VOICE RESET] Sukses keluar total dan hapus cache dari group: {chat_id}")
            
        except Exception as e:
            logger.error(f"leave error: {e}")
            await event.respond(f"❌ Gagal leave: `{e}`")

async def main():
    global call
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
    logger.info("✅ PyTgCalls ready")
    await tele.start()
    me = await tele.get_me()
    logger.info(f"🤖 Login: {me.first_name} (@{me.username})")
    logger.info("✅ Siap! Ketik .ping .jvc .leave")
    await tele.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
