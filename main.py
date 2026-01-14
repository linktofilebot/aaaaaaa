import asyncio
import random
import string
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta

# ==================== ১. কনফিগারেশন (এখানে আপনার তথ্য দিন) ====================
API_ID = 29904834                 # আপনার API ID
API_HASH = "8b4fd9ef578af114502feeafa2d31938"        # আপনার API Hash
BOT_TOKEN = "8061645932:AAE8HJGB_culcQ-EVtycl2GSrysTPMxTOHM"      # BotFather থেকে পাওয়া টোকেন
ADMIN_ID = 7525127704              # আপনার টেলিগ্রাম আইডি
LOG_CHANNEL = -1003400020848       # লগ চ্যানেল আইডি (অবশ্যই -100 সহ)
FILE_CHANNEL = -1003513942313      # ফাইল চ্যানেল আইডি (অবশ্যই -100 সহ)
MONGODB_URI = "mongodb+srv://Demo270:Demo270@cluster0.ls1igsg.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"   # আপনার MongoDB কানেকশন স্ট্রিং
OWNER_USERNAME = "AkashDeveloperBot"   # আপনার ইউজারনেম (@ ছাড়া)

# ==================== ২. ডাটাবেস ও ক্লায়েন্ট সেটআপ ====================
db_client = AsyncIOMotorClient(MONGODB_URI)
db = db_client["file_store_pro_db"]
users_col = db["users"]
files_col = db["stored_files"]
plans_col = db["plans"]
redeem_col = db["redeem_codes"]
settings_col = db["settings"]

app = Client("file_store_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ==================== ৩. সাহায্যকারী ফাংশনসমূহ (Helpers) ====================

# প্রিমিয়াম চেক এবং মেয়াদ যাচাই
async def check_premium(user_id):
    user = await users_col.find_one({"user_id": user_id})
    if user and user.get("is_premium"):
        expiry = user.get("expiry_date")
        if expiry and datetime.now() > expiry:
            await users_col.update_one({"user_id": user_id}, {"$set": {"is_premium": False}})
            return False, "Free User (Expired)"
        return True, expiry.strftime('%Y-%m-%d %H:%M')
    return False, "Regular Member"

# ইউনিভার্সাল সর্টেনার ফাংশন
async def get_shortlink(url):
    s = await settings_col.find_one({"id": "shortener"})
    if not s: return url
    api_url = f"https://{s['base_url']}/api?api={s['api_key']}&url={url}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=10) as res:
                data = await res.json()
                # বিভিন্ন সর্টেনার সাইটের জন্য কমন রেসপন্স চেক
                return data.get("shortenedUrl") or data.get("shortlink") or data.get("url") or url
    except: return url

# সময় কনভার্টার (1min, 1hour, 1day, 1month)
def parse_duration(t_str):
    try:
        num = int(''.join(filter(str.isdigit, t_str)))
        if "min" in t_str: return timedelta(minutes=num)
        if "hour" in t_str: return timedelta(hours=num)
        if "day" in t_str: return timedelta(days=num)
        if "month" in t_str: return timedelta(days=num * 30)
    except: return None
    return None

# ==================== ৪. ইউজার ও অ্যাডমিন কমান্ড হ্যান্ডলার ====================

# ১. /start কমান্ড: প্রোফাইল কার্ড, লোগো এবং ফ্রি ভেরিফিকেশন হ্যান্ডলার
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    user_id = message.from_user.id
    
    # নতুন ইউজার হলে ডাটাবেসে এড করা
    user_data = await users_col.find_one({"user_id": user_id})
    if not user_data:
        user_data = {"user_id": user_id, "is_premium": False, "p_index": 0, "f_index": 0}
        await users_col.update_one({"user_id": user_id}, {"$set": user_data}, upsert=True)
        user_data = await users_col.find_one({"user_id": user_id})

    # ফ্রি ইউজার ভেরিফিকেশন প্রসেস (লিংকের মাধ্যমে ফিরে আসলে)
    if len(message.command) > 1 and message.command[1].startswith("verify"):
        is_prem, _ = await check_premium(user_id)
        if is_prem: 
            return await message.reply("আপনি প্রিমিয়াম মেম্বার, আপনার ভেরিফিকেশন প্রয়োজন নেই।")
        
        # ডাটাবেস থেকে ১০টি ফাইল পাঠানো (সিরিয়াল অনুযায়ী)
        f_idx = user_data.get("f_index", 0)
        files = await files_col.find().sort("_id", 1).skip(f_idx).limit(10).to_list(10)
        
        if not files:
            await users_col.update_one({"user_id": user_id}, {"$set": {"f_index": 0}}) # রিসেট
            return await message.reply("সব ভিডিও দেখা শেষ! গেট ফাইলে ক্লিক করে আবার শুরু থেকে দেখুন।")
            
        await message.reply("✅ ভেরিফিকেশন সফল! আপনার ১০টি ভিডিও ক্রমানুসারে পাঠানো হচ্ছে...")
        for f in files:
            try:
                await client.copy_message(user_id, FILE_CHANNEL, f["msg_id"])
                await asyncio.sleep(1.5) # ফ্লাড এড়াতে গ্যাপ
            except Exception as e:
                print(f"Error copying file: {e}")
        
        # ইনডেক্স ১০ বাড়ানো
        await users_col.update_one({"user_id": user_id}, {"$inc": {"f_index": 10}})
        return

    # সাধারণ স্টার্ট মেসেজ (প্রোফাইল কার্ড ও লোগোসহ)
    is_prem, status_txt = await check_premium(user_id)
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Get Files", callback_data="get_file_logic")],
        [InlineKeyboardButton("💎 View Plans", callback_data="show_plans_logic"),
         InlineKeyboardButton("Owner 👑", url=f"https://t.me/{OWNER_USERNAME}")]
    ])
    
    start_text = (f"👋 আসসালামু আলাইকুম {message.from_user.first_name}!\n\n"
                  f"🆔 **আপনার আইডি:** `{user_id}`\n"
                  f"🎭 **আপনার নাম:** {message.from_user.first_name}\n"
                  f"💎 **মেম্বারশিপ:** {status_txt}\n\n"
                  "ফাইল পেতে নিচের বাটনে ক্লিক করুন অথবা কমান্ড দিন।")
    
    # ইউজারের প্রোফাইল ফটো নেওয়া
    try:
        async for photo in client.get_chat_photos(user_id, limit=1):
            await message.reply_photo(photo=photo.file_id, caption=start_text, reply_markup=btn)
            return
    except: pass
    await message.reply_text(start_text, reply_markup=btn)

# ২. /getfile কমান্ড: ফ্রি মেম্বারকে সর্ট লিংক এবং প্রিমিয়ামকে সরাসরি ১টি ফাইল
@app.on_callback_query(filters.regex("get_file_logic"))
@app.on_message(filters.command("getfile"))
async def getfile_handler(client, update):
    is_cb = hasattr(update, "data")
    user_id = update.from_user.id
    chat_id = update.message.chat.id if is_cb else update.chat.id
    
    user_data = await users_col.find_one({"user_id": user_id})
    is_prem, _ = await check_premium(user_id)

    if is_prem:
        # প্রিমিয়াম লজিক: ১টি ফাইল প্রতি ক্লিকে সিরিয়ালে
        p_idx = user_data.get("p_index", 0)
        files = await files_col.find().sort("_id", 1).skip(p_idx).limit(1).to_list(1)
        if not files:
            await users_col.update_one({"user_id": user_id}, {"$set": {"p_index": 0}}) # রিসেট
            return await client.send_message(chat_id, "সব ফাইল শেষ! আবার প্রথম থেকে ১টি করে দেওয়া হবে।")
        
        await client.copy_message(chat_id, FILE_CHANNEL, files[0]["msg_id"])
        await users_col.update_one({"user_id": user_id}, {"$inc": {"p_index": 1}})
        if is_cb: await update.answer("১টি ভিডিও পাঠানো হয়েছে।")
    else:
        # ফ্রি লজিক: সর্টেনার লিংক জেনারেট
        me = await client.get_me()
        verify_url = f"https://t.me/{me.username}?start=verify_{user_id}"
        short_link = await get_shortlink(verify_url)
        txt = "🚫 **ভেরিফিকেশন বাধ্যতামূলক!**\n\n১০টি ফাইল পেতে নিচের লিংকে ক্লিক করে ভেরিফাই করুন।"
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 ভেরিফাই লিংক", url=short_link)]])
        if is_cb: await update.message.reply(txt, reply_markup=btn); await update.answer()
        else: await update.reply(txt, reply_markup=btn)

# ৩. /plan কমান্ড: প্ল্যান লিস্ট দেখা
@app.on_message(filters.command("plan"))
@app.on_callback_query(filters.regex("show_plans_logic"))
async def plan_cmd(client, update):
    target = update.message if hasattr(update, "data") else update
    plans = await plans_col.find().to_list(100)
    if not plans:
        text = "বর্তমানে কোনো নির্দিষ্ট প্ল্যান সেট করা নেই।"
    else:
        text = "💎 **আমাদের প্রিমিয়াম প্ল্যানসমূহ:**\n\n" + "\n".join([f"🔹 {p['days']} দিন - {p['price']} টাকা" for p in plans])
        text += f"\n\n💳 কিনতে ওনারকে মেসেজ দিন: @{OWNER_USERNAME}"
    if hasattr(update, "data"): await update.answer()
    await target.reply(text)

# ৪. /bye_plan কমান্ড: প্ল্যান কেনার তথ্য
@app.on_message(filters.command("bye_plan"))
async def bye_plan_cmd(client, message):
    await message.reply(f"💳 প্রিমিয়াম মেম্বারশিপ কিনতে ওনারের সাথে যোগাযোগ করুন: @{OWNER_USERNAME}")

# ৫. /redeem [CODE] কমান্ড: ইউজার রিডিম কোড ব্যবহার করা
@app.on_message(filters.command("redeem"))
async def redeem_cmd(client, message):
    if len(message.command) < 2: return await message.reply("কোড দিন! উদা: `/redeem WK7jd0TjTe`")
    code_str = message.command[1].strip()
    data = await redeem_col.find_one({"code": code_str, "is_used": False})
    if not data: return await message.reply("❌ ভুল বা পুরাতন কোড!")
    
    delta = parse_duration(data["duration"])
    expiry = datetime.now() + delta
    await users_col.update_one({"user_id": message.from_user.id}, 
                                {"$set": {"is_premium": True, "expiry_date": expiry, "p_index": 0}}, upsert=True)
    await redeem_col.update_one({"code": code_str}, {"$set": {"is_used": True}})
    await message.reply(f"🎉 অভিনন্দন! প্রিমিয়াম সফলভাবে একটিভ হয়েছে।\n📅 মেয়াদ শেষ: {expiry.strftime('%Y-%m-%d %H:%M')}")

# ==================== ৫. অ্যাডমিন কমান্ডসমূহ (শুধুমাত্র আপনি) ====================

# ৬. /addplan [দিন] [টাকা]
@app.on_message(filters.command("addplan") & filters.user(ADMIN_ID))
async def addplan_admin(client, message):
    try:
        days, price = int(message.command[1]), int(message.command[2])
        await plans_col.update_one({"days": days}, {"$set": {"price": price}}, upsert=True)
        await message.reply(f"✅ প্ল্যান এড হয়েছে: {days} দিন - {price} টাকা")
    except: await message.reply("সঠিক নিয়ম: `/addplan দিন টাকা` (উদা: /addplan 30 100)")

# ৭. /delplan [দিন]
@app.on_message(filters.command("delplan") & filters.user(ADMIN_ID))
async def delplan_admin(client, message):
    try:
        days = int(message.command[1])
        await plans_col.delete_one({"days": days})
        await message.reply(f"✅ {days} দিনের প্ল্যান ডিলেট হয়েছে।")
    except: await message.reply("সঠিক নিয়ম: `/delplan দিন` (উদা: /delplan 30)")

# ৮. /add_redeem [সময়] [সংখ্যা]
@app.on_message(filters.command("add_redeem") & filters.user(ADMIN_ID))
async def add_red_admin(client, message):
    try:
        duration, count = message.command[1], int(message.command[2])
        codes = []
        for _ in range(count):
            c = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            await redeem_col.insert_one({"code": c, "duration": duration, "is_used": False})
            codes.append(f"`{c}`")
        await message.reply(f"✅ {duration} মেয়াদের {count}টি রিডিম কোড তৈরি হয়েছে:\n\n" + "\n".join(codes))
    except: await message.reply("সঠিক নিয়ম: `/add_redeem 1day 5` (উদা: /add_redeem 1month 10)")

# ৯. /add_premium [ID] [দিন]
@app.on_message(filters.command("add_premium") & filters.user(ADMIN_ID))
async def add_prem_manual(client, message):
    try:
        u_id, days = int(message.command[1]), int(message.command[2])
        expiry = datetime.now() + timedelta(days=days)
        await users_col.update_one({"user_id": u_id}, {"$set": {"is_premium": True, "expiry_date": expiry, "p_index": 0}}, upsert=True)
        await message.reply(f"✅ ইউজার {u_id} এখন {days} দিনের জন্য প্রিমিয়াম মেম্বার।")
    except: await message.reply("সঠিক নিয়ম: `/add_premium ID দিন` (উদা: /add_premium 12345 30)")

# ১০. /set_shortener [Domain] [API]
@app.on_message(filters.command("set_shortener") & filters.user(ADMIN_ID))
async def set_short_admin(client, message):
    try:
        url, key = message.command[1], message.command[2]
        await settings_col.update_one({"id": "shortener"}, {"$set": {"base_url": url, "api_key": key}}, upsert=True)
        await message.reply(f"✅ সর্টেনার সেট হয়েছে: {url}")
    except: await message.reply("সঠিক নিয়ম: `/set_shortener Domain API` (উদা: /set_shortener shareus.io api_key)")

# ১১. /del_shortener
@app.on_message(filters.command("del_shortener") & filters.user(ADMIN_ID))
async def del_short_admin(client, message):
    await settings_col.delete_one({"id": "shortener"})
    await message.reply("🗑 সর্টেনার মুছে ফেলা হয়েছে। এখন ডিরেক্ট লিংক জেনারেট হবে।")

# ==================== ৭. অটো ফাইল সেভ ও লগিং (চ্যানেল থেকে) ====================

@app.on_message(filters.chat(FILE_CHANNEL) & (filters.video | filters.document | filters.audio))
async def auto_save_handler(client, message):
    # ডাটাবেসে ফাইল আইডি সেভ করা
    await files_col.insert_one({"msg_id": message.id, "added_at": datetime.now()})
    
    # লগ চ্যানেলের জন্য লিংক তৈরি
    me = await client.get_me()
    direct_link = f"https://t.me/{me.username}?start=verify_{message.id}"
    short_link = await get_shortlink(direct_link)
    
    log_text = (f"✅ **নতুন ফাইল ডাটাবেসে সেভ হয়েছে!**\n\n"
                f"🔗 ডিরেক্ট ভেরিফাই লিংক: `{direct_link}`\n"
                f"🚀 সর্ট লিংক (ফ্রি মেম্বার): {short_link}")
    
    await client.send_message(LOG_CHANNEL, log_text)

# ==================== ৮. রান কমান্ডস ====================
print("অভিনন্দন! আপনার বটের পূর্ণাঙ্গ ফাইনাল কোডটি এখন সক্রিয়। 🚀")
app.run()
