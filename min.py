import asyncio
import random
import string
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta

# ==================== ১. কনফিগারেশন ====================
API_ID = 1234567                 
API_HASH = "your_api_hash"        
BOT_TOKEN = "your_bot_token"      
ADMIN_ID = 12345678              # আপনার আইডি
LOG_CHANNEL = -100...             # লগ চ্যানেল
FILE_CHANNEL = -100...            # ফাইল চ্যানেল
MONGODB_URI = "mongodb+srv://..."   # ডাটাবেস লিংক
OWNER_USERNAME = "YourUsername"   # আপনার ইউজারনেম (@ ছাড়া)

app = Client("file_store_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db = AsyncIOMotorClient(MONGODB_URI)["file_store_bot"]
users_col, files_col, plans_col, redeem_col, settings_col = db.users, db.files, db.plans, db.redeem, db.settings

# ==================== সাহায্যকারী ফাংশন ====================
async def is_premium(user_id):
    user = await users_col.find_one({"user_id": user_id})
    if user and user.get("is_premium"):
        if datetime.now() > user.get("expiry_date"):
            await users_col.update_one({"user_id": user_id}, {"$set": {"is_premium": False}})
            return False, "Free"
        return True, user.get("expiry_date").strftime('%Y-%m-%d')
    return False, "Free"

async def get_short(url):
    s = await settings_col.find_one({"id": "shortener"})
    if not s: return url
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(f"https://{s['base_url']}/api?api={s['api_key']}&url={url}") as r:
                data = await r.json()
                return data.get("shortenedUrl") or data.get("url") or url
    except: return url

def parse_time(t_str):
    n = int(''.join(filter(str.isdigit, t_str)))
    if "min" in t_str: return timedelta(minutes=n)
    if "hour" in t_str: return timedelta(hours=n)
    if "day" in t_str: return timedelta(days=n)
    if "month" in t_str: return timedelta(days=n*30)
    return None

# ==================== ১০টি কমান্ডের লজিক ====================

# ১. START কমান্ড
@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    # ইউজার ডাটাবেস আপডেট
    await users_col.update_one({"user_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)
    user_data = await users_col.find_one({"user_id": user_id})

    # ভেরিফিকেশন (ফ্রি ১০টি ফাইল)
    if len(message.command) > 1 and "verify" in message.command[1]:
        f_idx = user_data.get("f_index", 0)
        files = await files_col.find().sort("_id", 1).skip(f_idx).limit(10).to_list(10)
        if not files:
            await users_col.update_one({"user_id": user_id}, {"$set": {"f_index": 0}})
            return await message.reply("ফাইল শেষ! আবার শুরু থেকে নিন।")
        await message.reply("✅ ভেরিফিকেশন সফল! ১০টি ফাইল পাঠানো হচ্ছে...")
        for f in files:
            await client.copy_message(user_id, FILE_CHANNEL, f["msg_id"]); await asyncio.sleep(1)
        await users_col.update_one({"user_id": user_id}, {"$inc": {"f_index": 10}})
        return

    premium, expiry = await is_premium(user_id)
    txt = f"👋 স্বাগতম {message.from_user.first_name}!\n🆔 আইডি: `{user_id}`\n💎 স্ট্যাটাস: {'Premium 🌟' if premium else 'Regular 👤'}\n📅 মেয়াদ: {expiry}\n\nফাইল পেতে /getfile দিন।"
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("📂 Get Files", callback_data="get_file")],
                                 [InlineKeyboardButton("💎 Plans", callback_data="plans"),
                                  InlineKeyboardButton("Owner 👑", url=f"https://t.me/{OWNER_USERNAME}")]])
    try:
        async for photo in client.get_chat_photos(user_id, limit=1):
            await message.reply_photo(photo.file_id, caption=txt, reply_markup=btn); return
    except: pass
    await message.reply_text(txt, reply_markup=btn)

# ২. GETFILE কমান্ড
@app.on_message(filters.command("getfile"))
@app.on_callback_query(filters.regex("get_file"))
async def get_file_cmd(client, update):
    user_id = update.from_user.id
    chat_id = update.message.chat.id if hasattr(update, "data") else update.chat.id
    premium, _ = await is_premium(user_id)
    user_data = await users_col.find_one({"user_id": user_id})

    if premium:
        # প্রিমিয়াম: ১টি ফাইল
        idx = user_data.get("p_index", 0)
        files = await files_col.find().sort("_id", 1).skip(idx).limit(1).to_list(1)
        if not files:
            await users_col.update_one({"user_id": user_id}, {"$set": {"p_index": 0}})
            return await client.send_message(chat_id, "ফাইল শেষ! রিসেট হয়েছে।")
        await client.copy_message(chat_id, FILE_CHANNEL, files[0]["msg_id"])
        await users_col.update_one({"user_id": user_id}, {"$inc": {"p_index": 1}})
    else:
        # ফ্রি: ১০টি ফাইল (সর্টেনার)
        me = await client.get_me()
        v_url = await get_short(f"https://t.me/{me.username}?start=verify_{user_id}")
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 ভেরিফাই ও ১০টি ফাইল নিন", url=v_url)]])
        await client.send_message(chat_id, "🚫 ফ্রি ইউজারদের ভেরিফাই করলে ১০টি ফাইল দেওয়া হয়।", reply_markup=btn)

# ৩. PLAN কমান্ড
@app.on_message(filters.command("plan"))
@app.on_callback_query(filters.regex("plans"))
async def plan_list(client, update):
    target = update.message if hasattr(update, "data") else update
    all_plans = await plans_col.find().to_list(100)
    txt = "💎 **আমাদের প্ল্যানসমূহ:**\n\n" + "\n".join([f"🔹 {p['days']} দিন - {p['price']} টাকা" for p in all_plans])
    txt += f"\n\n💳 কিনতে যোগাযোগ: @{OWNER_USERNAME}"
    await target.reply(txt)

# ৪. BYE_PLAN কমান্ড
@app.on_message(filters.command("bye_plan"))
async def bye_plan(client, message):
    await message.reply(f"💳 প্ল্যান কিনতে চাইলে আপনার পছন্দের প্ল্যানটি বেছে নিয়ে ওনারকে মেসেজ দিন: @{OWNER_USERNAME}")

# ৫. REDEEM কমান্ড
@app.on_message(filters.command("redeem"))
async def redeem(client, message):
    if len(message.command) < 2: return await message.reply("কোড দিন! উদা: `/redeem ABC123XYZ`")
    code = message.command[1]
    data = await redeem_col.find_one({"code": code, "used": False})
    if not data: return await message.reply("❌ ভুল বা পুরাতন কোড!")
    expiry = datetime.now() + parse_time(data["dur"])
    await users_col.update_one({"user_id": message.from_user.id}, {"$set": {"is_premium": True, "expiry_date": expiry}}, upsert=True)
    await redeem_col.update_one({"code": code}, {"$set": {"used": True}})
    await message.reply(f"🎉 প্রিমিয়াম সাকসেস! মেয়াদ: {expiry.strftime('%Y-%m-%d')}")

# ৬. ADDPLAN কমান্ড (Admin)
@app.on_message(filters.command("addplan") & filters.user(ADMIN_ID))
async def addplan(client, message):
    try:
        days, price = int(message.command[1]), int(message.command[2])
        await plans_col.update_one({"days": days}, {"$set": {"price": price}}, upsert=True)
        await message.reply("✅ প্ল্যান সেভ হয়েছে।")
    except: await message.reply("উদা: `/addplan 30 100` (৩০ দিন ১০০ টাকা)")

# ৭. DELPLAN কমান্ড (Admin)
@app.on_message(filters.command("delplan") & filters.user(ADMIN_ID))
async def delplan(client, message):
    try:
        await plans_col.delete_one({"days": int(message.command[1])})
        await message.reply("🗑 প্ল্যান ডিলেট হয়েছে।")
    except: await message.reply("উদা: `/delplan 30`")

# ৮. ADD_REDEEM কমান্ড (Admin)
@app.on_message(filters.command("add_redeem") & filters.user(ADMIN_ID))
async def add_red(client, message):
    try:
        dur, count = message.command[1], int(message.command[2])
        codes = []
        for _ in range(count):
            c = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            await redeem_col.insert_one({"code": c, "dur": dur, "used": False})
            codes.append(f"`{c}`")
        await message.reply(f"✅ তৈরি কোড ({dur}):\n\n" + "\n".join(codes))
    except: await message.reply("উদা: `/add_redeem 1month 5`")

# ৯. ADD_PREMIUM কমান্ড (Admin)
@app.on_message(filters.command("add_premium") & filters.user(ADMIN_ID))
async def add_prem(client, message):
    try:
        u_id, days = int(message.command[1]), int(message.command[2])
        exp = datetime.now() + timedelta(days=days)
        await users_col.update_one({"user_id": u_id}, {"$set": {"is_premium": True, "expiry_date": exp}}, upsert=True)
        await message.reply(f"✅ ইউজার {u_id} এখন প্রিমিয়াম।")
    except: await message.reply("উদা: `/add_premium 123456 30`")

# ১০. SET_SHORTENER কমান্ড (Admin)
@app.on_message(filters.command("set_shortener") & filters.user(ADMIN_ID))
async def set_sh(client, message):
    try:
        await settings_col.update_one({"id": "shortener"}, {"$set": {"base_url": message.command[1], "api_key": message.command[2]}}, upsert=True)
        await message.reply("✅ সর্টেনার সেট হয়েছে।")
    except: await message.reply("উদা: `/set_shortener gplinks.in API_KEY`")

# অতিরিক্ত: DEL_SHORTENER
@app.on_message(filters.command("del_shortener") & filters.user(ADMIN_ID))
async def del_sh(client, message):
    await settings_col.delete_one({"id": "shortener"})
    await message.reply("🗑 সর্টেনার রিমুভ হয়েছে।")

# অটো সেভ লজিক
@app.on_message(filters.chat(FILE_CHANNEL) & (filters.video | filters.document))
async def auto_save(client, message):
    await files_col.insert_one({"msg_id": message.id})
    await client.send_message(LOG_CHANNEL, f"✅ নতুন ফাইল সেভ হয়েছে! ID: {message.id}")

app.run()
