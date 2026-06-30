import os
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# Import các module tự tạo
from db_manager import DBManager
from sheet_manager import SheetManager
from qr_generator import QRGenerator
from qr_parser import QRParser
from scheduler import CashScheduler

# Cấu hình logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Cấu hình múi giờ Việt Nam (UTC+7)
TZ_VN = timezone(timedelta(hours=7))

# Danh mục chi tiêu mặc định
CATEGORIES = {
    "cat_anuong": "🍔 Ăn uống",
    "cat_dichuyen": "🚗 Di chuyển",
    "cat_muasam": "🛍️ Mua sắm",
    "cat_hoadon": "⚡ Hóa đơn",
    "cat_suckhoe": "💊 Sức khỏe",
    "cat_giaitri": "☕ Giải trí",
    "cat_khac": "📝 Khác"
}

# Tải cấu hình
from dotenv import load_dotenv
config_env_path = os.path.join(os.path.dirname(__file__), "config.env")
if os.path.exists(config_env_path):
    load_dotenv(config_env_path)
else:
    load_dotenv()

config = {
    "telegram_token": os.getenv("TELEGRAM_TOKEN", ""),
    "google_credentials_file": os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"),
    "webapp_url": os.getenv("WEBAPP_URL", ""),
    "mongodb_uri": os.getenv("MONGODB_URI", "mongodb://localhost:27017/"),
    "mongodb_db_name": os.getenv("MONGODB_DB_NAME", "cash_manager")
}

# Khởi tạo các thành phần
db = DBManager(config["mongodb_uri"], config["mongodb_db_name"])

# Đảm bảo đường dẫn tệp credentials.json là tuyệt đối
creds_path = config["google_credentials_file"]
if not os.path.isabs(creds_path):
    creds_path = os.path.join(os.path.dirname(__file__), creds_path)

sheet = SheetManager(creds_path)
qr_gen = QRGenerator()
qr_parse = QRParser()

# Lưu trữ trạng thái hội thoại của người dùng (trong bộ nhớ tạm)
# Cấu trúc: { chat_id: { "state": STATE, "temp_data": {} } }
user_sessions = {}

# Các trạng thái hội thoại
STATE_NONE = 0
STATE_AWAITING_AMOUNT = 1
STATE_AWAITING_CONTENT = 2
STATE_AWAITING_LIMIT_TYPE = 3
STATE_AWAITING_LIMIT_AMOUNT = 4
STATE_AWAITING_MANUAL_BANK = 5
STATE_AWAITING_QR_AMOUNT = 6
STATE_AWAITING_QR_CONTENT = 7

def get_vietnam_now():
    return datetime.now(TZ_VN)

def format_currency(amount):
    return f"{amount:,.0f}".replace(",", ".") + "đ"

def make_progress_bar(percentage):
    filled_length = int(round(10 * percentage / 100))
    filled_length = max(0, min(10, filled_length))
    bar = "█" * filled_length + "░" * (10 - filled_length)
    return bar

def get_main_menu_keyboard(chat_id):
    """Tạo bàn phím menu chính dưới chân khung chat"""
    # Nút quét QR liên kết với WebApp
    scan_url = config.get("webapp_url", "")
    scan_button = KeyboardButton("📷 Quét QR trực tiếp", web_app=WebAppInfo(url=scan_url)) if scan_url else KeyboardButton("📷 Quét QR trực tiếp")
    
    keyboard = [
        [KeyboardButton("✍️ Nhập thủ công"), scan_button],
        [KeyboardButton("📊 Thống kê"), KeyboardButton("⚙️ Thiết lập")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /start"""
    chat_id = update.effective_chat.id
    user_sessions[chat_id] = {"state": STATE_NONE, "temp_data": {}}
    
    # Kiểm tra xem người dùng đã cài đặt Google Sheet chưa
    user_data = db.get_user(chat_id)
    
    welcome_text = (
        "👋 **Chào mừng bạn đến với Cash Manager Bot!**\n\n"
        "Tôi sẽ giúp bạn quản lý chi tiêu hàng ngày một cách thông minh, nhanh chóng thông qua "
        "kết hợp quét QR thanh toán và tự động đồng bộ hóa với Google Sheets.\n\n"
    )
    
    if not user_data or not user_data.get("sheet_url"):
        welcome_text += (
            "⚙️ **Bước đầu tiên:** Bạn cần liên kết bot với Google Sheets của bạn.\n"
            "1. Hãy gõ lệnh `/setup_sheet <ĐƯỜNG_DẪN_GOOGLE_SHEET>`\n"
            "2. Hoặc bấm nút **⚙️ Thiết lập** dưới chân màn hình."
        )
    else:
        welcome_text += "✅ Bot đã được cấu hình và sẵn sàng hoạt động!"

    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_menu_keyboard(chat_id),
        parse_mode="Markdown"
    )

async def setup_sheet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh cài đặt Google Sheet URL"""
    chat_id = update.effective_chat.id
    
    if not context.args:
        # Lấy email của Service Account để hướng dẫn người dùng
        sa_email = sheet.get_service_account_email() or "Email của bot"
        instructions = (
            "Để cài đặt Google Sheets, vui lòng sử dụng cú pháp:\n"
            "`/setup_sheet <URL_GOOGLE_SHEET>`\n\n"
            "**LƯU Ý QUAN TRỌNG:** Bạn phải cấp quyền truy cập (Share) cho tài khoản email sau của Bot với quyền **Editor**:\n"
            f"`{sa_email}`"
        )
        await update.message.reply_text(instructions, parse_mode="Markdown")
        return

    sheet_url = context.args[0]
    await check_and_save_sheet(update, chat_id, sheet_url)

async def check_and_save_sheet(update_or_callback, chat_id, sheet_url):
    """Xác thực và lưu liên kết Google Sheet"""
    # Gửi tin nhắn chờ
    send_method = update_or_callback.message.reply_text if hasattr(update_or_callback, "message") and update_or_callback.message else update_or_callback.edit_message_text
    
    waiting_msg = await send_method("⏳ Đang kiểm tra kết nối với Google Sheet của bạn...")
    
    try:
        sheet.verify_connection(sheet_url)
        db.save_user_sheet(chat_id, sheet_url)
        success_text = (
            "🎉 **Kết nối thành công!**\n"
            "Tệp Google Sheet của bạn đã được liên kết với Bot.\n"
            "Từ bây giờ, tất cả giao dịch chi tiêu sẽ được tự động ghi lại vào đây."
        )
        await waiting_msg.edit_text(success_text, parse_mode="Markdown")
    except PermissionError:
        sa_email = sheet.get_service_account_email() or "Email của bot"
        err_text = (
            "❌ **Không có quyền truy cập!**\n\n"
            "Bot chưa có quyền truy cập vào Google Sheet của bạn. Vui lòng:\n"
            "1. Mở file Google Sheets của bạn.\n"
            f"2. Bấm nút **Chia sẻ (Share)** và thêm email sau làm **Người chỉnh sửa (Editor)**:\n"
            f"`{sa_email}`\n"
            "3. Thử cấu hình lại lệnh `/setup_sheet`."
        )
        await waiting_msg.edit_text(err_text, parse_mode="Markdown")
    except Exception as e:
        await waiting_msg.edit_text(f"❌ **Lỗi cấu hình:** Đường dẫn Google Sheet không hợp lệ hoặc đã xảy ra lỗi API: {e}", parse_mode="Markdown")

async def close_day_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh chốt ngày chi tiêu"""
    chat_id = update.effective_chat.id
    now = get_vietnam_now()
    date_str = now.strftime("%d/%m/%Y")
    
    db.close_day(chat_id, date_str)
    await update.message.reply_text(
        f"✅ Đã chốt các khoản chi tiêu của ngày hôm nay ({date_str}) thành công.\nChúc bạn có một ngày cân đối tài chính tốt!",
        parse_mode="Markdown"
    )

async def set_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh đặt hạn mức chi tiêu"""
    chat_id = update.effective_chat.id
    keyboard = [
        [
            InlineKeyboardButton("Hạn mức Ngày", callback_data="set_limit:daily"),
            InlineKeyboardButton("Hạn mức Tuần", callback_data="set_limit:weekly"),
            InlineKeyboardButton("Hạn mức Tháng", callback_data="set_limit:monthly")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Chọn loại hạn mức bạn muốn thiết lập:",
        reply_markup=reply_markup
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh xem thống kê"""
    chat_id = update.effective_chat.id
    keyboard = [
        [
            InlineKeyboardButton("Hôm nay", callback_data="stats:day"),
            InlineKeyboardButton("Tuần này", callback_data="stats:week"),
            InlineKeyboardButton("Tháng này", callback_data="stats:month")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Chọn khoảng thời gian thống kê chi tiêu:",
        reply_markup=reply_markup
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi người dùng gửi ảnh mã QR (Photo Upload)"""
    chat_id = update.effective_chat.id
    user_data = db.get_user(chat_id)
    
    if not user_data or not user_data.get("sheet_url"):
        await update.message.reply_text("⚠️ Bạn cần cài đặt Google Sheet trước khi sử dụng. Gõ lệnh `/setup_sheet` hoặc bấm **⚙️ Thiết lập**.")
        return

    # Tải hình ảnh về
    photo_file = await update.message.photo[-1].get_file()
    image_bytes = await photo_file.download_as_bytearray()
    
    waiting_msg = await update.message.reply_text("🔍 Đang giải mã hình ảnh QR...")
    
    # Giải mã hình ảnh trước
    raw_qr_string = qr_parse.decode_image(image_bytes)
    if not raw_qr_string:
        await waiting_msg.edit_text("❌ Không tìm thấy hoặc không thể quét được bất kỳ mã QR nào trong hình ảnh.")
        return
        
    # Phân tích chuỗi QR
    qr_data = qr_parse.parse_vietqr_string(raw_qr_string)
    if not qr_data:
        await waiting_msg.edit_text(
            "❌ Quét được mã QR trong ảnh nhưng không thể phân tích thông tin tài khoản ngân hàng.\n\n"
            f"📝 **Nội dung gốc quét được:**\n`{raw_qr_string}`",
            parse_mode="Markdown"
        )
        return
        
    await waiting_msg.delete()
    await process_parsed_qr(update, chat_id, qr_data)

async def handle_webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi nhận được dữ liệu từ WebApp quét QR trực tiếp"""
    chat_id = update.effective_chat.id
    logger.info(f"Nhận được web_app_data từ chat_id: {chat_id}")
    
    if not update.message or not update.message.web_app_data:
        logger.warning(f"WebApp data trống hoặc không hợp lệ từ chat_id: {chat_id}")
        await update.effective_message.reply_text("❌ Không nhận được dữ liệu từ trình quét QR.")
        return
        
    qr_string = update.message.web_app_data.data
    logger.info(f"Dữ liệu QR gốc nhận được từ WebApp: {qr_string}")
    
    user_data = db.get_user(chat_id)
    if not user_data or not user_data.get("sheet_url"):
        await update.effective_message.reply_text("⚠️ Bạn cần cấu hình Google Sheet trước. Gõ lệnh `/setup_sheet`.")
        return

    # Phân tích chuỗi QR (chuẩn VietQR hoặc URL thanh toán)
    qr_data = qr_parse.parse_vietqr_string(qr_string)
    
    if not qr_data:
        # Nếu quét trực tiếp mà không phải mã chuyển khoản hợp lệ, hiển thị thông báo chi tiết
        logger.info(f"Không thể phân tích dữ liệu QR từ WebApp. Nội dung: {qr_string}")
        await update.effective_message.reply_text(
            "❌ Quét trực tiếp thành công nhưng không phân tích được thông tin tài khoản ngân hàng.\n\n"
            f"📝 **Nội dung gốc quét được:**\n`{qr_string}`", 
            parse_mode="Markdown"
        )
        return

    logger.info(f"Phân tích dữ liệu QR thành công từ WebApp: {qr_data}")
    await process_parsed_qr(update, chat_id, qr_data)

async def show_qr_category_keyboard(update: Update, chat_id, temp_data):
    """Hiển thị bàn phím chọn danh mục cho giao dịch QR"""
    amount_str = format_currency(temp_data["amount"])
    
    # Định dạng hiển thị Tên tài khoản nhận (bỏ ngoặc đơn nếu không có tên)
    acc_name = temp_data.get("account_name")
    name_str = f" ({acc_name})" if acc_name else ""
    payment_details = f"{temp_data['bank_name']} - {temp_data['account_number']}{name_str}"
    
    text = (
        "🔍 **Xác nhận giao dịch QR:**\n\n"
        f"💰 **Số tiền:** {amount_str}\n"
        f"📝 **Nội dung:** {temp_data['content'] or 'Không có'}\n"
        f"🏦 **Người nhận:** {payment_details}\n\n"
        "Vui lòng chọn danh mục chi tiêu bên dưới để ghi nhận vào Google Sheet:"
    )
    
    keyboard = []
    current_row = []
    for cat_id, cat_name in CATEGORIES.items():
        current_row.append(InlineKeyboardButton(cat_name, callback_data=f"qr_cat:{cat_id}"))
        if len(current_row) == 2:
            keyboard.append(current_row)
            current_row = []
    if current_row:
        keyboard.append(current_row)
        
    keyboard.append([InlineKeyboardButton("❌ Hủy giao dịch", callback_data="cancel_spend")])
    
    if temp_data["amount"]:
        pay_url = qr_gen.generate_pay_link(temp_data["bank_bin"], temp_data["account_number"], temp_data["amount"], temp_data["content"])
        keyboard.insert(0, [InlineKeyboardButton("🔗 Mở App ngân hàng thanh toán", url=pay_url)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def process_parsed_qr(update: Update, chat_id, qr_data):
    """Hiển thị thông tin QR đã quét và các tùy chọn xử lý"""
    amount = qr_data.get("amount")
    
    # Coi "Chuyen khoan QR" là nội dung trống cần hỏi lại để quản lý chi tiêu tốt hơn
    description = qr_data.get("description")
    if description == "Chuyen khoan QR" or not description:
        description = None
        
    # Lưu thông tin giao dịch vào phiên làm việc
    temp_data = {
        "amount": amount,
        "content": description,
        "bank_bin": qr_data.get("bank_bin"),
        "bank_name": qr_data.get("bank_name"),
        "account_number": qr_data.get("account_number"),
        "account_name": qr_data.get("account_name"),
        "qr_string": qr_data.get("qr_string")
    }
    
    user_sessions[chat_id] = {
        "state": STATE_NONE,
        "temp_data": temp_data
    }
    
    acc_name = temp_data.get("account_name")
    name_str = f" ({acc_name})" if acc_name else ""
    payment_details = f"{temp_data['bank_name']} - {temp_data['account_number']}{name_str}"

    # 1. Kiểm tra nếu chưa có số tiền (mã QR tĩnh)
    if not amount or amount <= 0:
        user_sessions[chat_id]["state"] = STATE_AWAITING_QR_AMOUNT
        await update.message.reply_text(
            f"🏦 **Tài khoản nhận:** {payment_details}\n\n"
            "💰 Mã QR này không chứa thông tin số tiền.\n"
            "Vui lòng nhập **số tiền** cần chi tiêu (ví dụ: `50k` hoặc `50000`):"
        )
        return
        
    # 2. Kiểm tra nếu chưa có nội dung chuyển khoản
    if not description:
        user_sessions[chat_id]["state"] = STATE_AWAITING_QR_CONTENT
        amount_str = format_currency(amount)
        await update.message.reply_text(
            f"🏦 **Tài khoản nhận:** {payment_details}\n"
            f"💰 **Số tiền:** {amount_str}\n\n"
            "📝 Vui lòng nhập **nội dung chi tiêu** (ví dụ: `Ăn trưa`, `Mua sắm`):"
        )
        return

    # 3. Nếu có đầy đủ, hiện luôn bàn phím chọn danh mục
    await show_qr_category_keyboard(update, chat_id, temp_data)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý tin nhắn văn bản thông thường và luồng nhập thủ công"""
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    
    # 1. Xử lý menu chính bằng bàn phím
    if text == "✍️ Nhập thủ công":
        user_sessions[chat_id] = {"state": STATE_AWAITING_AMOUNT, "temp_data": {}}
        await update.message.reply_text("💰 Vui lòng nhập số tiền chi tiêu (đơn vị: VNĐ, ví dụ: 50000 hoặc 50k):")
        return
        
    elif text == "📊 Thống kê":
        await stats_command(update, context)
        return
        
    elif text == "⚙️ Thiết lập":
        sa_email = sheet.get_service_account_email() or "Email của bot"
        user_data = db.get_user(chat_id)
        
        status_sheet = f"`{user_data['sheet_url']}`" if user_data and user_data.get("sheet_url") else "❌ Chưa liên kết"
        
        settings_text = (
            "⚙️ **Thiết lập hệ thống:**\n\n"
            f"📊 **Google Sheet:** {status_sheet}\n\n"
            "**Để liên kết file Google Sheet mới:**\n"
            "Hãy gõ lệnh `/setup_sheet <URL_CỦA_SHEET>`\n\n"
            "**Email của Bot cần được chia sẻ quyền Editor:**\n"
            f"`{sa_email}`\n\n"
            "**Để cấu hình hạn mức chi tiêu:**\n"
            "Hãy gõ lệnh `/set_limit`"
        )
        await update.message.reply_text(settings_text, parse_mode="Markdown")
        return

    # 2. Xử lý theo trạng thái hội thoại (State Machine)
    session = user_sessions.get(chat_id, {"state": STATE_NONE, "temp_data": {}})
    state = session["state"]
    
    if state == STATE_AWAITING_AMOUNT:
        # Xử lý số tiền nhập vào (cho phép định dạng như 50k, 100k, 1.5tr...)
        amount_raw = text.lower().replace(".", "").replace(",", "").replace("đ", "").replace("vnd", "").strip()
        
        amount = 0
        try:
            if amount_raw.endswith("k"):
                amount = float(amount_raw[:-1]) * 1000
            elif amount_raw.endswith("tr") or amount_raw.endswith("m"):
                amount = float(amount_raw[:-2]) * 1000000
            else:
                amount = float(amount_raw)
        except ValueError:
            await update.message.reply_text("❌ Định dạng số tiền không hợp lệ. Vui lòng nhập lại (Ví dụ: 50000 hoặc 50k):")
            return

        session["temp_data"]["amount"] = amount
        session["state"] = STATE_AWAITING_CONTENT
        await update.message.reply_text("📝 Vui lòng nhập nội dung chi tiêu (Ví dụ: Ăn sáng, Mua bột giặt...):")
        
    elif state == STATE_AWAITING_CONTENT:
        session["temp_data"]["content"] = text
        session["state"] = STATE_NONE
        
        # Chuyển qua bước chọn danh mục
        keyboard = []
        current_row = []
        for cat_id, cat_name in CATEGORIES.items():
            current_row.append(InlineKeyboardButton(cat_name, callback_data=f"manual_cat:{cat_id}"))
            if len(current_row) == 2:
                keyboard.append(current_row)
                current_row = []
        if current_row:
            keyboard.append(current_row)
            
        keyboard.append([InlineKeyboardButton("❌ Hủy", callback_data="cancel_spend")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        amount_str = format_currency(session["temp_data"]["amount"])
        await update.message.reply_text(
            f"ℹ️ **Thông tin đã nhập:**\n- **Số tiền:** {amount_str}\n- **Nội dung:** {text}\n\nChọn danh mục tương ứng:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
    elif state == STATE_AWAITING_LIMIT_AMOUNT:
        try:
            limit_amount = float(text.replace(".", "").replace(",", "").replace("k", "000").strip())
        except ValueError:
            await update.message.reply_text("❌ Số tiền không hợp lệ. Vui lòng nhập lại số tiền hạn mức:")
            return
            
        limit_type = session["temp_data"]["limit_type"]
        db.save_user_limits(chat_id, **{limit_type: limit_amount})
        
        session["state"] = STATE_NONE
        type_str = {"daily": "Ngày", "weekly": "Tuần", "monthly": "Tháng"}[limit_type]
        await update.message.reply_text(f"✅ Đã thiết lập hạn mức **{type_str}** là **{format_currency(limit_amount)}** thành công.")
        
    elif state == STATE_AWAITING_QR_AMOUNT:
        amount_raw = text.lower().replace(".", "").replace(",", "").replace("đ", "").replace("vnd", "").strip()
        amount = 0
        try:
            if amount_raw.endswith("k"):
                amount = float(amount_raw[:-1]) * 1000
            elif amount_raw.endswith("tr") or amount_raw.endswith("m"):
                amount = float(amount_raw[:-2]) * 1000000
            else:
                amount = float(amount_raw)
        except ValueError:
            await update.message.reply_text("❌ Định dạng số tiền không hợp lệ. Vui lòng nhập lại số tiền chi tiêu (Ví dụ: 50000 hoặc 50k):")
            return

        session["temp_data"]["amount"] = amount
        
        # Sau khi nhập số tiền, kiểm tra xem nội dung đã có chưa
        if not session["temp_data"].get("content"):
            session["state"] = STATE_AWAITING_QR_CONTENT
            await update.message.reply_text("📝 Vui lòng nhập nội dung chi tiêu (Ví dụ: Ăn trưa, Đổ xăng...):")
        else:
            session["state"] = STATE_NONE
            await show_qr_category_keyboard(update, chat_id, session["temp_data"])

    elif state == STATE_AWAITING_QR_CONTENT:
        session["temp_data"]["content"] = text
        session["state"] = STATE_NONE
        await show_qr_category_keyboard(update, chat_id, session["temp_data"])

    elif state == STATE_AWAITING_MANUAL_BANK:
        # Xử lý khi nhập ngân hàng người nhận: <mã ngân hàng> <số tài khoản>
        match = re.match(r"^([a-zA-Z0-9]+)\s+([0-9]+)$", text)
        if not match:
            await update.message.reply_text("❌ Định dạng không hợp lệ. Vui lòng nhập lại theo mẫu: `vcb 1234567890` hoặc gửi ảnh QR người nhận:")
            return
            
        bank_id = match.group(1).lower()
        account_no = match.group(2)
        
        temp_data = session["temp_data"]
        temp_data["bank_bin"] = bank_id
        temp_data["account_number"] = account_no
        temp_data["bank_name"] = bank_id.upper()
        temp_data["account_name"] = "Nguoi nhan"
        
        # Sinh VietQR URL
        qr_url = qr_gen.generate_vietqr_url(bank_id, account_no, temp_data["amount"], temp_data["content"])
        pay_url = qr_gen.generate_pay_link(bank_id, account_no, temp_data["amount"], temp_data["content"])
        
        keyboard = [
            [InlineKeyboardButton("🔗 Mở App ngân hàng thanh toán", url=pay_url)],
            [InlineKeyboardButton("✅ Đã chuyển, ghi vào Sheet", callback_data="manual_confirm_pay")],
            [InlineKeyboardButton("❌ Hủy", callback_data="cancel_spend")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_photo(
            photo=qr_url,
            caption=(
                "🏦 **Mã chuyển khoản VietQR được tạo:**\n\n"
                f"💰 **Số tiền:** {format_currency(temp_data['amount'])}\n"
                f"📝 **Nội dung:** {temp_data['content']}\n"
                f"🏛️ **Ngân hàng:** {bank_id.upper()} - **TK:** {account_no}\n\n"
                "Sau khi thực hiện chuyển khoản trên ứng dụng ngân hàng của bạn, hãy quay lại đây bấm **Đã chuyển** để ghi chép."
            ),
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        session["state"] = STATE_NONE

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý các sự kiện click nút bấm Inline Keyboard"""
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    data = query.data
    
    user_data = db.get_user(chat_id)
    session = user_sessions.setdefault(chat_id, {"state": STATE_NONE, "temp_data": {}})
    
    # 1. Hủy bỏ giao dịch
    if data == "cancel_spend":
        user_sessions[chat_id] = {"state": STATE_NONE, "temp_data": {}}
        await query.edit_message_text("❌ Giao dịch đã bị hủy bỏ.")
        return
        
    # 2. Xử lý gán danh mục cho giao dịch quét QR
    elif data.startswith("qr_cat:"):
        cat_id = data.split(":")[1]
        category = CATEGORIES.get(cat_id, "Khác")
        temp_data = session["temp_data"]
        
        # Ghi nhận vào Google Sheets
        try:
            # Gửi tin nhắn chờ ghi
            await query.edit_message_text("⏳ Đang ghi dữ liệu vào Google Sheet...")
            
            payment_info = f"{temp_data['bank_name']} - {temp_data['account_number']} ({temp_data['account_name']})"
            date_str, time_str = sheet.log_spending(
                user_data["sheet_url"],
                temp_data["amount"],
                temp_data["content"],
                category,
                status="Đã chuyển",
                payment_details=payment_info
            )
            
            # Kiểm tra hạn mức chi tiêu
            warning_msg = check_limits_and_warn(chat_id, temp_data["amount"])
            
            success_text = (
                "✅ **Đã ghi nhận chi tiêu thành công!**\n\n"
                f"📅 **Thời gian:** {date_str} lúc {time_str}\n"
                f"💰 **Số tiền:** {format_currency(temp_data['amount'])}\n"
                f"📝 **Nội dung:** {temp_data['content']}\n"
                f"🏷️ **Danh mục:** {category}\n"
                f"🏦 **Giao dịch:** {payment_info}\n"
            )
            if warning_msg:
                success_text += f"\n⚠️ **CẢNH BÁO HẠN MỨC:**\n{warning_msg}"
                
            await query.edit_message_text(success_text, parse_mode="Markdown")
            # Xóa session giao dịch
            user_sessions[chat_id] = {"state": STATE_NONE, "temp_data": {}}
        except Exception as e:
            await query.edit_message_text(f"❌ Lỗi khi ghi nhận giao dịch: {str(e)}")
            
    # 3. Xử lý gán danh mục cho giao dịch nhập thủ công
    elif data.startswith("manual_cat:"):
        cat_id = data.split(":")[1]
        category = CATEGORIES.get(cat_id, "Khác")
        session["temp_data"]["category"] = category
        
        # Hỏi xem có muốn chuyển khoản thanh toán không
        keyboard = [
            [
                InlineKeyboardButton("💵 Tiền mặt (Ghi ngay)", callback_data="pay_cash"),
                InlineKeyboardButton("💳 Chuyển khoản (Tạo VietQR)", callback_data="pay_transfer")
            ],
            [InlineKeyboardButton("❌ Hủy", callback_data="cancel_spend")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Hệ thống sẽ ghi nhận danh mục **{category}**.\nBạn muốn thanh toán khoản chi này thế nào?",
            reply_markup=reply_markup
        )

    # 4. Thanh toán tiền mặt
    elif data == "pay_cash":
        temp_data = session["temp_data"]
        try:
            await query.edit_message_text("⏳ Đang ghi nhận chi tiêu tiền mặt...")
            date_str, time_str = sheet.log_spending(
                user_data["sheet_url"],
                temp_data["amount"],
                temp_data["content"],
                temp_data["category"],
                status="Đã chuyển",
                payment_details="Tiền mặt"
            )
            
            warning_msg = check_limits_and_warn(chat_id, temp_data["amount"])
            
            success_text = (
                "✅ **Đã ghi nhận chi tiêu (Tiền mặt)!**\n\n"
                f"📅 **Thời gian:** {date_str} lúc {time_str}\n"
                f"💰 **Số tiền:** {format_currency(temp_data['amount'])}\n"
                f"📝 **Nội dung:** {temp_data['content']}\n"
                f"🏷️ **Danh mục:** {temp_data['category']}\n"
            )
            if warning_msg:
                success_text += f"\n⚠️ **CẢNH BÁO HẠN MỨC:**\n{warning_msg}"
                
            await query.edit_message_text(success_text, parse_mode="Markdown")
            user_sessions[chat_id] = {"state": STATE_NONE, "temp_data": {}}
        except Exception as e:
            await query.edit_message_text(f"❌ Lỗi ghi nhận: {str(e)}")

    # 5. Thanh toán chuyển khoản (Yêu cầu nhập thông tin nhận để sinh QR)
    elif data == "pay_transfer":
        session["state"] = STATE_AWAITING_MANUAL_BANK
        await query.edit_message_text(
            "Vui lòng nhập thông tin ngân hàng nhận theo cú pháp:\n"
            "`<Mã ngân hàng viết tắt> <Số tài khoản>`\n"
            "*(Ví dụ: `vcb 0071001234567` hoặc `mbbank 123456789`)*\n\n"
            "Hoặc bạn cũng có thể gửi ảnh mã QR nhận tiền của người nhận vào chat này.",
            parse_mode="Markdown"
        )

    # 6. Xác nhận đã chuyển khoản cho giao dịch nhập tay sinh QR
    elif data == "manual_confirm_pay":
        temp_data = session["temp_data"]
        try:
            await query.edit_message_text("⏳ Đang ghi nhận giao dịch chuyển khoản vào Sheet...")
            payment_info = f"{temp_data['bank_name']} - {temp_data['account_number']}"
            date_str, time_str = sheet.log_spending(
                user_data["sheet_url"],
                temp_data["amount"],
                temp_data["content"],
                temp_data["category"],
                status="Đã chuyển",
                payment_details=payment_info
            )
            
            warning_msg = check_limits_and_warn(chat_id, temp_data["amount"])
            
            success_text = (
                "✅ **Đã ghi nhận giao dịch chuyển khoản!**\n\n"
                f"📅 **Thời gian:** {date_str} lúc {time_str}\n"
                f"💰 **Số tiền:** {format_currency(temp_data['amount'])}\n"
                f"📝 **Nội dung:** {temp_data['content']}\n"
                f"🏷️ **Danh mục:** {temp_data['category']}\n"
                f"🏦 **Người nhận:** {payment_info}\n"
            )
            if warning_msg:
                success_text += f"\n⚠️ **CẢNH BÁO HẠN MỨC:**\n{warning_msg}"
                
            await query.edit_message_text(success_text, parse_mode="Markdown")
            user_sessions[chat_id] = {"state": STATE_NONE, "temp_data": {}}
        except Exception as e:
            await query.edit_message_text(f"❌ Lỗi ghi nhận: {str(e)}")

    # 7. Xử lý thiết lập hạn mức
    elif data.startswith("set_limit:"):
        limit_type = data.split(":")[1]
        session["state"] = STATE_AWAITING_LIMIT_AMOUNT
        session["temp_data"]["limit_type"] = limit_type
        
        type_str = {"daily": "Hàng ngày", "weekly": "Hàng tuần", "monthly": "Hàng tháng"}[limit_type]
        await query.edit_message_text(f"💰 Vui lòng nhập số tiền hạn mức {type_str} bạn muốn đặt (đơn vị: VNĐ):")

    # 8. Xem thống kê
    elif data.startswith("stats:"):
        period = data.split(":")[1]
        await show_stats_details(query, chat_id, user_data["sheet_url"], period)

    # 9. Chốt ngày nhanh từ tin nhắn nhắc nhở
    elif data.startswith("close_day:"):
        date_str = data.split(":")[1]
        db.close_day(chat_id, date_str)
        await query.edit_message_text(f"✅ Đã chốt chi tiêu cho ngày **{date_str}** thành công. Cảm ơn bạn!", parse_mode="Markdown")

    elif data == "stats_day":
        await show_stats_details(query, chat_id, user_data["sheet_url"], "day")

def check_limits_and_warn(chat_id, new_amount):
    """Kiểm tra hạn mức xem giao dịch mới có làm vượt hạn mức không"""
    user_data = db.get_user(chat_id)
    if not user_data:
        return None
        
    sheet_url = user_data["sheet_url"]
    warnings = []
    
    try:
        # Kiểm tra hạn mức Ngày
        if user_data["daily_limit"] > 0:
            spent, _ = sheet.get_statistics(sheet_url, "day")
            if spent > user_data["daily_limit"]:
                warnings.append(f"🔴 Vượt hạn mức NGÀY: Đã tiêu {format_currency(spent)} / Hạn mức {format_currency(user_data['daily_limit'])}")
                
        # Kiểm tra hạn mức Tuần
        if user_data["weekly_limit"] > 0:
            spent, _ = sheet.get_statistics(sheet_url, "week")
            if spent > user_data["weekly_limit"]:
                warnings.append(f"🔴 Vượt hạn mức TUẦN: Đã tiêu {format_currency(spent)} / Hạn mức {format_currency(user_data['weekly_limit'])}")
                
        # Kiểm tra hạn mức Tháng
        if user_data["monthly_limit"] > 0:
            spent, _ = sheet.get_statistics(sheet_url, "month")
            if spent > user_data["monthly_limit"]:
                warnings.append(f"🔴 Vượt hạn mức THÁNG: Đã tiêu {format_currency(spent)} / Hạn mức {format_currency(user_data['monthly_limit'])}")
    except Exception as e:
        logger.error(f"Lỗi kiểm tra hạn mức: {e}")
        
    return "\n".join(warnings) if warnings else None

async def show_stats_details(query, chat_id, sheet_url, period):
    """Tính toán và hiển thị báo cáo thống kê trực quan"""
    period_title = {"day": "Hôm nay", "week": "Tuần này", "month": "Tháng này"}[period]
    
    await query.edit_message_text(f"⏳ Đang thu thập số liệu chi tiêu của {period_title} từ Google Sheet...")
    
    try:
        total_spent, txs = sheet.get_statistics(sheet_url, period)
        user_data = db.get_user(chat_id)
        
        limit_val = 0
        if period == "day":
            limit_val = user_data["daily_limit"]
        elif period == "week":
            limit_val = user_data["weekly_limit"]
        elif period == "month":
            limit_val = user_data["monthly_limit"]
            
        limit_text = ""
        progress_bar_text = ""
        if limit_val > 0:
            pct = (total_spent / limit_val) * 100
            bar = make_progress_bar(pct)
            limit_text = f"\n🎯 **Hạn mức:** {format_currency(limit_val)} | Đã dùng: {pct:.1f}%"
            progress_bar_text = f"\n`[{bar}]`\n"
            if total_spent > limit_val:
                limit_text += " ⚠️ **(VƯỢT HẠN MỨC)**"
                
        # Phân tích theo nhóm danh mục
        cat_analysis = {}
        for tx in txs:
            cat = tx["category"] or "Chưa phân loại"
            cat_analysis[cat] = cat_analysis.get(cat, 0) + tx["amount"]
            
        cat_text = ""
        if cat_analysis:
            cat_text = "\n📊 **Phân tích theo nhóm:**\n"
            # Sắp xếp danh mục chi tiêu giảm dần
            sorted_cats = sorted(cat_analysis.items(), key=lambda x: x[1], reverse=True)
            for cat, amount in sorted_cats:
                pct_cat = (amount / total_spent) * 100 if total_spent > 0 else 0
                cat_text += f"- {cat}: **{format_currency(amount)}** ({pct_cat:.1f}%)\n"
                
        # Liệt kê 5 giao dịch gần nhất
        recent_txs = ""
        if txs:
            recent_txs = "\n📝 **Các khoản chi gần nhất:**\n"
            for tx in txs[-5:]:
                recent_txs += f"- [{tx['date']} {tx['time'][:5]}] {tx['content']}: **{format_currency(tx['amount'])}** ({tx['category']})\n"

        stats_message = (
            f"📊 **BÁO CÁO CHI TIÊU - {period_title.upper()}**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 **Tổng chi tiêu:** `{format_currency(total_spent)}`"
            f"{limit_text}"
            f"{progress_bar_text}"
            f"{cat_text}"
            f"{recent_txs}"
        )
        
        # Quay lại menu chọn
        keyboard = [
            [
                InlineKeyboardButton("Hôm nay", callback_data="stats:day"),
                InlineKeyboardButton("Tuần này", callback_data="stats:week"),
                InlineKeyboardButton("Tháng này", callback_data="stats:month")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(stats_message, reply_markup=reply_markup, parse_mode="Markdown")
        
    except Exception as e:
        await query.edit_message_text(f"❌ Lỗi tải thống kê: {str(e)}")

def main():
    token = config.get("telegram_token")
    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN":
        logger.error("Vui lòng cấu hình token Telegram Bot hợp lệ trong config.json.")
        return

    # Khởi tạo Application
    app = Application.builder().token(token).build()

    # Đăng ký các handler lệnh
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("setup_sheet", setup_sheet_command))
    app.add_handler(CommandHandler("set_limit", set_limit_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("close_day", close_day_command))

    # Xử lý tin nhắn ảnh (Photo)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Xử lý WebApp data (Quét QR trực tiếp)
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))

    # Xử lý tin nhắn văn bản thông thường (Menu chính + Trạng thái nhập thủ công)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Xử lý nút bấm callback inline
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Khởi động Scheduler nhắc nhở
    # Chúng ta sử dụng context.application.bot để lấy đối tượng bot chạy async
    scheduler = CashScheduler(app.bot, db)
    scheduler.start()

    logger.info("Bot đang chạy...")
    app.run_polling()

    # Dừng scheduler khi ứng dụng tắt
    scheduler.stop()

if __name__ == "__main__":
    main()
