from aiohttp import web
import asyncio
import random
import string
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta

# ==================== ১. কনফিগারেশন ====================
API_ID = 29904834                 
API_HASH = "8b4fd9ef578af114502feeafa2d31938"        
BOT_TOKEN = "8061645932:AAE8HJGB_culcQ-EVtycl2GSrysTPMxTOHM"      
ADMIN_ID = 7525127704              
LOG_CHANNEL = -1003400020848       
FILE_CHANNEL = -1003513942313      
MONGODB_URI = "mongodb+srv://Demo270:Demo270@cluster0.ls1igsg.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"   
OWNER_USERNAME = "AkashDeveloperBot"   

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

# সময়কে সুন্দরভাবে (মাস, সপ্তাহ, দিন, ঘণ্টা, মিনিট, সেকেন্ড) রূপান্তর করার ফাংশন
def get_readable_time(expiry_date):
    delta = expiry_date - datetime.now()
    seconds = int(delta.total_seconds())
    
    if seconds <= 0:
        return "Expired"

    months, seconds = divmod(seconds, 30 * 24 * 3600)
    weeks, seconds = divmod(seconds, 7 * 24 * 3600)
    days, seconds = divmod(seconds, 24 * 3600)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    
    parts = []
    if months: parts.append(f"{months} মাস")
    if weeks: parts.append(f"{weeks} সপ্তাহ")
    if days: parts.append(f"{days} দিন")
    if hours: parts.append(f"{hours} ঘণ্টা")
    if minutes: parts.append(f"{minutes} মিনিট")
    if seconds: parts.append(f"{seconds} সেকেন্ড")
    
    return ", ".join(parts)

# ইউজার ও লগ চ্যানেলে প্রিমিয়াম নোটিফিকেশন পাঠানোর ফাংশন
async def send_premium_report(client, user_id, expiry_date, method="Redeem Code"):
    try:
        user = await client.get_users(user_id)
        readable_time = get_readable_time(expiry_date)
        username = f"@{user.username}" if user.username else "None"
        
        report_text = (
            f"🚀 **প্রিমিয়াম মেম্বারশিপ আপডেট**\n\n"
            f"👤 **নাম:** {user.first_name}\n"
            f"🆔 **আইডি:** `{user.id}`\n"
            f"🔗 **ইউজারনেম:** {username}\n"
            f"⏳ **মেয়াদ:** {readable_time}\n"
            f"📅 **শেষ হবে:** {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"🛠 **পদ্ধতি:** {method}"
        )

        # লগ চ্যানেলে পাঠানো (ফটোসহ)
        try:
            photo_id = None
            async for photo in client.get_chat_photos(user_id, limit=1):
                photo_id = photo.file_id
            
            if photo_id:
                await client.send_photo(LOG_CHANNEL, photo_id, caption=report_text)
            else:
                await client.send_message(LOG_CHANNEL, report_text)
        except:
            await client.send_message(LOG_CHANNEL, report_text)

        # ইউজারকে পার্সোনাল মেসেজ পাঠানো
        await client.send_message(user_id, f"🎉 **অভিনন্দন! আপনার প্রিমিয়াম সফলভাবে একটিভ হয়েছে।**\n\n{report_text}")
        
    except Exception as e:
        print(f"Report Error: {e}")

# প্রিমিয়াম চেক
async def check_premium(user_id):
    user = await users_col.find_one({"user_id": user_id})
    if user and user.get("is_premium"):
        expiry = user.get("expiry_date")
        if expiry and datetime.now() > expiry:
            await users_col.update_one({"user_id": user_id}, {"$set": {"is_premium": False}})
            return False, "Free User (Expired)"
        return True, expiry.strftime('%Y-%m-%d %H:%M')
    return False, "Regular Member"

# সর্টেনার ফাংশন
async def get_shortlink(url):
    s = await settings_col.find_one({"id": "shortener"})
    if not s: return url
    api_url = f"https://{s['base_url']}/api?api={s['api_key']}&url={url}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=10) as res:
                data = await res.json()
                return data.get("shortenedUrl") or data.get("shortlink") or data.get("url") or url
    except: return url

# সময় কনভার্টার
def parse_duration(t_str):
    try:
        num = int(''.join(filter(str.isdigit, t_str)))
        if "min" in t_str: return timedelta(minutes=num)
        if "hour" in t_str: return timedelta(hours=num)
        if "day" in t_str: return timedelta(days=num)
        if "month" in t_str: return timedelta(days=num * 30)
    except: return None
    return None

# অ্যান্টি-ফরোয়ার্ড চেক
async def is_protect_on():
    data = await settings_col.find_one({"id": "forward_setting"})
    if data: return data.get("protect", False)
    return False

# ==================== ৪. ইউজার ও অ্যাডমিন কমান্ড হ্যান্ডলার ====================

@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    user_id = message.from_user.id
    
    # লগ চ্যানেলে ইউজারের তথ্য পাঠানো
    log_txt = (f"👤 **নতুন ইউজার অ্যাক্টিভিটি**\n\n"
               f"🆔 আইডি: `{user_id}`\n"
               f"🎭 নাম: {message.from_user.first_name}\n"
               f"🔗 ইউজারনেম: @{message.from_user.username if message.from_user.username else 'None'}")
    await client.send_message(LOG_CHANNEL, log_txt)

    # নতুন ইউজার হলে ডাটাবেসে এড করা
    user_data = await users_col.find_one({"user_id": user_id})
    if not user_data:
        user_data = {"user_id": user_id, "is_premium": False, "p_index": 0, "f_index": 0}
        await users_col.update_one({"user_id": user_id}, {"$set": user_data}, upsert=True)

    # ভেরিফিকেশন হ্যান্ডলিং
    if len(message.command) > 1 and message.command[1].startswith("verify"):
        is_prem, _ = await check_premium(user_id)
        if is_prem: 
            return await message.reply("আপনি প্রিমিয়াম মেম্বার, আপনার ভেরিফিকেশন প্রয়োজন নেই।")
        
        user_data = await users_col.find_one({"user_id": user_id})
        f_idx = user_data.get("f_index", 0)
        files = await files_col.find().sort("_id", 1).skip(f_idx).limit(10).to_list(10)
        
        if not files:
            await users_col.update_one({"user_id": user_id}, {"$set": {"f_index": 0}}) 
            return await message.reply("সব ভিডিও দেখা শেষ! গেট ফাইলে ক্লিক করে আবার শুরু থেকে দেখুন।")
            
        await message.reply("✅ ভেরিফিকেশন সফল! আপনার ১০টি ভিডিও ক্রমানুসারে পাঠানো হচ্ছে...")
        
        p_on = await is_protect_on()
        for f in files:
            try:
                await client.copy_message(user_id, FILE_CHANNEL, f["msg_id"], protect_content=p_on)
                await asyncio.sleep(1.5) 
            except Exception as e:
                print(f"Error: {e}")
        
        await users_col.update_one({"user_id": user_id}, {"$inc": {"f_index": 10}})
        return

    # সাধারণ স্টার্ট মেসেজ
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
    
    try:
        async for photo in client.get_chat_photos(user_id, limit=1):
            await message.reply_photo(photo=photo.file_id, caption=start_text, reply_markup=btn)
            return
    except: pass
    await message.reply_text(start_text, reply_markup=btn)

@app.on_callback_query(filters.regex("get_file_logic"))
@app.on_message(filters.command("getfile"))
async def getfile_handler(client, update):
    is_cb = hasattr(update, "data")
    user_id = update.from_user.id
    chat_id = update.message.chat.id if is_cb else update.chat.id
    
    user_data = await users_col.find_one({"user_id": user_id})
    is_prem, _ = await check_premium(user_id)

    if is_prem:
        p_idx = user_data.get("p_index", 0)
        files = await files_col.find().sort("_id", 1).skip(p_idx).limit(1).to_list(1)
        if not files:
            await users_col.update_one({"user_id": user_id}, {"$set": {"p_index": 0}}) 
            return await client.send_message(chat_id, "সব ফাইল শেষ! আবার প্রথম থেকে ১টি করে দেওয়া হবে।")
        
        p_on = await is_protect_on()
        await client.copy_message(chat_id, FILE_CHANNEL, files[0]["msg_id"], protect_content=p_on)
        await users_col.update_one({"user_id": user_id}, {"$inc": {"p_index": 1}})
        if is_cb: await update.answer("১টি ভিডিও পাঠানো হয়েছে।")
    else:
        me = await client.get_me()
        verify_url = f"https://t.me/{me.username}?start=verify_{user_id}"
        short_link = await get_shortlink(verify_url)
        txt = "🚫 **ভেরিফিকেশন বাধ্যতামূলক!**\n\n১০টি ফাইল পেতে নিচের লিংকে ক্লিক করে ভেরিফাই করুন।"
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 ভেরিফাই লিংক", url=short_link)]])
        if is_cb: await update.message.reply(txt, reply_markup=btn); await update.answer()
        else: await update.reply(txt, reply_markup=btn)

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
    
    # রিপোর্ট পাঠানো (নতুন)
    await send_premium_report(client, message.from_user.id, expiry, method=f"Redeem Code ({data['duration']})")

@app.on_message(filters.command("add_premium") & filters.user(ADMIN_ID))
async def add_prem_manual(client, message):
    try:
        u_id, days = int(message.command[1]), int(message.command[2])
        expiry = datetime.now() + timedelta(days=days)
        await users_col.update_one({"user_id": u_id}, {"$set": {"is_premium": True, "expiry_date": expiry, "p_index": 0}}, upsert=True)
        await message.reply(f"✅ ইউজার {u_id} এখন {days} দিনের জন্য প্রিমিয়াম মেম্বার।")
        
        # রিপোর্ট পাঠানো (নতুন)
        await send_premium_report(client, u_id, expiry, method=f"Admin Manual ({days} Days)")
    except: await message.reply("সঠিক নিয়ম: `/add_premium ID দিন` (উদা: /add_premium 12345 30)")

# ==================== ৫. অ্যাডমিন কমান্ডসমূহ ====================

@app.on_message(filters.command("addplan") & filters.user(ADMIN_ID))
async def addplan_admin(client, message):
    try:
        days, price = int(message.command[1]), int(message.command[2])
        await plans_col.update_one({"days": days}, {"$set": {"price": price}}, upsert=True)
        await message.reply(f"✅ প্ল্যান এড হয়েছে: {days} দিন - {price} টাকা")
    except: await message.reply("সঠিক নিয়ম: `/addplan দিন টাকা`")

@app.on_message(filters.command("delplan") & filters.user(ADMIN_ID))
async def delplan_admin(client, message):
    try:
        days = int(message.command[1])
        await plans_col.delete_one({"days": days})
        await message.reply(f"✅ {days} দিনের প্ল্যান ডিলেট হয়েছে।")
    except: await message.reply("সঠিক নিয়ম: `/delplan দিন`")

@app.on_message(filters.command("add_redeem") & filters.user(ADMIN_ID))
async def add_red_admin(client, message):
    try:
        duration, count = message.command[1], int(message.command[2])
        codes = []
        for _ in range(count):
            c = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
            await redeem_col.insert_one({"code": c, "duration": duration, "is_used": False})
            codes.append(f"`{c}`")
        await message.reply(f"✅ তৈরি হয়েছে:\n" + "\n".join(codes))
    except: await message.reply("সঠিক নিয়ম: `/add_redeem 1day 5`")

@app.on_message(filters.command("remove_premium") & filters.user(ADMIN_ID))
async def remove_prem_admin(client, message):
    try:
        u_id = int(message.command[1])
        await users_col.update_one({"user_id": u_id}, {"$set": {"is_premium": False}, "$unset": {"expiry_date": ""}})
        await message.reply(f"✅ ইউজার {u_id}-এর প্রিমিয়াম রিমুভ করা হয়েছে।")
    except: await message.reply("সঠিক নিয়ম: `/remove_premium ID`")

@app.on_message(filters.command("set_forward") & filters.user(ADMIN_ID))
async def set_fwd_admin(client, message):
    status = message.command[1].lower()
    await settings_col.update_one({"id": "forward_setting"}, {"$set": {"protect": (status == "on")}}, upsert=True)
    await message.reply(f"✅ অ্যান্টি-ফরোয়ার্ড {status} হয়েছে।")

@app.on_message(filters.command("set_shortener") & filters.user(ADMIN_ID))
async def set_short_admin(client, message):
    try:
        url, key = message.command[1], message.command[2]
        await settings_col.update_one({"id": "shortener"}, {"$set": {"base_url": url, "api_key": key}}, upsert=True)
        await message.reply(f"✅ সর্টেনার সেট হয়েছে: {url}")
    except: await message.reply("সঠিক নিয়ম: `/set_shortener Domain API`")

@app.on_message(filters.chat(FILE_CHANNEL) & (filters.video | filters.document | filters.audio))
async def auto_save_handler(client, message):
    await files_col.insert_one({"msg_id": message.id, "added_at": datetime.now()})
    log_text = f"✅ **নতুন ফাইল ডাটাবেসে সেভ হয়েছে!** ID: `{message.id}`"
    await client.send_message(LOG_CHANNEL, log_text)

# ==================== ৮. রান কমান্ডস ====================
async def web_server():
    server = web.Application()
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(web_server()) 
    print("বটটি সফলভাবে চালু হয়েছে! 🚀")
    app.run()
