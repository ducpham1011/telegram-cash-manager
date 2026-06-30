import cv2
import numpy as np
import requests

# Bản đồ mã BIN -> Tên viết tắt ngân hàng (Dự phòng trường hợp gọi API thất bại)
BACKUP_BANKS_MAP = {
    "970436": "Vietcombank (VCB)",
    "970407": "Techcombank (TCB)",
    "970422": "MBBank (MB)",
    "970415": "VietinBank",
    "970418": "BIDV",
    "970416": "ACB",
    "970423": "TPBank",
    "970432": "VPBank",
    "970403": "Sacombank",
    "970405": "Agribank",
    "970441": "VIB",
    "970443": "SHB",
    "970437": "HDBank",
    "970429": "SCB",
    "970440": "SeABank",
    "970428": "NamABank",
    "970408": "GPBank",
    "970412": "PVcomBank",
    "970434": "Indovina",
    "970454": "Bản Việt (BVBank)"
}

class QRParser:
    def __init__(self):
        self.banks_map = {}
        self.load_banks_data()

    def load_banks_data(self):
        """Tải danh sách các ngân hàng từ API của VietQR để cập nhật mã BIN mới nhất"""
        try:
            response = requests.get("https://api.vietqr.io/v2/banks", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "00":
                    for bank in data.get("data", []):
                        bin_code = bank.get("bin")
                        short_name = bank.get("shortName")
                        custom_name = f"{short_name} ({bank.get('name')})" if short_name else bank.get('name')
                        if bin_code:
                            self.banks_map[bin_code] = custom_name
        except Exception:
            # Nếu gặp lỗi mạng, sử dụng dữ liệu dự phòng
            pass
        
        # Merge dữ liệu dự phòng vào nếu chưa có
        for bin_code, name in BACKUP_BANKS_MAP.items():
            if bin_code not in self.banks_map:
                self.banks_map[bin_code] = name

    def get_bank_name(self, bin_code):
        return self.banks_map.get(bin_code, f"Mã BIN: {bin_code}")

    def decode_image(self, image_bytes):
        """Giải mã hình ảnh chứa QR thành chuỗi text bằng OpenCV"""
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return None
            
            # Sử dụng QRCodeDetector của OpenCV
            detector = cv2.QRCodeDetector()
            data, bbox, straight_qrcode = detector.detectAndDecode(img)
            
            if not data:
                # Thử resize hoặc chuyển sang ảnh xám để cải thiện độ nhận diện nếu thất bại lần đầu
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                data, bbox, straight_qrcode = detector.detectAndDecode(gray)
                
            return data if data else None
        except Exception as e:
            print(f"Lỗi giải mã ảnh QR: {str(e)}")
            return None

    def parse_tlv(self, data):
        """Phân tích chuỗi định dạng EMVCo Tag-Length-Value"""
        result = {}
        i = 0
        while i < len(data):
            if i + 4 > len(data):
                break
            tag = data[i:i+2]
            try:
                length = int(data[i+2:i+4])
            except ValueError:
                break
            value = data[i+4:i+4+length]
            result[tag] = value
            i += 4 + length
        return result

    def parse_vietqr_string(self, qr_string):
        """
        Phân tích chuỗi VietQR chuẩn EMVCo thành các thông tin chi tiết
        """
        if not qr_string or not (qr_string.startswith("00") or "38" in qr_string):
            return None

        try:
            fields = self.parse_tlv(qr_string)
            
            # Tag 38 là thông tin tài khoản nhận tiền (Merchant Account Info)
            account_info_raw = fields.get("38", "")
            if not account_info_raw:
                # Một số mã QR sử dụng Tag 26 thay cho Tag 38 tùy theo phiên bản EMVCo
                account_info_raw = fields.get("26", "")
                
            account_info = self.parse_tlv(account_info_raw)
            
            # Subtag 01 chứa mã BIN và Số tài khoản nhận tiền
            payment_info_raw = account_info.get("01", "")
            payment_info = self.parse_tlv(payment_info_raw)
            
            bank_bin = payment_info.get("00", "")
            account_number = payment_info.get("01", "")
            
            # Tag 54 là Số tiền (Amount)
            amount_str = fields.get("54", "")
            amount = float(amount_str) if amount_str else None
            
            # Tag 59 là Tên chủ tài khoản (Account Name)
            account_name = fields.get("59", "")
            
            # Tag 62 là thông tin bổ sung (Additional Data Field Template)
            additional_info_raw = fields.get("62", "")
            additional_info = self.parse_tlv(additional_info_raw)
            # Subtag 08 là nội dung chuyển khoản / Reference Label
            description = additional_info.get("08", "")
            
            # Nếu không tìm thấy bank_bin hoặc số tài khoản thì mã QR không hợp lệ
            if not bank_bin or not account_number:
                return None
                
            bank_name = self.get_bank_name(bank_bin)
            
            return {
                "bank_bin": bank_bin,
                "bank_name": bank_name,
                "account_number": account_number,
                "account_name": account_name,
                "amount": amount,
                "description": description,
                "qr_string": qr_string
            }
        except Exception as e:
            print(f"Lỗi phân tích cú pháp VietQR: {str(e)}")
            return None
            
    def parse_image_to_vietqr(self, image_bytes):
        """Giải mã ảnh và phân tích chuỗi VietQR chỉ trong một bước"""
        qr_string = self.decode_image(image_bytes)
        if not qr_string:
            return None
        return self.parse_vietqr_string(qr_string)
