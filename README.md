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

## Lỗi Gemini và cấu hình khóa

- Khóa chỉ được đọc ở backend từ `.env`; `.env.example` không chứa giá trị thật. Frontend không nhận khóa qua API.
- Mỗi yêu cầu nhận diện dùng chung ngân sách tối đa 45 giây cho các lượt gọi AI, kể cả bước sửa tiếng Việt. Mỗi lượt gọi có timeout tối đa 20 giây và tối đa 3 lần thử trong một lần sinh JSON.
- Timeout, mất kết nối, giới hạn lượt dùng, quá tải và lỗi xác thực được phân loại thành thông báo tiếng Việt. Khóa dự phòng khác khóa chính được thử sau lỗi đầu tiên phù hợp; lỗi yêu cầu không hợp lệ không được che bằng chuyển khóa.
- Kết quả phải là JSON object và không chứa NaN/Infinity. Kết quả sai được báo lỗi nhận diện để người dùng thử lại hoặc nhập tay.
- API scan không chuyển nguyên văn lỗi nhà cung cấp ra giao diện hoặc log ứng dụng. Nhận diện thất bại không tự thêm món hay làm thay đổi tổng thực đơn.

Các kiểm thử dùng khóa giả và dịch vụ giả lập. Khả năng gọi API thật còn phụ thuộc cấu hình, quyền truy cập và tình trạng dịch vụ.

## Chuẩn hóa kết quả nhận diện

- Kiểm tra JSON trước khi ghép với CSV: danh sách tối đa 5 món, tối đa 3 nhãn mỗi món, nguyên liệu dạng danh sách chuỗi và độ tin cậy hợp lệ nếu có.
- Phát hiện thêm tên món ngắn không dấu như `Pho ga`, yêu cầu viết lại tiếng Việt. Nếu bước sửa ngôn ngữ thay đổi cấu trúc, số liệu hoặc ID/đơn vị được bảo vệ thì trả lỗi để người dùng kiểm tra lại.
- Đối chiếu CSV bằng nhãn chính; nhãn thay thế không tự tạo thêm lựa chọn món khác. Kết quả có độ tin cậy thấp cần người dùng kiểm tra, không ép khớp món trong danh mục.
- Ước tính món ngoài danh mục dùng cơ sở 1 g; backend quy đổi về chuẩn lưu trữ tương ứng. Giá trị âm, không hữu hạn, sai kiểu hoặc vượt giới hạn không được dùng làm số liệu dinh dưỡng.

Các kiểm tra này kiểm soát định dạng và tính nhất quán. Chúng không xác nhận thành phần hay dinh dưỡng thật chỉ từ ảnh; món vẫn phải được người dùng xác nhận trước khi lưu.

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
