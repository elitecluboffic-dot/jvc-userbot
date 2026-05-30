import os
import time
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream

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
#  Filter: semua chat (grup, supergroup, channel, private)
# ─────────────────────────────────────────
all_chats = filters.group | filters.channel | filters.private


# ─────────────────────────────────────────
#  Buat semua client & pytgcalls
# ─────────────────────────────────────────
clients: list[tuple[Client, PyTgCalls, int]] = []

for idx, session_str in enumerate(sessions, start=1):
    client = Client(
        name=f"account_{idx}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_str,
    )
    call = PyTgCalls(client)
    clients.append((client, call, idx))
    logger.info(f"✅ Akun {idx} siap")


# ─────────────────────────────────────────
#  Register handlers
# ─────────────────────────────────────────
for (client, call, akun_idx) in clients:

    # Debug: log semua pesan masuk
    @client.on_message(all_chats)
    async def debug_all(c: Client, message: Message, _idx=akun_idx):
        if message.text:
            logger.info(f"[Akun {_idx}] Pesan masuk di {message.chat.type.value} {message.chat.id}: {message.text!r}")

    # .ping — cek bot hidup atau tidak
    @client.on_message(filters.command("ping", prefixes=".") & all_chats)
    async def ping(c: Client, message: Message, _idx=akun_idx):
        chat_id = message.chat.id
        logger.info(f"[Akun {_idx}] .ping diterima")
        start = time.time()
        await message.delete()
        sent = await c.send_message(chat_id, "🏓 Pong!")
        ms = round((time.time() - start) * 1000)
        await sent.edit_text(f"🏓 Pong! `{ms}ms`")
        await asyncio.sleep(5)
        await sent.delete()

    # .jvc — join voice/video chat
    @client.on_message(filters.command("jvc", prefixes=".") & all_chats)
    async def join_voice(c: Client, message: Message, _call=call, _idx=akun_idx):
        chat_id = message.chat.id
        logger.info(f"[Akun {_idx}] .jvc diterima di chat {chat_id}")
        await message.delete()
        try:
            await _call.join_group_call(
                chat_id,
                MediaStream(
                    "anullsrc",
                    ffmpeg_parameters="-f lavfi",
                )
            )
            sent = await c.send_message(chat_id, f"✅ Akun {_idx} berhasil join ke obrolan suara!")
            await asyncio.sleep(3)
            await sent.delete()
        except Exception as e:
            logger.error(f"[Akun {_idx}] Error join voice: {e}")
            err = await c.send_message(chat_id, f"❌ Gagal join voice chat.\n`{e}`")
            await asyncio.sleep(4)
            await err.delete()

    # .leave — leave voice/video chat
    @client.on_message(filters.command("leave", prefixes=".") & all_chats)
    async def leave_voice(c: Client, message: Message, _call=call, _idx=akun_idx):
        chat_id = message.chat.id
        logger.info(f"[Akun {_idx}] .leave diterima di chat {chat_id}")
        await message.delete()
        try:
            await _call.leave_group_call(chat_id)
            sent = await c.send_message(chat_id, f"👋 Akun {_idx} berhasil keluar dari obrolan suara!")
            await asyncio.sleep(3)
            await sent.delete()
        except Exception as e:
            logger.error(f"[Akun {_idx}] Error leave voice: {e}")
            err = await c.send_message(chat_id, f"❌ Gagal keluar voice chat.\n`{e}`")
            await asyncio.sleep(4)
            await err.delete()


# ─────────────────────────────────────────
#  Main
# ─────────────────────────────────────────
async def main():
    logger.info(f"🚀 Menjalankan {len(clients)} akun...")

    for (client, call, idx) in clients:
        await client.start()
        await call.start()
        me = await client.get_me()
        logger.info(f"🤖 Akun {idx} login sebagai: {me.first_name} (@{me.username})")

    logger.info("✅ Semua akun berjalan! Menunggu command...")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
