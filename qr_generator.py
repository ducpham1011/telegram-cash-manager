import re
import unicodedata
from urllib.parse import quote

def remove_vietnamese_accents(text):
    """Chuyển đổi chuỗi tiếng Việt có dấu thành không dấu, loại bỏ ký tự đặc biệt"""
    if not text:
        return ""
    
    # Thay thế chữ Đ/đ thủ công trước vì normalize không xử lý được chữ này
    text = text.replace('đ', 'd').replace('Đ', 'D')
    
    # Phân tách các tổ hợp dấu unicode (normalize sang NFKD)
    nfkd_form = unicodedata.normalize('NFKD', text)
    only_ascii = nfkd_form.encode('ASCII', 'ignore').decode('ASCII')
    
    # Chỉ giữ lại chữ cái, số, khoảng trắng, gạch ngang và gạch dưới
    clean_text = re.sub(r'[^a-zA-Z0-9\s\-_]', '', only_ascii)
    
    # Loại bỏ khoảng trắng thừa
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    return clean_text

# Bản đồ mã BIN -> App ID để sinh link thanh toán trực tiếp qua cổng dl.vietqr.io
BIN_TO_APP_ID = {
    "970436": "vcb",
    "970407": "tcb",
    "970422": "mb",
    "970415": "icb",
    "970418": "bidv",
    "970416": "acb",
    "970432": "vpb",
    "970423": "tpb",
    "970403": "sacombank",
    "970405": "vba",
    "970441": "vib",
    "970443": "shb",
    "970437": "hdb",
    "970448": "ocb",
    "970426": "msb",
    "970431": "eib",
    "970429": "scb",
    "970440": "seab",
    "970428": "nab",
    "970414": "oceanbank",
    "970408": "gpb",
    "970412": "pvcb",
    "970433": "vietbank",
    "970438": "bvb",
    "970446": "coopbank",
    "970449": "lpb",
    "970452": "klb",
    "970457": "wvn",
    "970421": "vrb",
    "458761": "hsbc",
    "970410": "standardchartered",
    "970439": "pbvn",
    "970419": "ncb",
    "970409": "bab",
    "970427": "vab",
    "970425": "abb",
    "970454": "timo",
    "970444": "cbb",
    "422589": "cimb",
    "970406": "vikki",
    "796500": "dbs"
}

class QRGenerator:
    def __init__(self, default_template="compact2"):
        self.default_template = default_template

    def generate_vietqr_url(self, bank_id, account_no, amount, content, account_name=None):
        """
        Tạo URL ảnh VietQR qua API vietqr.io
        - bank_id: Mã BIN ngân hàng (ví dụ: 970415) hoặc tên viết tắt (vcb, tcb...)
        - account_no: Số tài khoản nhận
        - amount: Số tiền giao dịch
        - content: Nội dung chuyển khoản
        - account_name: Tên chủ tài khoản (tùy chọn)
        """
        # Làm sạch nội dung chuyển khoản (không dấu, không ký tự đặc biệt)
        clean_content = remove_vietnamese_accents(content)
        # Giới hạn nội dung chuyển khoản dưới 20 ký tự để tương thích tốt với hầu hết ngân hàng
        clean_content = clean_content[:20].strip()
        
        encoded_content = quote(clean_content)
        
        url = f"https://img.vietqr.io/image/{bank_id}-{account_no}-{self.default_template}.png"
        url += f"?amount={int(amount)}&addInfo={encoded_content}"
        
        if account_name:
            clean_name = remove_vietnamese_accents(account_name).upper()
            url += f"&accountName={quote(clean_name)}"
            
        return url

    def generate_pay_link(self, bank_id, account_no, amount, content):
        """
        Tạo Link thanh toán nhanh (Quick Pay Link) để mở thẳng hoặc điều hướng tới app ngân hàng
        Sử dụng cổng deeplink chính thức dl.vietqr.io
        """
        clean_content = remove_vietnamese_accents(content)[:20].strip()
        encoded_content = quote(clean_content)
        
        # Ánh xạ bank_id (mã BIN hoặc tên viết tắt) sang appId tương ứng của dl.vietqr.io
        bank_key = str(bank_id).strip().lower()
        app_id = BIN_TO_APP_ID.get(bank_key, bank_key)
        
        # Cú pháp link chuyển tiếp chính thức của dl.vietqr.io
        return f"https://dl.vietqr.io/pay?app={app_id}&ba={account_no}@{app_id}&am={int(amount)}&tn={encoded_content}"
