import os
import json
import asyncio
import logging
from google import genai
from google.genai import errors as genai_errors

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]

client_gemini = genai.Client(api_key=GEMINI_API_KEY)

MEMORY_FILE = "bot/memory.json"
MAX_HISTORY = 30
MAX_OBSERVED = 100

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_memory(mem):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, ensure_ascii=False, indent=2)

memory = load_memory()
queues = {}

def get_queue(chat_id):
    if chat_id not in queues:
        queues[chat_id] = []
    return queues[chat_id]

def get_group(chat_id):
    key = str(chat_id)
    if key not in memory:
        memory[key] = {"users": {}, "history": [], "observed": []}
    return memory[key]

def update_user_mem(group, sender_id, name, username):
    uid = str(sender_id)
    if uid not in group["users"]:
        group["users"][uid] = {"name": name, "username": username, "count": 0}
    group["users"][uid]["name"] = name
    group["users"][uid]["username"] = username or ""
    group["users"][uid]["count"] += 1

def add_to_history(group, sender_name, text):
    group["history"].append({"who": sender_name, "msg": text})
    if len(group["history"]) > MAX_HISTORY:
        group["history"] = group["history"][-MAX_HISTORY:]

def add_to_observed(group, sender_name, text):
    group["observed"].append({"who": sender_name, "msg": text})
    if len(group["observed"]) > MAX_OBSERVED:
        group["observed"] = group["observed"][-MAX_OBSERVED:]

def build_members_summary(group):
    users = group.get("users", {})
    if not users:
        return "No known members yet."
    lines = []
    for uid, info in users.items():
        tag = f"@{info['username']}" if info["username"] else ""
        lines.append(f"- {info['name']} {tag} ({info['count']} messages)")
    return "\n".join(lines)

def build_history_text(group):
    history = group.get("history", [])
    if not history:
        return "No conversation history yet."
    return "\n".join([f"{h['who']}: {h['msg']}" for h in history])

def get_video_info(query):
    import yt_dlp
    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "noplaylist": True,
        "default_search": "ytsearch1",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        if "entries" in info:
            info = info["entries"][0]
        return info.get("webpage_url") or info.get("url"), info.get("title", query)

async def gemini_reply(event, prompt):
    for attempt in range(3):
        try:
            response = client_gemini.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            await event.reply(response.text)
            return
        except genai_errors.ClientError as e:
            if "429" in str(e) or "quota" in str(e).lower() or "rate" in str(e).lower():
                wait = (attempt + 1) * 5
                logger.warning(f"Rate limit, waiting {wait}s")
                await asyncio.sleep(wait)
            else:
                logger.error(f"Gemini error: {e}")
                await event.reply("Yaar kuch gadbad ho gayi, thodi der baad try karo 😅")
                return
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            await event.reply("Yaar kuch gadbad ho gayi, thodi der baad try karo 😅")
            return
    await event.reply("Abhi bahut busy hoon yaar, 1-2 minute baad try karo 🙏")

async def main():
    from telethon import TelegramClient, events
    from pytgcalls import PyTgCalls
    from pytgcalls.types import MediaStream, AudioQuality

    bot = TelegramClient("bot/bot_session", API_ID, API_HASH)
    call = PyTgCalls(bot)

    async def play_next(chat_id):
        queue = get_queue(chat_id)
        if not queue:
            return
        url, title = queue[0]
        try:
            await call.play(chat_id, MediaStream(url, AudioQuality.HIGH,
                                                  ytdlp_parameters="--js-runtimes node"))
            logger.info(f"Playing in {chat_id}: {title}")
        except Exception as e:
            logger.error(f"Error playing: {e}")
            if queue:
                queue.pop(0)

    @bot.on(events.NewMessage(pattern="/start"))
    async def cmd_start(event):
        await event.reply("Bacha Yarr tu Mera")

    @bot.on(events.NewMessage(pattern=r"/play(.*)"))
    async def cmd_play(event):
        query = event.pattern_match.group(1).strip()
        if not query:
            await event.reply("Bhai kuch toh daal! Usage: /play <song name or YouTube link>")
            return
        msg = await event.reply(f"🔍 Dhoond raha hoon: {query}...")
        try:
            url, title = await asyncio.to_thread(get_video_info, query)
        except Exception as e:
            logger.error(f"yt-dlp error: {e}")
            await msg.edit("Yaar yeh song nahi mila 😅 Doosra try karo!")
            return
        chat_id = event.chat_id
        queue = get_queue(chat_id)
        queue.append((url, title))
        if len(queue) == 1:
            await msg.edit(f"🎵 Ab baja raha hoon: **{title}**")
            await play_next(chat_id)
        else:
            await msg.edit(f"✅ Queue mein add ho gaya (#{len(queue)}): **{title}**")

    @bot.on(events.NewMessage(pattern="/skip"))
    async def cmd_skip(event):
        chat_id = event.chat_id
        queue = get_queue(chat_id)
        if not queue:
            await event.reply("Bhai queue toh khali hai!")
            return
        queue.pop(0)
        if queue:
            await event.reply("⏭️ Skip! Agla gaana...")
            await play_next(chat_id)
        else:
            try:
                await call.leave_call(chat_id)
            except Exception:
                pass
            await event.reply("⏭️ Queue khatam ho gayi.")

    @bot.on(events.NewMessage(pattern="/stop"))
    async def cmd_stop(event):
        chat_id = event.chat_id
        queues[chat_id] = []
        try:
            await call.leave_call(chat_id)
        except Exception:
            pass
        await event.reply("⏹️ Music band kar diya yaar.")

    @bot.on(events.NewMessage(pattern="/pause"))
    async def cmd_pause(event):
        try:
            await call.pause_stream(event.chat_id)
            await event.reply("⏸️ Pause kar diya!")
        except Exception:
            await event.reply("Pause nahi hua, pehle kuch bajao!")

    @bot.on(events.NewMessage(pattern="/resume"))
    async def cmd_resume(event):
        try:
            await call.resume_stream(event.chat_id)
            await event.reply("▶️ Resume!")
        except Exception:
            await event.reply("Resume nahi hua yaar!")

    @bot.on(events.NewMessage(pattern="/queue"))
    async def cmd_queue(event):
        queue = get_queue(event.chat_id)
        if not queue:
            await event.reply("Queue bilkul khali hai!")
            return
        lines = [f"{i+1}. {t}" for i, (_, t) in enumerate(queue)]
        await event.reply("🎶 Queue:\n" + "\n".join(lines))

    @bot.on(events.NewMessage)
    async def handle_message(event):
        if not event.text or event.text.startswith("/"):
            return
        sender = await event.get_sender()
        if not sender or getattr(sender, "bot", False):
            return

        sender_name = (getattr(sender, "first_name", "") or "") or (getattr(sender, "username", "") or "User")
        sender_id = sender.id
        username = getattr(sender, "username", "") or ""
        is_private = event.is_private
        is_group = event.is_group or event.is_channel
        me = await bot.get_me()
        bot_username = me.username

        is_mentioned = f"@{bot_username}" in event.text
        is_reply_to_bot = False
        if event.reply_to_msg_id:
            try:
                replied = await event.get_reply_message()
                if replied and replied.sender_id == me.id:
                    is_reply_to_bot = True
            except Exception:
                pass

        if is_group:
            group = get_group(event.chat_id)
            update_user_mem(group, sender_id, sender_name, username)
            add_to_observed(group, sender_name, event.text[:200])
            save_memory(memory)

        if is_group and not is_mentioned and not is_reply_to_bot:
            return

        user_text_clean = event.text.replace(f"@{bot_username}", "").strip()
        if not user_text_clean:
            return

        logger.info(f"[{'private' if is_private else 'group'}] {sender_name}: {user_text_clean[:60]}")

        if is_group:
            group = get_group(event.chat_id)
            add_to_history(group, sender_name, user_text_clean)
            save_memory(memory)
            members_summary = build_members_summary(group)
            history_text = build_history_text(group)
            prompt = f"""Tu ek dost-style chatbot hai jo Hindi, Punjabi aur Hinglish mein baat karta hai.
Tu is group ke logon ko jaanta hai aur unke saath friendly aur casual baat karta hai.
Kabhi Hindi use kar, kabhi Punjabi, kabhi Hinglish — jo natural lage wahi bol.

Group ke members:
{members_summary}

Recent conversation:
{history_text}

Ab {sender_name} ne yeh kaha:
{user_text_clean}

Short, friendly aur personal reply de. Agar member ka naam pata hai toh use karo."""
        else:
            prompt = f"""Tu ek dost-style chatbot hai jo Hindi, Punjabi aur Hinglish mein baat karta hai.
Kabhi Hindi use kar, kabhi Punjabi, kabhi Hinglish — jo natural lage wahi bol.
Friendly aur casual reply de.

User:
{user_text_clean}"""

        await gemini_reply(event, prompt)

    await bot.start(bot_token=BOT_TOKEN)
    await call.start()
    me = await bot.get_me()
    print(f"Bot is running as @{me.username}...")
    logger.info(f"Started as @{me.username}")
    await bot.run_until_disconnected()

print("Bot starting...")
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
try:
    loop.run_until_complete(main())
finally:
    loop.close()
