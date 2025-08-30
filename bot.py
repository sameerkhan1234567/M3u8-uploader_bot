# bot.py

import os
import re
import asyncio
import tempfile
import subprocess
from pathlib import Path
import aiohttp
import requests
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait

API_ID = int(os.environ.get("API_ID", "29755489"))
API_HASH = os.environ.get("API_HASH", 05e0d957751c827aa03494f503ab54fe")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CLASSPLUS_TOKEN = os.environ.get("CLASSPLUS_TOKEN", "")

TMP = Path(tempfile.gettempdir()) / "vidbot_temp"
TMP.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_MB = 1900

async def progress(current, total, message: Message, prefix=""):
    try:
        percent = (current / total) * 100
        bar = "█" * int(percent / 5) + "░" * (20 - int(percent / 5))
        text = f"{prefix}\n[{bar}] {percent:.1f}%"
        await message.edit_text(text)
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception:
        pass

async def get_final_url(url: str) -> str:
    url = url.strip()
    if "youtube.com" in url or "youtu.be" in url:
        return url
    if ".m3u8" in url:
        return url
    if "classplusapp.com" in url or "media-cdn-alisg.classplusapp.com" in url or "videos.classplusapp" in url:
        api = f'https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={url}'
        headers = {}
        if CLASSPLUS_TOKEN:
            headers['x-access-token'] = CLASSPLUS_TOKEN
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api, headers=headers, timeout=20) as resp:
                    data = await resp.json(content_type=None)
                    return data.get("url", url)
        except Exception:
            return url
    if "classx.co.in" in url or "transcoded-videos.classx.co.in" in url:
        return url
    if "apps-s3-jw-prod.utkarshapp.com" in url:
        return url
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20) as resp:
                text = await resp.text()
                m = re.search(r'(https?://[^"\']*?\.m3u8[^"\']*)', text)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return url

def download_m3u8_to_mp4(m3u8_url: str, out_path: Path) -> bool:
    cmd = ["ffmpeg", "-y", "-allowed_extensions", "ALL", "-i", m3u8_url, "-c", "copy", str(out_path)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode == 0 and out_path.exists():
        return True
    cmd = ["ffmpeg", "-y", "-allowed_extensions", "ALL", "-i", m3u8_url, "-c:v", "libx264", "-c:a", "aac", str(out_path)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode == 0 and out_path.exists()

async def download_stream(url: str, out_path: Path, status_msg: Message):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=120) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0))
                done = 0
                with out_path.open("wb") as f:
                    async for chunk in r.content.iter_chunked(1024 * 128):
                        if chunk:
                            f.write(chunk)
                            done += len(chunk)
                            if total:
                                await progress(done, total, status_msg, "Downloading...")
        return True
    except Exception:
        return False

def download_with_ytdlp(url: str, out_path: Path) -> bool:
    cmd = ["yt-dlp", "-f", "bestvideo+bestaudio/best", "--merge-output-format", "mp4", "-o", str(out_path), url]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return proc.returncode == 0 and out_path.exists()

app = Client("video_extractor_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

@app.on_message(filters.command("start"))
async def start(_, message: Message):
    await message.reply_text("👋 Hi! Send me a video link (ClassPlus, ClassX, Utkarsh, YouTube, m3u8, mp4).")

@app.on_message(filters.regex(r"https?://") | filters.command("get"))
async def handle_link(_, message: Message):
    text = message.text or message.caption or ""
    url = None
    if message.text and message.text.startswith("/get "):
        url = message.text.split(None, 1)[1].strip()
    else:
        m = re.search(r'(https?://[^\s]+)', text)
        if m:
            url = m.group(1).strip("<>")
    if not url and message.reply_to_message:
        rtext = message.reply_to_message.text or ""
        m2 = re.search(r'(https?://[^\s]+)', rtext)
        if m2:
            url = m2.group(1).strip("<>")
    if not url:
        await message.reply_text("❌ No valid URL found.")
        return
    status_msg = await message.reply_text("🔍 Resolving link...")
    try:
        final = await get_final_url(url)
        await status_msg.edit_text(f"✅ Final URL:\n`{final}`", parse_mode="md")
    except Exception as e:
        await status_msg.edit_text(f"❌ Error resolving: `{e}`", parse_mode="md")
        return
    out_path = TMP / f"{message.message_id}_video.mp4"
    try:
        if "youtube.com" in final or "youtu.be" in final:
            await status_msg.edit_text("🎥 Downloading YouTube...")
            ok = download_with_ytdlp(final, out_path)
        elif ".m3u8" in final:
            await status_msg.edit_text("🎬 Downloading m3u8 via ffmpeg...")
            ok = download_m3u8_to_mp4(final, out_path)
        else:
            await status_msg.edit_text("📥 Downloading direct file...")
            ok = await download_stream(final, out_path, status_msg)
        if not ok:
            await status_msg.edit_text("❌ Download failed.")
            return
        size_mb = out_path.stat().st_size / (1024 * 1024)
        if size_mb > MAX_UPLOAD_MB:
            await status_msg.edit_text(f"⚠️ File too large ({size_mb:.1f} MB). Can't upload.")
            return
        await status_msg.edit_text(f"⬆️ Uploading... ({size_mb:.1f} MB)")
        await message.reply_document(str(out_path), caption=f"Here is your video from: {url}")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: `{e}`", parse_mode="md")
    finally:
        if out_path.exists():
            out_path.unlink()

if __name__ == "__main__":
    print("🚀 Bot Started...")
    app.run()
    