# HBTNFIT

Khung ứng dụng React + Vite và FastAPI. Hiện có thanh điều hướng, giao diện nền tối và API `/api/health` để kiểm tra kết nối. Các file database, model, schema và AI mới là vị trí chờ triển khai; chưa có chức năng đăng nhập, nhận diện món ăn, thực đơn hoặc tập luyện.

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

Mở [frontend](http://127.0.0.1:5173), chọn Trang chủ và bấm **Kiểm tra kết nối API**. Tài liệu API ở [Swagger](http://127.0.0.1:8000/docs). Hai cổng 8000 và 5173 cần còn trống.

Bản khung không cần API key và chưa mở database. `.env.example` chỉ chứa cấu hình mẫu cho các phần sẽ bổ sung. Không commit `.env`, database, ảnh người dùng hoặc thư mục runtime.

## Cấu trúc

```text
backend/
  app/main.py          FastAPI, CORS và health check
  app/db.py            vị trí bổ sung kết nối database
  app/models.py        vị trí bổ sung model
  app/schemas.py       vị trí bổ sung schema
  app/ai.py            vị trí bổ sung tích hợp AI
  tests/test_health.py kiểm tra API khởi động
frontend/
  src/App.jsx          bố cục và điều hướng
  src/api.js           hàm gọi API
  src/constants.js     nhãn bữa ăn và dinh dưỡng
  src/style.css        giao diện nền và responsive
data/                  vị trí bổ sung danh mục CSV
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
