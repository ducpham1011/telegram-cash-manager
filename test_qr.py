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
    print("\n🎉 TẤT CẢ CÁC KIỂM THỬ ĐÃ VƯỢT QUA THÀNH CÔNG!")

if __name__ == "__main__":
    test_integration()
