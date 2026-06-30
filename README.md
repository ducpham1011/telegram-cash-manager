# 💸 Cash Manager - Telegram Bot Quản lý Chi tiêu Cá nhân

Cash Manager là một bộ công cụ Telegram Bot cá nhân tích hợp trực tiếp với Google Sheets giúp bạn quản lý, theo dõi và chốt hạn mức chi tiêu hàng ngày một cách trực quan, tối ưu và nhanh chóng nhất.

---

## ✨ Tính năng nổi bật

1.  **Quét QR trực tiếp (Real-time Scan):** Tích hợp Telegram WebApp SDK, chỉ cần bấm nút `📷 Quét QR trực tiếp` trên bàn phím Bot, camera quét QR của Telegram sẽ mở lên để bạn quét trực tiếp hóa đơn/mã chuyển khoản tại quầy.
2.  **Gửi ảnh QR (Photo Upload):** Hỗ trợ gửi ảnh chụp màn hình/ảnh chụp chứa mã QR chuyển khoản ngân hàng VietQR. Bot tự động phân tích lấy thông tin.
3.  **Tự động tạo VietQR & Link thanh toán:** Khi nhập thủ công giao dịch và chọn thanh toán chuyển khoản, Bot tự sinh ảnh mã VietQR và link thanh toán nhanh giúp điều hướng trực tiếp vào ứng dụng ngân hàng trên điện thoại (đã điền sẵn số tiền và nội dung chuyển khoản).
4.  **Đồng bộ Google Sheets linh hoạt:** Không lưu dữ liệu giao dịch trên server cá nhân, dữ liệu được ghi trực tiếp vào tệp Google Sheets của bạn. Mỗi người dùng tự cấu hình link Google Sheets riêng.
5.  **Quản lý Hạn mức & Cảnh báo:** Thiết lập hạn mức chi tiêu theo Ngày, Tuần, Tháng. Cảnh báo trực quan bằng thanh tiến trình (progress bar) và tin nhắn đỏ nếu chi tiêu vượt quá giới hạn.
6.  **Nhắc nhở Chốt ngày thông minh:** Nhắc nhở định kỳ vào lúc 21:00 hàng ngày và nhắc nhở hàng giờ sau đó nếu bạn chưa chốt chi tiêu của ngày hôm nay, hoặc nhắc vào ban ngày nếu bạn quên chốt ngày hôm qua.

---

## 🏗️ Cấu trúc thư mục

```plaintext
cash-manager/
├── webapp/                  # Chứa trang tĩnh phục vụ quét QR trực tiếp
│   └── index.html           # Trang HTML tĩnh tích hợp Telegram WebApp SDK gọi camera quét QR
├── config.env               # File cấu hình (Telegram Token, WebApp URL...) [Chưa commit]
├── config.env.example       # File cấu hình mẫu
├── credentials.json         # Khóa bí mật kết nối API Google Sheets (Service Account) [Chưa commit]
├── db_manager.py            # Quản lý cơ sở dữ liệu cấu hình MongoDB
├── sheet_manager.py         # Quản lý tương tác đọc/ghi với Google Sheets
├── qr_generator.py          # Module sinh mã VietQR và Pay Link mở app ngân hàng
├── qr_parser.py             # Module dùng OpenCV giải mã QR từ hình ảnh gửi lên
├── scheduler.py             # Quản lý sự kiện gửi tin nhắn nhắc nhở chốt chi tiêu định kỳ
├── requirements.txt         # Các thư viện python phụ thuộc
└── README.md                # Tài liệu hướng dẫn sử dụng này
```

---

## 🚀 Hướng dẫn cài đặt & Cấu hình

### Bước 1: Chuẩn bị tài nguyên trên Google Cloud (Kết nối Google Sheets)
Để Bot có thể ghi chép vào Google Sheets của bạn:
1.  Truy cập vào [Google Cloud Console](https://console.cloud.google.com/).
2.  Tạo một Project mới.
3.  Bật (Enable) hai dịch vụ API sau:
    *   **Google Sheets API**
    *   **Google Drive API**
4.  Truy cập mục **APIs & Services > Credentials** $\rightarrow$ Chọn **Create Credentials > Service Account**.
5.  Sau khi tạo xong Service Account, chọn tài khoản đó $\rightarrow$ Vào tab **Keys** $\rightarrow$ **Add Key > Create new key (định dạng JSON)**.
6.  Tải file key này về máy, đổi tên thành `credentials.json` và đặt nó vào thư mục `cash-manager/`.

### Bước 2: Tạo Telegram Bot & WebApp quét QR
1.  Mở Telegram, nhắn tin với [@BotFather](https://t.me/BotFather).
2.  Gửi lệnh `/newbot` để tạo bot mới và lấy **API Token**.
3.  Gửi lệnh `/newapp` để liên kết tính năng WebApp quét QR trực tiếp:
    *   Chọn bot vừa tạo.
    *   Nhập tên cho WebApp (ví dụ: `Quét mã QR`).
    *   Cung cấp URL của trang quét: Bạn phải deploy thư mục `webapp/index.html` lên một host có hỗ trợ HTTPS (như Vercel, Netlify hoặc GitHub Pages) và điền đường dẫn HTTPS đó vào phần **Webapp URL**. (Hoặc bạn có thể dùng đường dẫn đã được host sẵn nếu có).
    *   Nhập tên ngắn (Short name) cho WebApp và hoàn thành.

### Bước 3: Cấu hình mã nguồn cục bộ
1.  Di chuyển vào thư mục dự án và sao chép tệp cấu hình mẫu:
    ```bash
    cp config.env.example config.env
    ```
2.  Mở `config.env` và điền thông tin tương ứng:
    ```ini
    # Cấu hình Token Telegram Bot
    TELEGRAM_TOKEN=ĐIỀN_TOKEN_BOT_TELEGRAM_CỦA_BẠN

    # Mã bảo mật (API Key) để gọi API điều khiển từ bên ngoài (tùy chọn)
    API_KEY=your_secret_api_key_here

    # URL WebApp quét QR trực tiếp đã deploy có hỗ trợ HTTPS
    WEBAPP_URL=ĐIỀN_URL_HTTPS_WEBAPP_ĐÃ_DEPLOY

    # Đường dẫn file chứng thực Google Sheets API
    GOOGLE_CREDENTIALS_FILE=credentials.json

    # Đường dẫn lưu cơ sở dữ liệu SQLite cục bộ
    DATABASE_PATH=cash_manager.db
    ```

### Bước 4: Khởi chạy dự án
1.  Cài đặt môi trường ảo Python và cài đặt các thư viện phụ thuộc:
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # Trên Windows dùng: .venv\Scripts\activate
    pip install -r requirements.txt
    ```
2.  Chạy chương trình Bot:
    ```bash
    python bot.py
    ```

---

## 💡 Hướng dẫn sử dụng chi tiết

### 1. Khởi tạo & Cấu hình lần đầu
*   Nhấn nút **`/start`** trên đoạn chat với Bot.
*   Cài đặt Google Sheet của bạn bằng lệnh:
    `/setup_sheet https://docs.google.com/spreadsheets/d/your-sheet-id/edit`
*   **QUAN TRỌNG:** Copy email Service Account hiển thị trên màn hình bot (hoặc trong file `credentials.json` trường `client_email`) và tiến hành **Chia sẻ (Share) tệp Google Sheet của bạn cho email này với quyền Editor**.

### 2. Nhập chi tiêu bằng quét QR trực tiếp (Khuyên dùng)
1.  Tại cửa hàng, bấm nút **`📷 Quét QR trực tiếp`** trên bàn phím dưới chân chat.
2.  Điện thoại sẽ mở camera quét mã QR. Hướng camera vào mã VietQR của cửa hàng.
3.  Hệ thống tự động giải mã: hiển thị **Số tiền, tên cửa hàng, nội dung**.
4.  Bấm vào các nút danh mục chi tiêu hiển thị (Ăn uống, Mua sắm...) để hoàn tất ghi chép.
5.  *Nếu mã QR chưa điền số tiền:* Bạn có thể chọn danh mục và bot sẽ tự ghi nhận hoặc hỏi số tiền.

### 3. Nhập chi tiêu bằng cách gửi ảnh chụp (Photo Upload)
1.  Gửi bất kỳ hình ảnh mã QR chuyển khoản nào vào phòng chat.
2.  Bot sẽ tự động quét ảnh và thực hiện bóc tách tương tự như quét trực tiếp.

### 4. Nhập chi tiêu thủ công
1.  Bấm nút **`✍️ Nhập thủ công`**.
2.  Lần lượt làm theo hướng dẫn: Nhập số tiền $\rightarrow$ Nhập nội dung chi tiêu $\rightarrow$ Chọn danh mục $\rightarrow$ Chọn phương thức thanh toán (**Tiền mặt** để ghi trực tiếp, hoặc **Chuyển khoản** để bot sinh mã QR kèm link chuyển khoản).

### 5. Quản lý hạn mức và báo cáo
*   **Xem thống kê:** Bấm **`📊 Thống kê`** để xem báo cáo Ngày, Tuần, Tháng kèm biểu đồ tiến trình và danh sách danh mục chi nhiều nhất.
*   **Thiết lập hạn mức:** Gõ `/set_limit` $\rightarrow$ Chọn Hạn mức Ngày/Tuần/Tháng $\rightarrow$ Nhập số tiền giới hạn.
*   **Chốt ngày:** Gõ `/close_day` để chốt sổ chi tiêu cuối ngày (hoặc bấm nút chốt trong tin nhắn nhắc nhở lúc 21h).

---

## 🛠️ Phát triển nâng cao
Mã nguồn này được viết tách biệt các tầng độc lập để bạn dễ dàng nâng cấp:
*   Muốn đổi định dạng dòng dữ liệu ghi vào Sheets: Sửa đổi hàm `log_spending` trong `sheet_manager.py`.
*   Muốn nâng cấp luồng tự động kiểm tra biến động số dư (Không cần bấm xác nhận): Bạn có thể liên kết Webhook từ Casso/SePay bằng cách tạo một API endpoint nhận dữ liệu POST trong `bot.py` sử dụng thư viện micro-web framework như `FastAPI`.
