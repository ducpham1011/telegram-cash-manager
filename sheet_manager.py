import re
from datetime import datetime, timedelta, timezone
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Cấu hình múi giờ Việt Nam (UTC+7)
TZ_VN = timezone(timedelta(hours=7))

def get_vietnam_now():
    return datetime.now(TZ_VN)

class SheetManager:
    def __init__(self, credentials_path):
        self.credentials_path = credentials_path
        self.scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive"
        ]
        self._client = None

    @property
    def client(self):
        if not self._client:
            import os
            import json
            # Thử tải khóa cấu hình từ biến môi trường dạng JSON trước (cho môi trường Serverless như Vercel)
            creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
            if creds_json:
                try:
                    creds_dict = json.loads(creds_json)
                    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, self.scope)
                    self._client = gspread.authorize(creds)
                    return self._client
                except Exception as e:
                    print(f"Lỗi giải mã GOOGLE_CREDENTIALS_JSON: {e}")
            
            # Cách cũ: Tải từ đường dẫn file vật lý
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                self.credentials_path, self.scope
            )
            self._client = gspread.authorize(creds)
        return self._client

    def get_service_account_email(self):
        """Trả về email của Service Account để người dùng tiện share quyền"""
        try:
            import os
            import json
            creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
            if creds_json:
                creds_dict = json.loads(creds_json)
                return creds_dict.get("client_email")
                
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                self.credentials_path, self.scope
            )
            return creds.service_account_email
        except Exception:
            return None

    def _open_sheet(self, sheet_url):
        """Mở Google Sheet bằng URL và trả về worksheet đầu tiên"""
        try:
            sh = self.client.open_by_url(sheet_url)
            # Thử tìm sheet "Lịch sử chi tiêu", nếu không tìm thấy thì lấy sheet đầu tiên
            try:
                worksheet = sh.worksheet("Lịch sử chi tiêu")
            except gspread.exceptions.WorksheetNotFound:
                # Nếu không tìm thấy, lấy sheet đầu tiên và đổi tên thành "Lịch sử chi tiêu"
                worksheet = sh.get_worksheet(0)
                try:
                    worksheet.update_title("Lịch sử chi tiêu")
                except Exception:
                    pass
            
            # Kiểm tra nếu sheet rỗng thì ghi dòng tiêu đề
            headers = ["Ngày", "Giờ", "Số tiền (đ)", "Nội dung", "Danh mục", "Trạng thái", "Chi tiết thanh toán"]
            row_one = worksheet.row_values(1)
            if not row_one or len(row_one) == 0:
                worksheet.append_row(headers)
            
            return worksheet
        except gspread.exceptions.APIError as e:
            if "PERMISSION_DENIED" in str(e):
                raise PermissionError("Bot chưa được cấp quyền chia sẻ (Share) tệp Google Sheet này.")
            raise e

    def verify_connection(self, sheet_url):
        """Kiểm tra xem bot có kết nối và ghi được dữ liệu vào Sheet không"""
        try:
            self._open_sheet(sheet_url)
            return True
        except Exception as e:
            raise e

    def log_spending(self, sheet_url, amount, content, category, status="Đã chuyển", payment_details=""):
        """Ghi nhận khoản chi tiêu vào Google Sheet"""
        try:
            worksheet = self._open_sheet(sheet_url)
            now = get_vietnam_now()
            date_str = now.strftime("%d/%m/%Y")
            time_str = now.strftime("%H:%M:%S")
            
            row = [
                date_str,
                time_str,
                amount,
                content,
                category,
                status,
                payment_details
            ]
            worksheet.append_row(row)
            return date_str, time_str
        except Exception as e:
            raise RuntimeError(f"Lỗi ghi dữ liệu vào Google Sheet: {str(e)}")

    def get_statistics(self, sheet_url, period="day"):
        """Tính toán tổng chi tiêu theo khoảng thời gian: ngày, tuần, tháng"""
        try:
            worksheet = self._open_sheet(sheet_url)
            records = worksheet.get_all_records()
            if not records:
                return 0, []

            now = get_vietnam_now()
            total_spent = 0
            filtered_transactions = []

            for row in records:
                # Bỏ qua dòng tiêu đề nếu có trong records
                if not row.get("Ngày") or not row.get("Số tiền (đ)"):
                    continue

                try:
                    # Chuyển đổi định dạng ngày DD/MM/YYYY
                    tx_date = datetime.strptime(row["Ngày"], "%d/%m/%Y").date()
                    amount = float(str(row["Số tiền (đ)"]).replace(",", "").replace(".", "").strip())
                except ValueError:
                    continue

                is_in_period = False
                if period == "day":
                    is_in_period = (tx_date == now.date())
                elif period == "week":
                    # Tính từ thứ 2 của tuần hiện tại
                    start_of_week = now.date() - timedelta(days=now.weekday())
                    is_in_period = (tx_date >= start_of_week)
                elif period == "month":
                    is_in_period = (tx_date.year == now.year and tx_date.month == now.month)

                if is_in_period:
                    total_spent += amount
                    filtered_transactions.append({
                        "date": row["Ngày"],
                        "time": row.get("Giờ", ""),
                        "amount": amount,
                        "content": row.get("Nội dung", ""),
                        "category": row.get("Danh mục", ""),
                        "status": row.get("Trạng thái", "Đã chuyển")
                    })

            return total_spent, filtered_transactions
        except Exception as e:
            raise RuntimeError(f"Lỗi đọc thống kê từ Google Sheet: {str(e)}")
