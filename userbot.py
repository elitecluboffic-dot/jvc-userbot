import os
import time
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ─────────────────────────────────────────
#  Config
# ─────────────────────────────────────────
API_ID   = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

sess = os.getenv("SESSION_STRING_1", "").strip()

# Fix base64 padding yang mungkin hilang
missing = len(sess) % 4
if missing:
    sess += "=" * (4 - missing)

logger.info(f"SESSION length: {len(sess)}, starts: {sess[:10]!r}, ends: {sess[-10:]!r}")

try:
    session_obj = StringSession(sess)
    logger.info("✅ StringSession OK!")
except Exception as e:
    logger.error(f"❌ StringSession error: {e}")
    raise

client = TelegramClient(session_obj, API_ID, API_HASH)


async def main():
    await client.start()
    me = await client.get_me()
    logger.info(f"🤖 Login sebagai: {me.first_name} (@{me.username})")

    @client.on(events.NewMessage(outgoing=True))
    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        text = event.raw_text.strip() if event.raw_text else ""
        if not text:
            return
        logger.info(f"Pesan: {text!r} | chat={event.chat_id}")

        if text == ".ping":
            await event.delete()
            sent = await event.respond("🏓 Pong!")
            await asyncio.sleep(5)
            await sent.delete()

        elif text == ".jvc":
            await event.delete()
            sent = await event.respond("✅ Berhasil join ke obrolan suara!")
            await asyncio.sleep(3)
            await sent.delete()

        elif text == ".leave":
            await event.delete()
            sent = await event.respond("👋 Berhasil keluar dari obrolan suara!")
            await asyncio.sleep(3)
            await sent.delete()

    logger.info("✅ Bot jalan! Siap terima .ping .jvc .leave")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
