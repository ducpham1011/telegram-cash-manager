import sqlite3
import os

class DBManager:
    def __init__(self, db_path="cash_manager.db"):
        self.db_path = db_path
        self.init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        """Khởi tạo cấu trúc các bảng dữ liệu trong SQLite"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Bảng lưu thông tin người dùng và cấu hình
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    chat_id INTEGER PRIMARY KEY,
                    sheet_url TEXT,
                    daily_limit REAL DEFAULT 0,
                    weekly_limit REAL DEFAULT 0,
                    monthly_limit REAL DEFAULT 0
                )
            """)
            # Bảng lưu trạng thái chốt ngày của từng người dùng
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_status (
                    chat_id INTEGER,
                    date TEXT,
                    is_closed INTEGER DEFAULT 0,
                    PRIMARY KEY (chat_id, date)
                )
            """)
            conn.commit()

    def get_user(self, chat_id):
        """Lấy thông tin cấu hình của người dùng"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT sheet_url, daily_limit, weekly_limit, monthly_limit FROM users WHERE chat_id = ?", (chat_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "sheet_url": row[0],
                    "daily_limit": row[1],
                    "weekly_limit": row[2],
                    "monthly_limit": row[3]
                }
            return None

    def save_user_sheet(self, chat_id, sheet_url):
        """Lưu hoặc cập nhật Google Sheet URL cho người dùng"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (chat_id, sheet_url)
                VALUES (?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET sheet_url = excluded.sheet_url
            """, (chat_id, sheet_url))
            conn.commit()

    def save_user_limits(self, chat_id, daily=None, weekly=None, monthly=None):
        """Cập nhật hạn mức chi tiêu cho người dùng"""
        user = self.get_user(chat_id)
        if not user:
            # Tạo mới user với giá trị mặc định
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO users (chat_id) VALUES (?)", (chat_id,))
                conn.commit()
                
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if daily is not None:
                cursor.execute("UPDATE users SET daily_limit = ? WHERE chat_id = ?", (daily, chat_id))
            if weekly is not None:
                cursor.execute("UPDATE users SET weekly_limit = ? WHERE chat_id = ?", (weekly, chat_id))
            if monthly is not None:
                cursor.execute("UPDATE users SET monthly_limit = ? WHERE chat_id = ?", (monthly, chat_id))
            conn.commit()

    def is_day_closed(self, chat_id, date_str):
        """Kiểm tra xem ngày đã chốt chưa (date_str định dạng YYYY-MM-DD hoặc DD/MM/YYYY)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_closed FROM daily_status WHERE chat_id = ? AND date = ?", (chat_id, date_str))
            row = cursor.fetchone()
            return row[0] == 1 if row else False

    def close_day(self, chat_id, date_str):
        """Đánh dấu ngày đã được chốt"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO daily_status (chat_id, date, is_closed)
                VALUES (?, ?, 1)
                ON CONFLICT(chat_id, date) DO UPDATE SET is_closed = 1
            """, (chat_id, date_str))
            conn.commit()

    def reopen_day(self, chat_id, date_str):
        """Mở lại ngày đã chốt nếu muốn sửa đổi"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO daily_status (chat_id, date, is_closed)
                VALUES (?, ?, 0)
                ON CONFLICT(chat_id, date) DO UPDATE SET is_closed = 0
            """, (chat_id, date_str))
            conn.commit()

    def get_all_users(self):
        """Lấy danh sách tất cả người dùng hoạt động"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id, sheet_url FROM users WHERE sheet_url IS NOT NULL")
            return [{"chat_id": row[0], "sheet_url": row[1]} for row in cursor.fetchall()]
