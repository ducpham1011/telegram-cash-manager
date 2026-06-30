from pymongo import MongoClient

class DBManager:
    def __init__(self, mongodb_uri, db_name="cash_manager"):
        """
        Khởi tạo kết nối tới MongoDB
        - mongodb_uri: Chuỗi kết nối MongoDB (ví dụ: mongodb+srv://...)
        - db_name: Tên cơ sở dữ liệu (mặc định: cash_manager)
        """
        self.client = MongoClient(mongodb_uri)
        self.db = self.client[db_name]

    def get_user(self, chat_id):
        """Lấy thông tin cấu hình của người dùng"""
        user = self.db.users.find_one({"_id": chat_id})
        if user:
            return {
                "sheet_url": user.get("sheet_url"),
                "daily_limit": user.get("daily_limit", 0.0),
                "weekly_limit": user.get("weekly_limit", 0.0),
                "monthly_limit": user.get("monthly_limit", 0.0)
            }
        return None

    def save_user_sheet(self, chat_id, sheet_url):
        """Lưu hoặc cập nhật Google Sheet URL cho người dùng"""
        self.db.users.update_one(
            {"_id": chat_id},
            {"$set": {"sheet_url": sheet_url}},
            upsert=True
        )

    def save_user_limits(self, chat_id, daily=None, weekly=None, monthly=None):
        """Cập nhật hạn mức chi tiêu cho người dùng"""
        update_fields = {}
        if daily is not None:
            update_fields["daily_limit"] = daily
        if weekly is not None:
            update_fields["weekly_limit"] = weekly
        if monthly is not None:
            update_fields["monthly_limit"] = monthly

        if update_fields:
            self.db.users.update_one(
                {"_id": chat_id},
                {"$set": update_fields},
                upsert=True
            )

    def is_day_closed(self, chat_id, date_str):
        """Kiểm tra xem ngày đã chốt chưa (date_str định dạng DD/MM/YYYY)"""
        doc_id = f"{chat_id}_{date_str}"
        status = self.db.daily_status.find_one({"_id": doc_id})
        return status.get("is_closed", False) if status else False

    def close_day(self, chat_id, date_str):
        """Đánh dấu ngày đã được chốt"""
        doc_id = f"{chat_id}_{date_str}"
        self.db.daily_status.update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "chat_id": chat_id,
                    "date": date_str,
                    "is_closed": True
                }
            },
            upsert=True
        )

    def reopen_day(self, chat_id, date_str):
        """Mở lại ngày đã chốt nếu muốn sửa đổi"""
        doc_id = f"{chat_id}_{date_str}"
        self.db.daily_status.update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "chat_id": chat_id,
                    "date": date_str,
                    "is_closed": False
                }
            },
            upsert=True
        )

    def get_all_users(self):
        """Lấy danh sách tất cả người dùng có liên kết Google Sheet"""
        cursor = self.db.users.find({"sheet_url": {"$ne": None}})
        return [{"chat_id": user["_id"], "sheet_url": user["sheet_url"]} for user in cursor]
