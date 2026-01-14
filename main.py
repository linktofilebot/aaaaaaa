import asyncio
import random
import string
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta

# ==================== ১. কনফিগারেশন (আপনার তথ্য দিন) ====================
API_ID = 1234567                 # আপনার API ID
API_HASH = "your_api_hash"        # আপনার API Hash
BOT_TOKEN = "your_bot_token"      # BotFather থেকে পাওয়া টোকেন
ADMIN_ID = 12345678              # আপনার টেলিগ্রাম আইডি (অ্যাডমিন)
LOG_CHANNEL = -100123456789       # লগ চ্যানেল আইডি (অবশ্যই -100 সহ)
FILE_CHANNEL = -100987654321      # ফাইল চ্যানেল আইডি (অবশ্যই -100 সহ)
MONGODB_URI = "mongodb+srv://..."   # আপনার MongoDB লিংক
OWNER_USERNAME = "YourUsername"   # আপনার ইউজারনেম (@ ছাড়া)

# ==================== ২. ডাটাবেস ও ক্লায়েন্ট সেটআপ ====================
db_client = AsyncIOMotorClient(MONGODB_URI)
db = db_client["file_store_db"]
users_col = db["users"]
files_col = db["files"]
plans_col = db["plans"]
redeem_col = db["redeem"]
settings_col = db["settings"]

app = Client("file_store_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ==================== ৩. সাহায্যকারী ফাংশনসমূহ ====================

# প্রিমিয়াম স্ট্যাটাস চেক
async def check_premium_status(user_id):
    user = await users_col.find_one({"user_id": user_id})
    if user and user.get("is_premium"):
        expiry = user.get("expiry_date")
        if expiry and datetime.now() > expiry:
            await users_col.update_one({"user_id": user_id}, {"$set": {"is_premium": False}})
            return False, "ফ্রি (মেয়াদ শেষ)"
        return True, expiry.strftime('%Y-%m-%d %H:%M')
    return False, "ফ্রি মেম্বার"

# ইউনিভার্সাল সর্টেনার ফাংশন (সব সাইটে কাজ করবে)
async def get_universal_shortlink(url):
    s = await settings_col.find_one({"id": "shortener"})
    if not s: return url
    api_url = f"https://{s['base_url']}/api?api={s['api_key']}&url={url}"
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(api_url, timeout=10) as res:
                data = await res.json()
                return data.get("shortenedUrl") or data.get("shortlink") or data.get("url") or url
    except: return url

# টাইম পার্সার (যেমন: 1day, 1hour)
def get_exp_time(t_str):
    try:
        n = int(''.join(filter(str.isdigit, t_str)))
        if "min" in t_str: return timedelta(minutes=n)
        if "hour" in t_str: return timedelta(hours=n)
        if "day" in t_str: return timedelta(days=n)
        if "month" in t_str: return timedelta(days=n * 30)
    except: return None

# ==================== ৪. মূল কমান্ড হ্যান্ডলার ====================

# ১. START কমান্ড (প্রোফাইল কার্ড, লোগো ও ভেরিফিকেশন)
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    user_id = message.from_user.id
    
    # ইউজার ডাটাবেসে সেভ করা
    user_data = await users_col.find_one({"user_id": user_id})
    if not user_data:
        user_data = {"user_id": user_id, "is_premium": False, "p_index": 0, "f_index": 0}
        await users_col.insert_one(user_data)

    # ভেরিফিকেশন প্রসেস (ফ্রি ইউজারদের ১০টি ফাইল)
    if len(message.command) > 1 and message.command[1].startswith("verify"):
        is_prem, _ = await check_premium_status(user_id)
        if is_prem: return await message.reply("আপনি প্রিমিয়াম মেম্বার, আপনার ভেরিফিকেশন লাগবে না।")
        
        f_idx = user_data.get("f_index", 0)
        files = await files_col.find().sort("_id", 1).skip(f_idx).limit(10).to_list(10)
        
        if not files:
            await users_col.update_one({"user_id": user_id}, {"$set": {"f_index": 0}})
            return await message.reply("ডাটাবেসের সব ফাইল শেষ! শুরু থেকে আবার গেট ফাইল করুন।")
            
        await message.reply("✅ ভেরিফিকেশন সফল! আপনার ১০টি ভিডিও পাঠানো হচ্ছে...")
        for f in files:
            try:
                await client.copy_message(user_id, FILE_CHANNEL, f["msg_id"])
                await asyncio.sleep(1)
            except: pass
        await users_col.update_one({"user_id": user_id}, {"$inc": {"f_index": 10}})
        return

    # সাধারণ স্টার্ট মেসেজ
    is_prem, status_txt = await check_premium_status(user_id)
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Get Files", callback_data="btn_getfile")],
        [InlineKeyboardButton("💎 Plans", callback_data="btn_plans"),
         InlineKeyboardButton("Owner 👑", url=f"https://t.me/{OWNER_USERNAME}")]
    ])
    
    text = (f"👋 স্বাগতম {message.from_user.first_name}!\n\n"
            f"🆔 **আপনার আইডি:** `{user_id}`\n"
            f"🎭 **আপনার নাম:** {message.from_user.first_name}\n"
            f"💎 **স্ট্যাটাস:** {status_txt}\n\n"
            "ফাইল পেতে নিচের বাটনে ক্লিক করুন।")
    
    try:
        async for photo in client.get_chat_photos(user_id, limit=1):
            await message.reply_photo(photo=photo.file_id, caption=text, reply_markup=btn)
            return
    except: pass
    await message.reply_text(text, reply_markup=btn)

# ২. GETFILE কমান্ড (প্রিমিয়াম ১টি, ফ্রি ১০টি সর্ট লিংকের মাধ্যমে)
@app.on_callback_query(filters.regex("btn_getfile"))
@app.on_message(filters.command("getfile"))
async def getfile_handler(client, update):
    is_cb = hasattr(update, "data")
    user_id = update.from_user.id
    chat_id = update.message.chat.id if is_cb else update.chat.id
    
    user_data = await users_col.find_one({"user_id": user_id})
    is_prem, _ = await check_premium_status(user_id)

    if is_prem:
        # প্রিমিয়াম: ১টি করে ফাইল সিরিয়ালে দিবে
        p_idx = user_data.get("p_index", 0)
        files = await files_col.find().sort("_id", 1).skip(p_idx).limit(1).to_list(1)
        if not files:
            await users_col.update_one({"user_id": user_id}, {"$set": {"p_index": 0}})
            return await client.send_message(chat_id, "সব ফাইল শেষ! আবার শুরু থেকে ১টি করে দেওয়া হবে।")
        
        await client.copy_message(chat_id, FILE_CHANNEL, files[0]["msg_id"])
        await users_col.update_one({"user_id": user_id}, {"$inc": {"p_index": 1}})
        if is_cb: await update.answer("১টি ভিডিও পাঠানো হয়েছে।")
    else:
        # ফ্রি: সর্টেনার ভেরিফিকেশন লিংক
        me = await client.get_me()
        v_url = f"https://t.me/{me.username}?start=verify_{user_id}"
        short = await get_universal_shortlink(v_url)
        txt = "🚫 **ফ্রি মেম্বার ভেরিফিকেশন!**\n\n১০টি ফাইল পেতে নিচের বাটনে ক্লিক করে ভেরিফাই করুন।"
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 ভেরিফাই লিংক", url=short)]])
        if is_cb: await update.message.reply(txt, reply_markup=btn); await update.answer()
        else: await update.reply(txt, reply_markup=btn)

# ৩. PLAN কমান্ড (সকল প্ল্যান দেখা)
@app.on_message(filters.command("plan"))
@app.on_callback_query(filters.regex("btn_plans"))
async def plan_cmd(client, update):
    target = update.message if hasattr(update, "data") else update
    plans = await plans_col.find().to_list(100)
    if not plans: text = "বর্তমানে কোনো প্ল্যান নেই।"
    else:
        text = "💎 **আমাদের প্রিমিয়াম প্ল্যানসমূহ:**\n\n" + "\n".join([f"🔹 {p['days']} দিন - {p['price']} টাকা" for p in plans])
        text += f"\n\n💳 কিনতে যোগাযোগ: @{OWNER_USERNAME}"
    if hasattr(update, "data"): await update.answer()
    await target.reply(text)

# ৪. BYE_PLAN কমান্ড
@app.on_message(filters.command("bye_plan"))
async def bye_plan(client, message):
    await message.reply(f"💳 প্রিমিয়াম মেম্বারশিপ কিনতে ওনারকে মেসেজ দিন: @{OWNER_USERNAME}")

# ৫. REDEEM কমান্ড (ইউজারদের জন্য)
@app.on_message(filters.command("redeem"))
async def redeem_cmd(client, message):
    if len(message.command) < 2: return await message.reply("কোড দিন! উদা: `/redeem ABC123XYZ`")
    code = message.command[1].strip()
    data = await redeem_col.find_one({"code": code, "used": False})
    if not data: return await message.reply("❌ ভুল বা পুরাতন কোড!")
    
    delta = get_exp_time(data["dur"])
    exp = datetime.now() + delta
    await users_col.update_one({"user_id": message.from_user.id}, {"$set": {"is_premium": True, "expiry_date": exp, "p_index": 0}}, upsert=True)
    await redeem_col.update_one({"code": code}, {"$set": {"used": True}})
    await message.reply(f"🎉 প্রিমিয়াম সফল! মেয়াদ: {exp.strftime('%Y-%m-%d %H:%M')}")

# ==================== ৫. অ্যাডমিন কমান্ডস (ম্যানেজমেন্ট) ====================

# ৬. ADDPLAN (অ্যাডমিন)
@app.on_message(filters.command("addplan") & filters.user(ADMIN_ID))
async def addplan_admin(client, message):
    try:
        d, p = int(message.command[1]), int(message.command[2])
        await plans_col.update_one({"days": d}, {"$set": {"price": p}}, upsert=True)
        await message.reply(f"✅ প্ল্যান এড: {d} দিন - {p} টাকা")
    except: await message.reply("নিয়ম: `/addplan দিন টাকা`")

# ৭. DELPLAN (অ্যাডমিন)
@app.on_message(filters.command("delplan") & filters.user(ADMIN_ID))
async def delplan_admin(client, message):
    try:
        await plans_col.delete_one({"days": int(message.command[1])})
        await message.reply("🗑 প্ল্যান ডিলেট হয়েছে।")
    except: await message.reply("নিয়ম: `/delplan দিন`")

# ৮. ADD_REDEEM (অ্যাডমিন)
@app.on_message(filters.command("add_redeem") & filters.user(ADMIN_ID))
async def add_red_admin(client, message):
    try:
        dur, count = message.command[1], int(message.command[2])
        codes = []
        for _ in range(count):
            c = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            await redeem_col.insert_one({"code": c, "dur": dur, "used": False})
            codes.append(f"`{c}`")
        await message.reply(f"✅ তৈরি কোডসমূহ ({dur}):\n\n" + "\n".join(codes))
    except: await message.reply("নিয়ম: `/add_redeem 1day 5`")

# ৯. ADD_PREMIUM (অ্যাডমিন)
@app.on_message(filters.command("add_premium") & filters.user(ADMIN_ID))
async def add_prem_manual(client, message):
    try:
        u, d = int(message.command[1]), int(message.command[2])
        exp = datetime.now() + timedelta(days=d)
        await users_col.update_one({"user_id": u}, {"$set": {"is_premium": True, "expiry_date": exp, "p_index": 0}}, upsert=True)
        await message.reply(f"✅ ইউজার {u} কে {d} দিনের প্রিমিয়াম দেওয়া হয়েছে।")
    except: await message.reply("নিয়ম: `/add_premium ID দিন`")

# ১০. SET_SHORTENER (অ্যাডমিন)
@app.on_message(filters.command("set_shortener") & filters.user(ADMIN_ID))
async def set_short_admin(client, message):
    try:
        u, k = message.command[1], message.command[2]
        await settings_col.update_one({"id": "shortener"}, {"$set": {"base_url": u, "api_key": k}}, upsert=True)
        await message.reply(f"✅ সর্টেনার সেট: {u}")
    except: await message.reply("নিয়ম: `/set_shortener Domain API_KEY`")

@app.on_message(filters.command("del_shortener") & filters.user(ADMIN_ID))
async def del_short_admin(client, message):
    await settings_col.delete_one({"id": "shortener"})
    await message.reply("🗑 সর্টেনার ডিলেট হয়েছে।")

# ==================== ৬. অটো সেভ ও লগিং ====================

@app.on_message(filters.chat(FILE_CHANNEL) & (filters.video | filters.document))
async def auto_save_handler(client, message):
    # ডাটাবেসে ফাইল সেভ
    await files_col.insert_one({"msg_id": message.id, "time": datetime.now()})
    
    # সর্ট লিংক জেনারেশন (লগ চ্যানেলের জন্য)
    me = await client.get_me()
    d_url = f"https://t.me/{me.username}?start=verify_{message.id}"
    s_url = await get_universal_shortlink(d_url)
    
    await client.send_message(LOG_CHANNEL, f"✅ **নতুন ভিডিও সেভ হয়েছে!**\n\n🔗 ডিরেক্ট লিংক: `{d_url}`\n🚀 সর্ট লিংক: {s_url}")

# ==================== ৭. রান কমান্ডস ====================
print("বটটি সফলভাবে চালু হয়েছে! 🚀")
app.run()
