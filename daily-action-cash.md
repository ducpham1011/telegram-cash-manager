# Hành động chi tiêu hàng ngày

- Phát sinh hoá đơn, khoản chi
- Mở ứng dụng ngân hàng
- Nhập số tiền
- Chuyển khoản

# Mong muốn chức năng của tool/bot:
- Nhận input về số tiền, nội dung chi tiêu, danh mục chi tiêu, thời gian
- Generate QR code chuyển tiền
- Từ QR code chuyển tiền, có button điều hướng sang app ngân hàng với số tiền và nội dung chuyển khoản có trong QR
- Sau khi chuyển khoản, bot sẽ ghi lại lịch sử chi tiêu trong googlesheet
- Có thể tổng hợp, thống kê các hoạt động chi tiêu trong tuần, trong tháng. Dữ liệu được lấy từ file google sheets
- Bot nhắc nhở hàng ngày lúc 21h để cập nhật hoặc chốt các khoản chi trong ngày. Nếu chưa chốt khoản chi trong ngày sẽ nhắc nhở định kỳ về ngày chưa chốt mỗi giờ 1 lần.
- Có thể đặt ra hạn mức chi tiêu trong ngày, tuần, tháng. Nếu quá sẽ cảnh báo