import os
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
from pytgcalls.types.stream import StreamAudioEnded

# ─────────────────────────────────────────
#  Config
# ─────────────────────────────────────────
API_ID   = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

# Otomatis detect SESSION_STRING_1, SESSION_STRING_2, dst
sessions: list[str] = []
i = 1
while True:
    s = os.getenv(f"SESSION_STRING_{i}", "")
    if not s:
        break
    sessions.append(s)
    i += 1

if not sessions:
    raise ValueError("Tidak ada SESSION_STRING_1 yang ditemukan di environment!")

# ─────────────────────────────────────────
#  Setup logging
# ─────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
#  Buat client + pytgcalls per akun
# ─────────────────────────────────────────
clients: list[tuple[Client, PyTgCalls]] = []

for idx, session_str in enumerate(sessions, start=1):
    client = Client(
        name=f"account_{idx}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_str,
    )
    call = PyTgCalls(client)
    clients.append((client, call))
    logger.info(f"✅ Akun {idx} siap")


# ─────────────────────────────────────────
#  Register handler ke semua akun
# ─────────────────────────────────────────
def register_handlers(client: Client, call: PyTgCalls, akun_idx: int):

    @client.on_message(filters.command("jvc", prefixes=".") & filters.group)
    async def join_voice(c: Client, message: Message):
        chat_id = message.chat.id
        await message.delete()
        try:
            # MediaStream dengan silence via ffmpeg
            await call.join_group_call(
                chat_id,
                MediaStream(
                    "anullsrc",
                    ffmpeg_parameters="-f lavfi",
                )
            )
            sent = await c.send_message(
                chat_id,
                f"✅ Akun {akun_idx} berhasil join ke obrolan suara!"
            )
            await asyncio.sleep(3)
            await sent.delete()
        except Exception as e:
            logger.error(f"[Akun {akun_idx}] Error join voice: {e}")
            err = await c.send_message(
                chat_id,
                f"❌ Akun {akun_idx} gagal join voice chat.\n`{e}`"
            )
            await asyncio.sleep(4)
            await err.delete()

    @client.on_message(filters.command("leave", prefixes=".") & filters.group)
    async def leave_voice(c: Client, message: Message):
        chat_id = message.chat.id
        await message.delete()
        try:
            await call.leave_group_call(chat_id)
            sent = await c.send_message(
                chat_id,
                f"👋 Akun {akun_idx} berhasil keluar dari obrolan suara!"
            )
            await asyncio.sleep(3)
            await sent.delete()
        except Exception as e:
            logger.error(f"[Akun {akun_idx}] Error leave voice: {e}")
            err = await c.send_message(
                chat_id,
                f"❌ Akun {akun_idx} gagal keluar voice chat.\n`{e}`"
            )
            await asyncio.sleep(4)
            await err.delete()


# Register semua handler
for idx, (client, call) in enumerate(clients, start=1):
    register_handlers(client, call, idx)


# ─────────────────────────────────────────
#  Main
# ─────────────────────────────────────────
async def main():
    logger.info(f"🚀 Menjalankan {len(clients)} akun...")

    for idx, (client, call) in enumerate(clients, start=1):
        await client.start()
        await call.start()
        me = await client.get_me()
        logger.info(f"🤖 Akun {idx} login sebagai: {me.first_name} (@{me.username})")

    logger.info("✅ Semua akun berjalan! Menunggu command .jvc / .leave ...")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
