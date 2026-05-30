"""
Jalankan script ini SEKALI di lokal untuk generate SESSION_STRING.
Hasil SESSION_STRING nanti dimasukkan ke Railway Variables.

Cara pakai:
    pip install pyrogram tgcrypto
    python generate_session.py
"""

import asyncio
from pyrogram import Client
import os

API_ID   = input("Masukkan API_ID kamu: ").strip()
API_HASH = input("Masukkan API_HASH kamu: ").strip()

async def main():
    async with Client(
        "session_generator",
        api_id=int(API_ID),
        api_hash=API_HASH,
        in_memory=True,
    ) as app:
        session = await app.export_session_string()
        print("\n" + "="*60)
        print("✅ SESSION_STRING kamu:")
        print("="*60)
        print(session)
        print("="*60)
        print("\nCopy string di atas dan masukkan ke Railway Variables sebagai SESSION_STRING")

asyncio.run(main())
