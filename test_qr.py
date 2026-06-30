from qr_generator import QRGenerator
from qr_parser import QRParser

def test_integration():
    print("=== CHẠY KIỂM THỬ TÍCH HỢP VIETQR ===")
    
    # 1. Kiểm tra bộ sinh link VietQR
    gen = QRGenerator()
    url = gen.generate_vietqr_url("970436", "1234567890", 50000, "an sang mua xoi")
    print(f"[1] URL VietQR sinh ra: {url}")
    assert "970436" in url
    assert "1234567890" in url
    assert "amount=50000" in url
    assert "addInfo=an%20sang%20mua%20xoi" in url
    print("=> Bộ sinh link VietQR: OK")
    
    # 1b. Kiểm tra bộ sinh link thanh toán nhanh qua dl.vietqr.io
    pay_link = gen.generate_pay_link("970436", "1234567890", 50000, "an sang mua xoi")
    print(f"[1b] Link thanh toan nhanh sinh ra: {pay_link}")
    assert "dl.vietqr.io" in pay_link
    assert "app=vcb" in pay_link
    assert "ba=1234567890@vcb" in pay_link
    assert "am=50000" in pay_link
    assert "tn=an%20sang%20mua%20xoi" in pay_link
    print("=> Bộ sinh link thanh toán nhanh (dl.vietqr.io): OK")
    
    # 2. Kiểm tra bộ giải mã chuỗi EMVCo
    parser = QRParser()
    
    # Chuỗi mẫu VietQR chuẩn EMVCo (Đã sửa độ dài các Tag 38 và 62 chính xác)
    qr_string = (
        "000201"                        # Payload Indicator
        "010212"                        # Dynamic QR
        "3854"                          # Tag 38 (Merchant Info) - Length 54 (14+28+12)
          "0010A000000727"              # NAPAS GUID
          "0124"                        # Tag 01 (Payment Info) - Length 24
            "0006970436"                # Bank BIN 970436 (VCB)
            "01101234567890"            # Account Number 1234567890
          "0208QRIBFTTA"                # Service Code
        "5303704"                       # Currency VND (704)
        "540550000"                     # Amount 50000
        "5802VN"                        # Country VN
        "5912NGUYEN VAN A"              # Account Name
        "6211"                          # Tag 62 - Length 11 (2+2+7)
          "0807AN SANG"                 # Description (Subtag 08) - Length 7
        "6304ABCD"                      # CRC Checksum
    )
    
    print("\n[2] Bắt đầu phân tích chuỗi VietQR...")
    parsed = parser.parse_vietqr_string(qr_string)
    print(f"Kết quả phân tích: {parsed}")
    
    assert parsed is not None
    assert parsed["bank_bin"] == "970436"
    assert parsed["account_number"] == "1234567890"
    assert parsed["amount"] == 50000.0
    assert parsed["description"] == "AN SANG"
    assert parsed["account_name"] == "NGUYEN VAN A"
    assert "Vietcombank" in parsed["bank_name"]
    
    print("=> Bộ phân tích VietQR (EMVCo Parser): OK")
    
    # 3. Kiểm tra giải mã URL thanh toán
    print("\n[3] Bắt đầu kiểm thử giải mã URL thanh toán...")
    url_test = "https://qr.vietqr.co/v2/tcb/19032664473011?amount=50000&nd=Lunch"
    parsed_url = parser.parse_vietqr_string(url_test)
    print(f"Kết quả phân tích URL: {parsed_url}")
    assert parsed_url is not None
    assert parsed_url["bank_bin"] == "970407"
    assert parsed_url["account_number"] == "19032664473011"
    assert parsed_url["amount"] == 50000.0
    assert parsed_url["description"] == "Lunch"
    print("=> Bộ giải mã URL thanh toán: OK")
    
    print("\n🎉 TẤT CẢ CÁC KIỂM THỬ ĐÃ VƯỢT QUA THÀNH CÔNG!")

if __name__ == "__main__":
    test_integration()
