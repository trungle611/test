# HBTNFIT

HBTNFIT dùng React + Vite, FastAPI và SQLite. Bản này đã nối luồng ăn uống: tải ảnh, nhận gợi ý Gemini, chọn bữa, sửa món/khẩu phần, xác nhận, cập nhật thực đơn và xem lịch sử. Đăng nhập, trang cá nhân và tập luyện chưa được tích hợp vào giao diện này.

Backend nạp hai danh mục CSV trong `data/` khi khởi động. Xem [mô tả cấu trúc, đơn vị và nguồn dữ liệu](data/README.md).

## Chạy local

Yêu cầu Python 3.11+, Node.js 20+ và Git. Chạy các lệnh sau từ thư mục gốc repo:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements-dev.txt
Copy-Item backend\.env.example backend\.env
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Mở terminal khác từ thư mục gốc repo:

```powershell
cd frontend
npm ci
npm run dev
```

Mở [frontend](http://127.0.0.1:5173) để thử luồng ăn uống. Tài liệu API ở [Swagger](http://127.0.0.1:8000/docs). Hai cổng 8000 và 5173 cần còn trống.

Để nhận diện thật, điền `GEMINI_API_KEY` và model được phép sử dụng trong `backend/.env`. Có thể điền `GEMINI_FALLBACK_API_KEY` nếu có khóa dự phòng. Không có key vẫn chạy được ứng dụng và kiểm thử bằng giả lập; giao diện sẽ báo lỗi nhận diện và cho nhập món thủ công. Không có chế độ giả lập Gemini được bật sẵn trong ứng dụng.

SQLite tạo `backend/hbtnfit.db` khi chạy bằng lệnh trên. Ảnh lịch sử lưu trong `backend/uploads/scans`. Bản này nhận diện phiên sử dụng bằng mã lưu trong trình duyệt. Không commit `.env`, database, ảnh người dùng hoặc thư mục runtime.

## Luồng sử dụng

1. Chọn bữa sáng, trưa, tối hoặc bữa phụ rồi tải ảnh JPG, PNG hoặc WEBP, tối đa 5 MB.
2. Kiểm tra từng món Gemini gợi ý. Có thể chọn lại món trong CSV, nhập món mới hoặc bỏ món nhận diện sai.
3. Sửa lượng ăn. Tô, quả, đĩa và các đơn vị đếm cần số nguyên; g và ml có thể nhập số thập phân. Dinh dưỡng xem trước cập nhật theo lượng ăn.
4. Nhấn **Xác nhận thêm**. Chỉ lúc này món mới được cộng vào thực đơn. Mã xác nhận ngăn gửi lại cùng yêu cầu làm trùng món.
5. Sửa hoặc xóa món trong thực đơn. Lịch sử ăn theo ngày và tổng dinh dưỡng cập nhật theo dữ liệu đã lưu.
6. Lịch sử ảnh chỉ hiện bản ghi đã xác nhận, có nút **Xem ảnh**. Thời gian hiển thị theo múi giờ Việt Nam.

Gợi ý và số liệu dinh dưỡng cần được người dùng kiểm tra. Các kiểm thử gọi AI bằng giả lập xác nhận luồng xử lý, không đánh giá độ chính xác của Gemini trên ảnh thật.

## Cấu trúc

```text
backend/
  app/main.py          API scan, thực đơn, khẩu phần và lịch sử
  app/db.py            engine, session và cập nhật schema demo
  app/models.py        model SQLAlchemy dùng chung
  app/schemas.py       kiểm tra dữ liệu đầu vào
  app/catalog.py       nạp CSV
  app/core.py          đối chiếu món và tính dinh dưỡng
  app/ai.py            gọi Gemini và xử lý lỗi
  app/scan_service.py  kiểm tra ảnh, chuẩn hóa món và lưu ảnh lịch sử
  app/goals.py         tính mục tiêu và đánh giá lịch sử dinh dưỡng
  tests/              health check và kiểm thử luồng ăn uống
frontend/
  src/App.jsx          bố cục và điều hướng
  src/api.js           hàm gọi API
  src/constants.js     nhãn bữa ăn và dinh dưỡng
  src/style.css        giao diện nền và responsive
  src/ScanSection.jsx  tải ảnh, kiểm tra và xác nhận món
  src/TodayMeals.jsx   thực đơn, sửa/xóa và tổng dinh dưỡng
  src/ScanHistory.jsx  lịch sử quét và xem ảnh
  src/FoodHistory.jsx  tổng hợp thực đơn theo ngày
data/                  danh mục CSV và mô tả cấu trúc, đơn vị, nguồn
```

## Kiểm tra

Từ thư mục gốc repo:

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check backend
.\.venv\Scripts\python -m ruff format --check backend
cd frontend
npm run format:check
npm run build
```

API key thật không cần thiết cho bộ kiểm thử. Các test dùng SQLite và thư mục ảnh tạm. Để chạy song song với một backend khác, có thể đặt `API_PROXY_TARGET` khi khởi động Vite; mặc định vẫn là `http://127.0.0.1:8000`.
