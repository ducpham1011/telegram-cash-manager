import os
import json
import logging
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Import các thành phần nội bộ từ thư mục gốc
# Vì Vercel sẽ chạy trong thư mục gốc của dự án, import bình thường
from db_manager import DBManager
from sheet_manager import SheetManager
from qr_generator import QRGenerator
from qr_parser import QRParser

# Import trực tiếp các hàm handler từ bot.py để tái sử dụng tối đa logic
# Ta import các hàm cần thiết từ bot
import bot as bot_module

# Cấu hình múi giờ Việt Nam
TZ_VN = timezone(timedelta(hours=7))

# Tải cấu hình từ config.env (nạp bởi python-dotenv đã gọi ở bot_module)
config = bot_module.config
db = bot_module.db
sheet = bot_module.sheet
qr_gen = bot_module.qr_gen
qr_parse = bot_module.qr_parse

# Khởi tạo FastAPI
app = FastAPI(title="Cash Manager Serverless API")

# Biến global lưu trữ ứng dụng Telegram đã được khởi tạo
telegram_app = None
init_lock = asyncio_lock = None

async def get_telegram_app():
    """Khởi tạo ứng dụng Telegram Bot ở chế độ serverless (không chạy polling loop)"""
    global telegram_app
    if telegram_app is None:
        token = config.get("telegram_token")
        if not token:
            raise ValueError("Không tìm thấy TELEGRAM_TOKEN trong cấu hình.")
            
        app = Application.builder().token(token).build()
        
        # Đăng ký các Handler giống hệt bot.py
        app.add_handler(CommandHandler("start", bot_module.start_command))
        app.add_handler(CommandHandler("setup_sheet", bot_module.setup_sheet_command))
        app.add_handler(CommandHandler("set_limit", bot_module.set_limit_command))
        app.add_handler(CommandHandler("stats", bot_module.stats_command))
        app.add_handler(CommandHandler("close_day", bot_module.close_day_command))
        
        app.add_handler(MessageHandler(filters.PHOTO, bot_module.handle_photo))
        app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, bot_module.handle_webapp_data))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_module.handle_message))
        app.add_handler(CallbackQueryHandler(bot_module.callback_handler))
        
        # Khởi tạo ứng dụng bất đồng bộ
        await app.initialize()
        telegram_app = app
        
    return telegram_app

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Cash Manager Bot Serverless",
        "time_vn": datetime.now(TZ_VN).strftime("%Y-%m-%d %H:%M:%S")
    }

@app.get("/webapp", response_class=HTMLResponse)
async def webapp_page():
    """Serve trang quét QR trực tiếp cho Telegram WebApp"""
    webapp_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "webapp", "index.html")
    if not os.path.exists(webapp_path):
        return HTMLResponse("❌ Không tìm thấy file webapp/index.html", status_code=404)
        
    with open(webapp_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    """Cổng đón sự kiện Webhook từ Telegram"""
    try:
        data = await request.json()
        app = await get_telegram_app()
        
        # Chuyển đổi JSON nhận được thành đối tượng Update của Telegram
        update = Update.de_json(data, app.bot)
        
        # Xử lý update bất đồng bộ bằng router của Application
        await app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Lỗi xử lý webhook: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/api/setup_webhook")
async def setup_webhook(request: Request):
    """Endpoint tiện ích để đăng ký Webhook URL với Telegram"""
    host = request.headers.get("host")
    if not host:
        return {"status": "error", "message": "Host header is missing"}
        
    # Phát hiện giao thức (luôn sử dụng https khi chạy trên Vercel)
    scheme = "https" if "vercel" in host or request.headers.get("x-forwarded-proto") == "https" else "http"
    webhook_url = f"{scheme}://{host}/api/webhook"
    
    try:
        app = await get_telegram_app()
        success = await app.bot.set_webhook(webhook_url)
        return {
            "status": "success" if success else "failed",
            "webhook_url": webhook_url,
            "message": "Webhook has been set successfully!" if success else "Failed to set webhook."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- LOGIC CRON JOBS CỦA VERCEL (THAY THẾ SCHEDULER.PY) ---

def verify_cron_request(request: Request):
    """Xác thực xem yêu cầu gọi API Cron có đến từ hệ thống Vercel đáng tin cậy không"""
    # Vercel tự động gửi CRON_SECRET trong Header Authorization: Bearer <CRON_SECRET>
    cron_secret = os.environ.get("CRON_SECRET")
    if not cron_secret:
        # Nếu chưa cấu hình bảo mật CRON_SECRET, cho phép gọi (để test)
        return
        
    auth_header = request.headers.get("Authorization")
    if not auth_header or auth_header != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="Unauthorized Cron request")

@app.get("/api/cron/reminder")
async def cron_daily_reminder(request: Request):
    """Cron Job chạy lúc 21h hàng ngày (14:00 UTC)"""
    verify_cron_request(request)
    
    app = await get_telegram_app()
    now = datetime.now(TZ_VN)
    date_str = now.strftime("%d/%m/%Y")
    
    users = db.get_all_users()
    count = 0
    for user in users:
        chat_id = user["chat_id"]
        if not db.is_day_closed(chat_id, date_str):
            msg = f"🔔 **[Nhắc nhở 21h]**\nĐến giờ chốt sổ rồi! Bạn chưa chốt các khoản chi tiêu cho ngày hôm nay ({date_str}).\nVui lòng cập nhật các khoản chi và bấm chốt nhé!"
            await send_cron_reminder(app.bot, chat_id, msg, date_str)
            count += 1
            
    return {"status": "success", "reminded_users": count}

@app.get("/api/cron/hourly_check")
async def cron_hourly_check(request: Request):
    """Cron Job chạy mỗi giờ (vào phút 0)"""
    verify_cron_request(request)
    
    app = await get_telegram_app()
    now = datetime.now(TZ_VN)
    hour = now.hour
    
    # Tránh nhắc nhở lúc nửa đêm (24h - 7h sáng)
    if hour < 8 or hour > 23:
        return {"status": "ignored", "reason": "silent hours"}

    users = db.get_all_users()
    date_today = now.strftime("%d/%m/%Y")
    date_yesterday = (now - timedelta(days=1)).strftime("%d/%m/%Y")
    count = 0

    for user in users:
        chat_id = user["chat_id"]
        
        # 1. Kiểm tra ngày hôm qua (chỉ nhắc nếu bây giờ là ban ngày và ngày hôm qua chưa chốt)
        if 8 <= hour <= 20:
            if not db.is_day_closed(chat_id, date_yesterday):
                msg = f"⚠️ **[Nhắc nhở chưa chốt]**\nBạn vẫn chưa chốt chi tiêu cho **ngày hôm qua ({date_yesterday})**.\nHãy dành chút thời gian chốt ngày nhé!"
                await send_cron_reminder(app.bot, chat_id, msg, date_yesterday)
                count += 1
                continue

        # 2. Kiểm tra ngày hôm nay (nhắc nhở định kỳ mỗi giờ sau 21h nếu chưa chốt)
        if hour >= 22:
            if not db.is_day_closed(chat_id, date_today):
                msg = f"⏰ **[Nhắc nhở định kỳ]**\nĐã {hour}h00 nhưng bạn chưa chốt chi tiêu cho ngày hôm nay ({date_today}).\nVui lòng cập nhật và chốt ngày nhé!"
                await send_cron_reminder(app.bot, chat_id, msg, date_today)
                count += 1
                
    return {"status": "success", "reminded_users": count}

async def send_cron_reminder(bot, chat_id, message, date_str):
    """Hàm phụ trợ gửi nhắc nhở từ Cron Job"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = [
        [
            InlineKeyboardButton("✅ Chốt ngày ngay", callback_data=f"close_day:{date_str}"),
            InlineKeyboardButton("📊 Xem chi tiêu hôm nay", callback_data="stats_day")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Lỗi gửi tin nhắn nhắc nhở từ Cron: {e}")
