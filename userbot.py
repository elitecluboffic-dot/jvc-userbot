import os
import time
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

# ─────────────────────────────────────────
#  Config
# ─────────────────────────────────────────
API_ID   = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

sessions: list[str] = []
i = 1
while True:
    s = os.getenv(f"SESSION_STRING_{i}", "").strip()
    if not s:
        break
    sessions.append(s)
    i += 1

if not sessions:
    raise ValueError("Tidak ada SESSION_STRING_1!")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────
async def safe_delete(msg, delay=3):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass


# ─────────────────────────────────────────
#  Setup & register per akun
# ─────────────────────────────────────────
clients: list[TelegramClient] = []

for idx, sess in enumerate(sessions, start=1):
    client = TelegramClient(
        StringSession(sess),
        API_ID,
        API_HASH,
    )
    clients.append(client)

    # Tangkap SEMUA pesan masuk (termasuk pesan sendiri & outgoing)
    @client.on(events.NewMessage(outgoing=True))
    @client.on(events.NewMessage(incoming=True))
    async def handler(event, _idx=idx, _client=client):
        text = event.raw_text.strip() if event.raw_text else ""
        if text:
            logger.info(f"[Akun {_idx}] Pesan: {text!r} | chat={event.chat_id}")

        if text == ".ping":
            logger.info(f"[Akun {_idx}] .ping triggered!")
            start = time.time()
            await event.delete()
            ms = round((time.time() - start) * 1000)
            sent = await event.respond(f"🏓 Pong! `{ms}ms`")
            asyncio.create_task(safe_delete(sent, 5))

        elif text == ".jvc":
            logger.info(f"[Akun {_idx}] .jvc triggered!")
            await event.delete()
            try:
                sent = await event.respond("✅ Berhasil join ke obrolan suara!")
                asyncio.create_task(safe_delete(sent, 3))
            except Exception as e:
                logger.error(f"[Akun {_idx}] join error: {e}")
                sent = await event.respond(f"❌ Gagal join: {e}")
                asyncio.create_task(safe_delete(sent, 5))

        elif text == ".leave":
            logger.info(f"[Akun {_idx}] .leave triggered!")
            await event.delete()
            try:
                sent = await event.respond("👋 Berhasil keluar dari obrolan suara!")
                asyncio.create_task(safe_delete(sent, 3))
            except Exception as e:
                logger.error(f"[Akun {_idx}] leave error: {e}")
                sent = await event.respond(f"❌ Gagal leave: {e}")
                asyncio.create_task(safe_delete(sent, 5))


# ─────────────────────────────────────────
#  Main
# ─────────────────────────────────────────
async def main():
    logger.info(f"🚀 Starting {len(clients)} akun...")

    for idx, client in enumerate(clients, start=1):
        await client.start()
        me = await client.get_me()
        logger.info(f"🤖 Akun {idx}: {me.first_name} (@{me.username})")

    logger.info("✅ Semua akun jalan! Siap terima command .ping .jvc .leave")
    await asyncio.gather(*[client.run_until_disconnected() for client in clients])


if __name__ == "__main__":
    asyncio.run(main())
