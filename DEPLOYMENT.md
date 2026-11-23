# Chạy demo và cấu hình triển khai HBTNFIT

## 1. Chuẩn bị

- Python 3.11 trở lên, Node.js 22, Git. Kiểm tra `python --version`, `node --version`, `npm --version`.
- Với Mac Intel chạy macOS 12, dùng Node 22 phù hợp hệ điều hành; không dùng bản Node mới hơn yêu cầu macOS mới hơn. [Bản tải Node 22](https://nodejs.org/en/download/archive/v22).
- Luôn mở terminal tại thư mục gốc có `backend/` và `frontend/`. Không chạy lệnh cài backend trong `frontend/`.
- Giữ nguyên `.env` và database đang dùng. Chỉ sao chép `.env.example` khi chưa có `.env`.

## 2. Windows PowerShell

Tại thư mục gốc:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
if (!(Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Mở terminal thứ hai, tại thư mục gốc:

```powershell
cd frontend
npm ci
npm run dev
```

## 3. macOS/Linux

Tại thư mục gốc:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
test -f backend/.env || cp backend/.env.example backend/.env
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Terminal thứ hai: `cd frontend`, `npm ci`, `npm run dev`.
Môi trường `.venv` của Windows không dùng được trên Mac; tạo lại bằng Python trên chính máy đó.

## 4. Cấu hình dữ liệu và phiên đăng nhập

Điền cấu hình riêng trong `backend/.env`. Không commit `.env`, khóa API, database, thư mục ảnh hoặc khóa ký phiên.

| Biến | Ý nghĩa |
| --- | --- |
| `APP_ENV` | `local` khi demo; `production` khi triển khai chính thức. |
| `APP_DATA_DIR` | Thư mục dữ liệu bền. Nếu để trống, dự án mới dùng `backend/.runtime`. |
| `DATABASE_URL` | Để trống để tự tìm một database cũ tại gốc/backend; nếu có hai file cùng tên phải chọn đường dẫn tuyệt đối. |
| `SCAN_UPLOAD_DIR` | Thư mục ảnh riêng; mặc định trong thư mục dữ liệu, hoặc giữ thư mục ảnh cũ nếu đã có. |
| `AUTH_SECRET` | Chuỗi ngẫu nhiên ít nhất 32 ký tự ở production. Local để trống sẽ tự tạo và giữ khóa trong thư mục dữ liệu. |
| `GEMINI_API_KEY` | Khóa Gemini phía backend. Thiếu khóa vẫn đăng nhập/lưu mục tiêu được, nhưng không gọi nhận diện/gợi ý AI được. |
| `GEMINI_FALLBACK_API_KEY` | Khóa dự phòng tùy chọn. Hai khóa chung project thường dùng chung hạn mức. |
| `FRONTEND_ORIGINS` | Domain frontend đầy đủ, phân cách bằng dấu phẩy; ví dụ `https://hbtnfit.example.com`. |

Ví dụ SQLite trên Windows: `DATABASE_URL=sqlite:///D:/HBTNFIT-data/hbtnfit.db`.
Trên Linux: `DATABASE_URL=sqlite:////var/lib/hbtnfit/hbtnfit.db`.
Nếu dùng PostgreSQL: `DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DB` (giữ bí mật chuỗi thật).

Khởi động lần đầu tự tạo bảng và nạp CSV. Các migration nhỏ giữ cột/dữ liệu cũ. Sao lưu trước khi nâng cấp. Bản này bổ sung bảng phiên đăng nhập: tài khoản cũ vẫn còn nhưng cần đăng nhập lại để tạo phiên mới.
Đăng xuất thu hồi phiên hiện tại ở server; các thiết bị khác vẫn đăng nhập. Đổi `AUTH_SECRET` làm mọi token cũ mất hiệu lực.

### Sao lưu và khôi phục local

1. Dừng backend để không có thao tác ghi SQLite.
2. Sao chép database thực tế, thư mục ảnh và `auth-secret` (nếu dùng khóa tự tạo) sang nơi riêng. Không đưa bản sao lưu lên Git.
3. Khôi phục cả database và thư mục ảnh; đặt lại đúng `DATABASE_URL`, `SCAN_UPLOAD_DIR`, `AUTH_SECRET`.
4. Chạy backend, đăng nhập, kiểm tra thực đơn/lịch sử/tập luyện. Không xóa DB để chữa lỗi đăng nhập.

## 5. Demo qua tunnel

Chạy cả backend 8000 và frontend 5173. Tunnel trỏ vào frontend; proxy `/api` chuyển đến backend. Nếu Vite chặn hostname, đặt hostname tunnel vào `frontend/.env` tại `DEV_ALLOWED_HOSTS`, khởi động lại Vite. Không đặt `allowedHosts: true`.
Máy phải bật và cả hai tiến trình phải chạy. Tắt tunnel không xóa database; tắt máy làm link demo tạm ngừng phục vụ.

## 6. Triển khai frontend lên Vercel

1. Triển khai backend Python trước trên host có HTTPS và bộ nhớ lưu bền. Start command tại gốc: `python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT` (host cần đặt `PORT`). Cài `backend/requirements.txt`.
2. Backend: `APP_ENV=production`, `AUTH_SECRET` đủ dài, `FRONTEND_ORIGINS` đúng domain, khóa Gemini riêng. Nếu SQLite, mount ổ bền và đặt `APP_DATA_DIR` vào ổ đó. Giữ một backend process khi demo SQLite nhỏ.
3. Vercel: import repo, **Root Directory = frontend**, framework Vite, build `npm run build`, output `dist`.
4. Đặt `VITE_API_URL=https://DOMAIN-BACKEND` ở Vercel. Biến `VITE_` công khai trong JS: chỉ đặt URL, tuyệt đối không đặt khóa Gemini/secret ở đây. Redeploy khi đổi URL.
5. `frontend/vercel.json` hỗ trợ trang frontend. `/api` phải gọi backend qua `VITE_API_URL`; Vite dev proxy chỉ tồn tại lúc chạy local.
6. Dùng HTTPS cả hai phía. Kiểm tra CORS từ domain chính thức. Chỉ bật `ALLOW_VERCEL_PREVIEWS=1` nếu thực sự cần cho preview.

Không dùng filesystem tạm của Vercel để lưu SQLite/ảnh/tài khoản lâu dài. Cấu hình này đưa frontend lên Vercel, backend và dữ liệu đặt ở host bền riêng. Có thể đổi sang PostgreSQL; ảnh vẫn cần ổ bền hoặc tích hợp object storage trước khi bỏ ổ cục bộ. Chưa có dịch vụ nào tự được triển khai chỉ nhờ thêm các file cấu hình này.

## 7. Kiểm tra sau cấu hình

1. Mở backend `/api/health`: HTTP 200. Mở frontend local `http://127.0.0.1:5173`.
2. Đăng ký bằng tên đăng nhập, mật khẩu và xác nhận; thử trùng tên/sai mật khẩu.
3. Nhập mục tiêu hợp lệ, tính thử, lưu, chuyển Ăn uống kiểm tra đủ bốn chỉ số.
4. Thử tải ảnh nếu đã có khóa Gemini. AI lỗi không được làm mất mục tiêu/nhật ký đã lưu.
5. Đăng xuất, tải lại trang: không còn vào tài khoản. Đăng nhập lại: dữ liệu còn.
6. Thử hai tài khoản và hai kích thước màn hình. Khởi động lại backend rồi kiểm tra dữ liệu cũ.

```bash
python -m pytest backend/tests -q
python -m ruff check backend
python -m ruff format --check backend
cd frontend
npm run format:check
npm run build
```

## 8. Lỗi thường gặp

- `npm: command not found`: chưa cài Node hoặc terminal chưa nhận PATH. Mở lại terminal và kiểm tra Node.
- `requirements-dev.txt not found`: đang đứng sai thư mục; quay về gốc repo.
- Frontend 500/proxy `ECONNREFUSED`: kiểm tra backend đang chạy đúng port trước; xem traceback terminal backend nếu chính API trả 500.
- 401 sau cập nhật: đăng nhập lại. Nếu cứ mất phiên sau mỗi restart, kiểm tra khóa ký và thư mục dữ liệu có giữ bền không.
- 422: đọc thông báo nhập liệu; cân nặng tăng/giảm phải khớp mục tiêu và ngày hoàn thành phải sau hôm nay.
- CORS hoặc HTTPS mixed content: sửa đúng URL frontend/backend và redeploy frontend.
- Có hai database cũ: chọn file đang chứa tài khoản thực, đặt đường dẫn tuyệt đối. Không xóa một file theo phỏng đoán.

Tài liệu nền tảng: [Vercel cho Vite](https://vercel.com/docs/frameworks/frontend/vite), [biến môi trường framework](https://vercel.com/docs/environment-variables/framework-environment-variables), [chạy FastAPI](https://fastapi.tiangolo.com/deployment/manually/).
