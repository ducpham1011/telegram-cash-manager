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
        Sử dụng dịch vụ chuyển tiếp trung gian của qr.sepay.vn (ổn định và hỗ trợ deep link tốt)
        """
        clean_content = remove_vietnamese_accents(content)[:20].strip()
        encoded_content = quote(clean_content)
        
        # Cú pháp link chuyển tiếp của qr.sepay.vn
        return f"https://qr.sepay.vn/transfer?bank={bank_id}&acc={account_no}&amount={int(amount)}&descr={encoded_content}"
