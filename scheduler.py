from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

TZ_VN = timezone(timedelta(hours=7))

class CashScheduler:
    def __init__(self, bot, db_manager):
        self.bot = bot
        self.db = db_manager
        self.scheduler = AsyncIOScheduler(timezone=TZ_VN)

    def start(self):
        """Khởi động scheduler"""
        if not self.scheduler.running:
            # Chạy nhắc nhở lúc 21:00 hàng ngày
            self.scheduler.add_job(
                self.daily_reminder,
                'cron',
                hour=21,
                minute=0,
                id='daily_reminder',
                replace_existing=True
            )
            # Kiểm tra định kỳ mỗi giờ một lần (vào phút 0) để nhắc nhở nếu chưa chốt
            self.scheduler.add_job(
                self.hourly_unclosed_check,
                'cron',
                minute=0,
                id='hourly_check',
                replace_existing=True
            )
            self.scheduler.start()
            print("Scheduler đã được khởi động.")

    def stop(self):
        """Dừng scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            print("Scheduler đã dừng.")

    async def send_reminder(self, chat_id, message, date_str):
        """Gửi tin nhắn nhắc nhở kèm nút bấm Chốt nhanh"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Chốt ngày ngay", callback_data=f"close_day:{date_str}"),
                InlineKeyboardButton("📊 Xem chi tiêu hôm nay", callback_data="stats_day")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        except TelegramError as e:
            print(f"Không thể gửi tin nhắn nhắc nhở tới {chat_id}: {str(e)}")

    async def daily_reminder(self):
        """Job nhắc nhở 21h hàng ngày"""
        now = datetime.now(TZ_VN)
        date_str = now.strftime("%d/%m/%Y")
        users = self.db.get_all_users()
        
        for user in users:
            chat_id = user["chat_id"]
            if not self.db.is_day_closed(chat_id, date_str):
                msg = f"🔔 **[Nhắc nhở 21h]**\nĐến giờ chốt sổ rồi! Bạn chưa chốt các khoản chi tiêu cho ngày hôm nay ({date_str}).\nVui lòng cập nhật các khoản chi và bấm chốt nhé!"
                await self.send_reminder(chat_id, msg, date_str)

    async def hourly_unclosed_check(self):
        """Job kiểm tra mỗi giờ, nhắc nhở nếu chưa chốt (từ 22h tối đến 23h tối, và 8h sáng đến 20h tối)"""
        now = datetime.now(TZ_VN)
        hour = now.hour
        
        # Tránh nhắc nhở lúc nửa đêm (24h - 7h sáng)
        if hour < 8 or hour > 23:
            return

        users = self.db.get_all_users()
        date_today = now.strftime("%d/%m/%Y")
        date_yesterday = (now - timedelta(days=1)).strftime("%d/%m/%Y")

        for user in users:
            chat_id = user["chat_id"]
            
            # 1. Kiểm tra ngày hôm qua (chỉ nhắc nếu bây giờ là ban ngày và ngày hôm qua vẫn chưa chốt)
            if 8 <= hour <= 20:
                if not self.db.is_day_closed(chat_id, date_yesterday):
                    msg = f"⚠️ **[Nhắc nhở chưa chốt]**\nBạn vẫn chưa chốt chi tiêu cho **ngày hôm qua ({date_yesterday})**.\nHãy dành chút thời gian chốt ngày nhé!"
                    await self.send_reminder(chat_id, msg, date_yesterday)
                    continue  # Ưu tiên nhắc ngày cũ trước

            # 2. Kiểm tra ngày hôm nay (nhắc nhở định kỳ mỗi giờ sau 21h nếu chưa chốt)
            if hour >= 22:
                if not self.db.is_day_closed(chat_id, date_today):
                    msg = f"⏰ **[Nhắc nhở định kỳ]**\nĐã {hour}h00 nhưng bạn chưa chốt chi tiêu cho ngày hôm nay ({date_today}).\nVui lòng cập nhật và chốt ngày nhé!"
                    await self.send_reminder(chat_id, msg, date_today)
