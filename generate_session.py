"""
Jalankan script ini SEKALI di lokal untuk generate SESSION_STRING Telethon.
Hasil SESSION_STRING nanti dimasukkan ke Railway Variables.

Cara pakai:
    pip install telethon cryptg
    python generate_session.py
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = int(input("Masukkan API_ID kamu: ").strip())
API_HASH = input("Masukkan API_HASH kamu: ").strip()

async def main():
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        session = client.session.save()
        print("\n" + "="*60)
        print("✅ SESSION_STRING Telethon kamu:")
        print("="*60)
        print(session)
        print("="*60)
        print("\nCopy string di atas → paste ke Railway Variables sebagai SESSION_STRING_1")

asyncio.run(main())
