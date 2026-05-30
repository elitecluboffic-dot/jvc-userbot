import os
import time
import asyncio
import logging
from pyrogram import Client, filters, idle
from pyrogram.types import Message
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
    s = os.getenv(f"SESSION_STRING_{i}", "")
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
#  Setup clients
# ─────────────────────────────────────────
apps: list[Client] = []
calls: list[PyTgCalls] = []

for idx, sess in enumerate(sessions, start=1):
    app = Client(
        name=f"acc_{idx}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=sess,
    )
    call = PyTgCalls(app)
    apps.append(app)
    calls.append(call)


# ─────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────
def make_filter():
    """Tangkap semua pesan dari mana aja termasuk pesan sendiri."""
    return filters.create(lambda _, __, ___: True)


async def safe_delete(msg, delay=3):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass


# ─────────────────────────────────────────
#  Register handlers per akun
# ─────────────────────────────────────────
for idx, (app, call) in enumerate(zip(apps, calls), start=1):

    @app.on_message(make_filter())
    async def catch_all(c: Client, m: Message, _idx=idx):
        if m.text:
            logger.info(f"[Akun {_idx}] [{m.chat.type}] Pesan: {m.text!r}")

    @app.on_message(filters.regex(r"^\.ping$") & make_filter())
    async def cmd_ping(c: Client, m: Message, _idx=idx):
        logger.info(f"[Akun {_idx}] .ping triggered!")
        start = time.time()
        try:
            await m.delete()
        except Exception:
            pass
        ms = round((time.time() - start) * 1000)
        sent = await c.send_message(m.chat.id, f"🏓 Pong! `{ms}ms`")
        asyncio.create_task(safe_delete(sent, 5))

    @app.on_message(filters.regex(r"^\.jvc$") & make_filter())
    async def cmd_jvc(c: Client, m: Message, _call=call, _idx=idx):
        logger.info(f"[Akun {_idx}] .jvc triggered!")
        chat_id = m.chat.id
        try:
            await m.delete()
        except Exception:
            pass
        try:
            await _call.join_group_call(
                chat_id,
                MediaStream("anullsrc", ffmpeg_parameters="-f lavfi"),
            )
            sent = await c.send_message(chat_id, f"✅ Akun {_idx} berhasil join ke obrolan suara!")
            asyncio.create_task(safe_delete(sent, 3))
        except Exception as e:
            logger.error(f"[Akun {_idx}] join error: {e}")
            sent = await c.send_message(chat_id, f"❌ Gagal join: `{e}`")
            asyncio.create_task(safe_delete(sent, 5))

    @app.on_message(filters.regex(r"^\.leave$") & make_filter())
    async def cmd_leave(c: Client, m: Message, _call=call, _idx=idx):
        logger.info(f"[Akun {_idx}] .leave triggered!")
        chat_id = m.chat.id
        try:
            await m.delete()
        except Exception:
            pass
        try:
            await _call.leave_group_call(chat_id)
            sent = await c.send_message(chat_id, f"👋 Akun {_idx} berhasil keluar dari obrolan suara!")
            asyncio.create_task(safe_delete(sent, 3))
        except Exception as e:
            logger.error(f"[Akun {_idx}] leave error: {e}")
            sent = await c.send_message(chat_id, f"❌ Gagal leave: `{e}`")
            asyncio.create_task(safe_delete(sent, 5))


# ─────────────────────────────────────────
#  Main
# ─────────────────────────────────────────
async def main():
    logger.info(f"🚀 Starting {len(apps)} akun...")

    for idx, (app, call) in enumerate(zip(apps, calls), start=1):
        await app.start()
        await call.start()
        me = await app.get_me()
        logger.info(f"🤖 Akun {idx}: {me.first_name} (@{me.username})")

    logger.info("✅ Semua akun jalan! Siap terima command .ping .jvc .leave")
    await idle()


if __name__ == "__main__":
    asyncio.run(main())
