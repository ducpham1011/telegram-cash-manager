import cv2
import numpy as np
import requests

# Bản đồ mã BIN -> Tên viết tắt ngân hàng (Đầy đủ 40+ ngân hàng tại Việt Nam)
BACKUP_BANKS_MAP = {
    "970436": "Vietcombank (VCB)",
    "970407": "Techcombank (TCB)",
    "970422": "MBBank (MB)",
    "970415": "VietinBank",
    "970418": "BIDV",
    "970416": "ACB",
    "970432": "VPBank",
    "970423": "TPBank",
    "970403": "Sacombank",
    "970405": "Agribank",
    "970441": "VIB",
    "970443": "SHB",
    "970437": "HDBank",
    "970448": "OCB",
    "970426": "MSB",
    "970431": "Eximbank",
    "970429": "SCB",
    "970440": "SeABank",
    "970428": "NamABank",
    "970414": "Oceanbank",
    "970408": "GPBank",
    "970412": "PVcomBank",
    "970433": "VietBank",
    "970438": "BaoVietBank",
    "970446": "CoopBank",
    "970449": "LPBank",
    "970452": "KienLongBank",
    "668888": "KBank",
    "970457": "Woori Bank",
    "970421": "VRB",
    "458761": "HSBC",
    "970410": "StandardChartered",
    "970439": "PublicBank",
    "970419": "NCB",
    "970409": "BacABank",
    "970427": "VietABank",
    "970425": "ABBANK",
    "970454": "BVBank (Bản Việt)",
    "970444": "CBBank",
    "422589": "CIMB",
    "970406": "Vikki",
    "970442": "HongLeong",
    "796500": "DBS Bank"
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

    def parse_url_to_vietqr(self, url):
        """
        Phân tích cú pháp các đường dẫn thanh toán phổ biến để bóc tách thông tin ngân hàng và tài khoản
        """
        url_lower = url.strip().lower()
        
        bank_bin = None
        account_number = None
        amount = None
        description = None
        
        # Mapping từ shortName sang mã BIN ngân hàng
        short_to_bin = {
            "vcb": "970436", "vietcombank": "970436",
            "tcb": "970407", "techcombank": "970407",
            "mb": "970422", "mbbank": "970422",
            "icb": "970415", "vietinbank": "970415",
            "bidv": "970418",
            "acb": "970416",
            "vpb": "970432", "vpbank": "970432",
            "tpb": "970423", "tpbank": "970423",
            "sacombank": "970403",
            "vba": "970405", "agribank": "970405",
            "vib": "970441",
            "shb": "970443",
            "hdb": "970437", "hdbank": "970437",
            "ocb": "970448",
            "msb": "970426",
            "eib": "970431", "eximbank": "970431",
            "scb": "970429",
            "seab": "970440", "seabank": "970440",
            "nab": "970428", "namabank": "970428",
            "lpb": "970449", "lpbank": "970449",
            "bvb": "970438", "baovietbank": "970438",
            "vietbank": "970433"
        }
        
        # 1. Định dạng https://qr.vietqr.co/v2/<bank>/<account>
        # Hoặc https://pay.vietqr.co/<bank>/<account>
        import re
        match1 = re.search(r"vietqr\.(co|io|vn)/(v2/)?([a-zA-Z0-9\-]+)/([0-9]+)", url_lower)
        if match1:
            bank_bin = match1.group(3).replace("-", "")
            account_number = match1.group(4)
            
        # 2. Định dạng https://img.vietqr.io/image/<bank>-<account>-<template>.png
        match2 = re.search(r"img\.vietqr\.io/image/([a-zA-Z0-9\-]+)-([0-9]+)", url_lower)
        if match2:
            bank_bin = match2.group(1).replace("-", "")
            account_number = match2.group(2)
            
        # 3. Định dạng qr.sepay.vn
        if "qr.sepay.vn" in url_lower:
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(url)
            params = parse_qs(parsed_url.query)
            bank_bin = params.get("bank", [None])[0]
            account_number = params.get("acc", [None])[0]
            amount_str = params.get("amount", [None])[0]
            if amount_str:
                try:
                    amount = float(amount_str)
                except ValueError:
                    pass
            description = params.get("descr", [None])[0]
            
        # 4. Định dạng dl.vietqr.io
        if "dl.vietqr.io" in url_lower:
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(url)
            params = parse_qs(parsed_url.query)
            app = params.get("app", [None])[0]
            ba = params.get("ba", [None])[0]
            if ba and "@" in ba:
                account_number, bank_bin = ba.split("@", 1)
            elif ba:
                account_number = ba
                bank_bin = app
                
            amount_str = params.get("am", [None])[0]
            if amount_str:
                try:
                    amount = float(amount_str)
                except ValueError:
                    pass
            description = params.get("tn", [None])[0] or params.get("addinfo", [None])[0]
            
        # Lấy thêm các query parameters phổ biến (amount, addInfo, nd)
        if (bank_bin and account_number) and (not amount or not description):
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(url)
            params = parse_qs(parsed_url.query)
            
            if not amount:
                amount_str = params.get("amount", [None])[0] or params.get("am", [None])[0]
                if amount_str:
                    try:
                        amount = float(amount_str)
                    except ValueError:
                        pass
            if not description:
                description = params.get("addinfo", [None])[0] or params.get("nd", [None])[0] or params.get("tn", [None])[0]
                
        if bank_bin and account_number:
            # Chuẩn hóa bank_bin (chuyển chữ viết tắt thành mã BIN số)
            resolved_bin = short_to_bin.get(bank_bin, bank_bin)
            bank_name = self.get_bank_name(resolved_bin)
            
            return {
                "bank_bin": resolved_bin,
                "bank_name": bank_name,
                "account_number": account_number,
                "account_name": "", # URL không chứa tên chủ tài khoản thụ hưởng
                "amount": amount,
                "description": description,
                "qr_string": url
            }
            
        return None

    def parse_vietqr_string(self, qr_string):
        """
        Phân tích chuỗi VietQR chuẩn EMVCo hoặc URL thanh toán thành các thông tin chi tiết
        """
        if not qr_string:
            return None
            
        # NẾU LÀ ĐƯỜNG DẪN (URL): Chuyển qua bộ phân tích URL
        if qr_string.strip().lower().startswith("http"):
            return self.parse_url_to_vietqr(qr_string)

        if not (qr_string.startswith("00") or "38" in qr_string or "26" in qr_string):
            return None

        try:
            fields = self.parse_tlv(qr_string)
            
            # Tag 38 hoặc Tag 26 là thông tin tài khoản nhận tiền (Merchant Account Info)
            account_info_raw = fields.get("38", "")
            if not account_info_raw:
                account_info_raw = fields.get("26", "")
                
            account_info = self.parse_tlv(account_info_raw)
            
            # Subtag 01 chứa mã BIN và Số tài khoản nhận tiền
            payment_info_raw = account_info.get("01", "")
            payment_info = self.parse_tlv(payment_info_raw)
            
            bank_bin = payment_info.get("00", "")
            account_number = payment_info.get("01", "")
            
            # --- CƠ CHẾ DỰ PHÒNG (FALLBACK PARSING) ---
            # Nếu cấu trúc lồng nhau của tag 38/26 bị khác chuẩn Napas 01, quét tất cả subtag
            if not bank_bin or not account_number:
                for subtag_id, subtag_val in account_info.items():
                    sub_fields = self.parse_tlv(subtag_val)
                    if "00" in sub_fields and "01" in sub_fields:
                        val_00 = sub_fields["00"]
                        # Kiểm tra xem mã BIN có hợp lý không (thường là 6 chữ số)
                        if len(val_00) == 6 and val_00.isdigit():
                            bank_bin = val_00
                            account_number = sub_fields["01"]
                            break
            
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
