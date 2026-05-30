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
TELE_SESS = os.getenv("SESSION_STRING_1", "").strip()  # Telethon format
PYRO_SESS = os.getenv("PYRO_SESSION", "").strip()      # Pyrogram format — akun SAMA, format beda

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Telethon — buat baca/kirim pesan
tele = TelegramClient(StringSession(TELE_SESS), API_ID, API_HASH)

# Pyrogram — buat voice chat (akun sama, session format pyrogram)
pyro = PyroClient(
    name="voice",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=PYRO_SESS,
)
call = PyTgCalls(pyro)


async def safe_delete(msg, delay=3):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass


@tele.on(events.NewMessage(outgoing=True))
@tele.on(events.NewMessage(incoming=True))
async def handler(event):
    text = event.raw_text.strip() if event.raw_text else ""
    if not text:
        return
    logger.info(f"Pesan: {text!r} | chat={event.chat_id}")

    if text == ".ping":
        start = time.monotonic()
        await event.delete()
        sent = await event.respond("🏓 Mengukur...")
        ms = round((time.monotonic() - start) * 1000)
        await sent.edit(f"🏓 Pong! `{ms}ms`")
        asyncio.create_task(safe_delete(sent, 5))

    elif text == ".jvc":
        await event.delete()
        try:
            await call.join_group_call(
                event.chat_id,
                MediaStream("anullsrc", ffmpeg_parameters="-f lavfi"),
            )
            sent = await event.respond("✅ Berhasil join ke obrolan suara!")
            asyncio.create_task(safe_delete(sent, 3))
        except Exception as e:
            logger.error(f"join error: {e}")
            sent = await event.respond(f"❌ Gagal join: `{e}`")
            asyncio.create_task(safe_delete(sent, 5))

    elif text == ".leave":
        await event.delete()
        try:
            await call.leave_group_call(event.chat_id)
            sent = await event.respond("👋 Berhasil keluar dari obrolan suara!")
            asyncio.create_task(safe_delete(sent, 3))
        except Exception as e:
            logger.error(f"leave error: {e}")
            sent = await event.respond(f"❌ Gagal leave: `{e}`")
            asyncio.create_task(safe_delete(sent, 5))


async def main():
    logger.info("🚀 Starting...")
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
