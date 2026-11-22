# HBTNFIT

HBTNFIT dùng React + Vite, FastAPI và SQLite. Bản này đã nối luồng ăn uống, tài khoản và tập luyện. Dữ liệu cá nhân được giới hạn theo tài khoản đăng nhập. Trang cá nhân và gợi ý mục tiêu vẫn là phần tích hợp tiếp theo; các API hồ sơ hiện có đã được bảo vệ theo tài khoản.

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

Mở [frontend](http://127.0.0.1:5173), đăng ký một tài khoản rồi đăng nhập để thử ăn uống và tập luyện. Tài liệu API ở [Swagger](http://127.0.0.1:8000/docs). Hai cổng 8000 và 5173 cần còn trống.

Để nhận diện thật, điền `GEMINI_API_KEY` và model được phép sử dụng trong `backend/.env`. Có thể điền `GEMINI_FALLBACK_API_KEY` nếu có khóa dự phòng. Không có key vẫn chạy được ứng dụng và kiểm thử bằng giả lập; giao diện sẽ báo lỗi nhận diện và cho nhập món thủ công. Không có chế độ giả lập Gemini được bật sẵn trong ứng dụng.

SQLite tạo `backend/hbtnfit.db` khi chạy bằng lệnh trên. Ảnh lịch sử lưu trong `backend/uploads/scans`. Mọi API dữ liệu cá nhân yêu cầu Bearer token hợp lệ và tài khoản còn tồn tại. Backend lấy `user_id` từ token đã xác minh, bỏ qua `X-Visitor-Id`; frontend không được chỉ định chủ sở hữu qua payload. Không commit `.env`, database, ảnh người dùng hoặc thư mục runtime.

## Database mới và nâng cấp database cũ

Không copy database hoặc `.env` giữa các thành viên. Mỗi máy tạo DB riêng, dùng cùng CSV trong repo.

- Database mới: chạy backend lần đầu sẽ tự tạo bảng và nạp CSV. Có thể thực hiện riêng bằng `python -m app.init_db` từ thư mục `backend` sau khi cấu hình `.env`.
- Để tạo DB mới mà vẫn giữ bản cũ: tắt backend, đặt `DATABASE_URL=sqlite:///./hbtnfit_moi.db` trong `backend/.env`, rồi chạy lệnh khởi tạo. Không xóa file DB cũ.
- Trước khi nâng cấp DB có dữ liệu: tắt backend, sao lưu file `.db` và thư mục `backend/uploads/scans`. Nếu SQLite còn file `-wal`/`-shm`, cần đóng hết kết nối trước khi sao chép, hoặc dùng công cụ backup SQLite. Sao lưu cả `.runtime/auth-secret` nếu đang dùng khóa local tự sinh.
- Khi khởi động bản mới, migration tự đổi cột `visitor_id` thành `user_id`, bổ sung cột sở hữu còn thiếu và index. Chạy lại không tạo trùng bảng hoặc xóa bản ghi.
- Dữ liệu phiên demo cũ vẫn được giữ, nhưng không tự gán cho tài khoản mới. Chỉ token hợp lệ của một tài khoản có đúng ID mới truy cập được dữ liệu. Lịch tập cũ chưa có chủ sở hữu được giữ trong DB nhưng không đưa vào lịch của tài khoản mới.
- Model mới dùng khóa ngoại tới `users` và index theo `user_id`. Với DB SQLite cũ, migration giữ cấu trúc và ràng buộc sẵn có; không dựng lại toàn bộ bảng để bổ sung mọi khóa ngoại. Quyền truy cập vẫn được kiểm tra ở API.
- DB mới tạo unique index cho hồ sơ, gợi ý và giáo án đang chọn theo tài khoản. Nếu DB cũ có nhiều hồ sơ cùng một ID, cần rà soát bản sao trước khi nâng cấp; không tự xóa bản ghi để vượt qua lỗi ràng buộc.
- `username` đang ánh xạ vào cột SQL `users.email` để đọc được DB của bản trước. Giao diện/API chỉ sử dụng tên đăng nhập, không yêu cầu email.
- Không lưu ảnh nhị phân vào SQLite: `scan_history` chỉ giữ khóa đường dẫn, metadata và kết quả; API xem ảnh luôn kiểm tra tài khoản sở hữu.

SQLite cần phiên bản 3.25+ để đổi tên cột. Quy trình demo được kiểm thử bằng SQLite; cần kiểm tra riêng migration trước khi triển khai PostgreSQL với dữ liệu thật.

## Tài khoản và phiên đăng nhập

Đăng ký bằng tên đăng nhập, mật khẩu và xác nhận mật khẩu. Mật khẩu được băm PBKDF2 với salt; token được ký ở backend. Đăng xuất sẽ xóa token và hủy state giao diện của tài khoản cũ. Token sai, hết hạn hoặc thuộc tài khoản không tồn tại bị từ chối với mã 401. Token hiện có hạn 7 ngày; đăng xuất ở trình duyệt chưa thu hồi token trên các thiết bị khác.

Khi chạy local, nếu `AUTH_SECRET` để trống, ứng dụng tự sinh khóa ngẫu nhiên và lưu trong `backend/.runtime/auth-secret` (đã được Git bỏ qua). Không dùng khóa ký cố định công khai. Khi triển khai, cấu hình `AUTH_SECRET` riêng ít nhất 32 ký tự; các tiến trình backend phải dùng cùng khóa. Không đưa khóa thật, DB hoặc ảnh người dùng lên Git.

## Tập luyện

1. Vào **Tập luyện**, chọn một trong bốn giáo án: PPL hoặc Upper/Lower, theo nhóm tăng cơ hoặc giảm cân.
2. Mở **Xem bài tập từng buổi** để xem tên bài cụ thể, nhóm cơ, số hiệp và số lần. Buổi tập hiển thị thêm hướng dẫn động tác và thời gian nghỉ.
3. Chọn **Có đi tập** hoặc **Nghỉ hôm nay**. Lịch tháng hiển thị xanh cho ngày đi tập/hoàn thành, đỏ cho ngày đã chọn nghỉ; ngày chưa ghi nhận giữ màu xám.
4. Bắt đầu từng bài rồi đánh dấu hoàn thành. Chỉ sau khi hoàn thành tất cả bài, lần đi tập sau mới chuyển sang buổi kế tiếp. Ngày nghỉ không đẩy lịch sang buổi mới.
5. Trạng thái bài đã làm được giữ khi tiếp tục cùng buổi qua ngày khác. Chu kỳ mới không dùng lại trạng thái của chu kỳ trước. Bản này cho hoàn thành tối đa một buổi mỗi giáo án trong một ngày.
6. Đổi giáo án không xóa lịch đi tập. Lịch tháng tổng hợp tất cả giáo án của cùng tài khoản; tiến độ từng giáo án được giữ riêng.

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
  app/auth_routes.py   đăng ký, đăng nhập và thông tin phiên
  app/migrations.py    nâng cấp quyền sở hữu dữ liệu cũ
  app/init_db.py       lệnh tạo/nâng cấp DB và nạp CSV
  app/workout_routes.py giáo án, tiến độ và lịch đi tập
  app/workout_plans.py tên bài, nhóm cơ và hướng dẫn
  app/ai.py            gọi Gemini và xử lý lỗi
  app/scan_service.py  kiểm tra ảnh, chuẩn hóa món và lưu ảnh lịch sử
  app/goals.py         tính mục tiêu và đánh giá lịch sử dinh dưỡng
  tests/              ăn uống, lỗi AI, hai tài khoản, migration và tập luyện
frontend/
  src/App.jsx          phiên đăng nhập, bố cục và điều hướng
  src/AuthPage.jsx     biểu mẫu tài khoản
  src/WorkoutPlans.jsx chọn và xem giáo án
  src/WorkoutPanel.jsx bài tập và lịch xanh/đỏ
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
