# Đánh giá nhận diện AI bằng bộ ảnh có nhãn

Công cụ chạy thật qua `app.ai.scan_image`, cùng catalog CSV và luồng kiểm tra/sửa tiếng Việt của ứng dụng. Lưu văn bản Gemini trả về ở từng lượt gọi trước khi kiểm tra, kết quả cuối của pipeline, lỗi, thời gian và số liệu tổng hợp. Không giả lập trong lệnh `run`.

## Chuẩn bị dữ liệu trước khi gọi AI

Đề xuất cho đợt demo: 30 ảnh thực tế, 10 ảnh dev và 20 ảnh test. Đây là quy mô đề xuất cho bài tập, không bảo đảm đại diện cho mọi món Việt. Bao gồm ảnh một món, nhiều món, mờ/che khuất, món ngoài CSV và ảnh không có đồ ăn. Lưu bộ ảnh ngoài Git, ví dụ `.local/evaluation/dataset/images/`.

1. Copy `labels.template.json` thành `.local/evaluation/dataset/labels.json`.
2. Hai người xem ảnh và duyệt tên món trước khi chạy AI; điền hai tên khác nhau vào `reviewed_by`. Người gán nhãn không xem kết quả AI trên tập test để chọn tên tương đương.
3. Mỗi món là một mảng trong `expected`. Ví dụ `[["Phở bò"], ["Cơm tấm", "Cơm tấm sườn"]]` là hai món; các tên trong một mảng phải là tên tương đương được duyệt trước. Không đưa những món khác nhau vào một nhóm tên để tăng điểm. Không có đồ ăn dùng `[]`.
4. `group_id` gom cùng bữa ăn, cùng lượt chụp hoặc ảnh cắt/chỉnh từ cùng ảnh gốc. Tất cả ảnh cùng nhóm phải ở một split. Công cụ chặn ảnh trùng byte và nhóm trùng giữa các split; nhóm vẫn phải tự kiểm tra ảnh gần giống, vì công cụ không tự phát hiện mọi ảnh chụp lại.
5. Ghi nguồn ảnh và quyền sử dụng trong `source`. Chỉ dùng ảnh nhóm được phép xử lý. Không tự suy đoán nhãn với ảnh không đủ thông tin; rà soát trước khi khóa. Bộ template cố ý chưa hợp lệ khi chưa có ảnh và người duyệt.

Giữ tập test ngoài các lần chỉnh prompt. Có thể điều chỉnh trên dev, sau đó chốt prompt/model/catalog và chạy test. Nếu sửa prompt sau khi xem test, phải báo rõ vòng thử đó và chuẩn bị tập test mới cho đánh giá cuối.

## Khóa bộ ảnh

Chạy tại gốc repo sau khi cài `backend/requirements-dev.txt`:

```bash
python -m backend.evaluation freeze .local/evaluation/dataset/labels.json --root .local/evaluation/dataset --output .local/evaluation/dataset.lock.json
```

Lệnh kiểm tra file, dung lượng, định dạng, người duyệt, split, nhóm ảnh và lưu SHA-256. File lock không được ghi đè. Lưu riêng bản lock đã duyệt; ghi link hoặc hash vào báo cáo trước khi chạy. Muốn đổi nhãn phải tạo phiên bản mới, giải thích lý do, không sửa lock của lần đã chạy.

## Chạy Gemini thật

Cấu hình khóa riêng trong `backend/.env` hoặc truyền `--env-file` trỏ tới file cấu hình riêng. Không copy khóa sang manifest hoặc đưa `.env` vào Git. Model lấy từ `GEMINI_MODEL` của backend; dùng model mà project được phép truy cập.

```bash
python -m backend.evaluation run .local/evaluation/dataset.lock.json --root .local/evaluation/dataset --split dev --output .local/evaluation/dev-run-01
python -m backend.evaluation run .local/evaluation/dataset.lock.json --root .local/evaluation/dataset --split test --output .local/evaluation/test-run-01
```

Mỗi thư mục chạy phải là thư mục mới. Công cụ kiểm tra ảnh chưa đổi sau khi khóa, rồi chạy tuần tự. Lượt retry/fallback và sửa tiếng Việt của ứng dụng vẫn được lưu trong `provider_calls`; không tự chạy lại từng ảnh chỉ vì nhận diện sai. Lỗi quota/xác thực làm dừng sớm; summary ghi `complete=false` nếu chưa thử đủ ảnh. Giữ lần lỗi, sửa cấu hình hoặc chờ dịch vụ, rồi tạo lần chạy mới được ghi rõ trong báo cáo.

## Các file minh chứng

- `dataset.lock.json`: nhãn và hash ảnh đã dùng.
- `run.json`: thời điểm, commit, trạng thái cây mã, hash mã AI/công cụ/catalog, SDK, model yêu cầu và phiên bản prompt.
- `response-XXXX.json`: `provider_calls` chứa `text` nguyên văn trả từ SDK, model version nếu SDK cung cấp, loại/mã lỗi; `result` là JSON cuối pipeline, chưa có người sửa hoặc xác nhận món.
- `results.jsonl`: ghi ngay từng ảnh để giữ được phần đã chạy khi bị ngắt.
- `summary.json`: toàn bộ ảnh đã thử, số ảnh dự kiến, lỗi, điểm và nhóm tình huống.
- `checksums.json`: hash các file kết quả; dùng đối chiếu cùng bản lưu gốc. Hash không thay thế việc quản lý quyền sửa file; giữ nguyên bản và lưu bản sao riêng.

Không lưu nội dung exception có thể chứa URL/credential. Ảnh, nhãn thật và phản hồi được giữ trong `.local/` mặc định; không tự đưa lên repo công khai. Nếu nhóm muốn công bố dữ liệu, cần rà soát nguồn và quyền sử dụng trước.

## Cách đọc điểm

Tên được chuẩn hóa hoa/thường, khoảng trắng, dấu câu và Unicode, vẫn giữ dấu tiếng Việt. Tên không dấu chỉ được chấp nhận nếu nhóm đã ghi alias hợp lệ trước khi khóa. Không dùng AI khác hoặc khớp mờ để tự chấm cho đẹp số liệu.

- Top 1: so tên đầu tiên của từng món với nhãn đã duyệt.
- Top 3: một món được coi khớp nếu một trong ba tên đầu khớp alias đã duyệt. Đây là độ phủ tên gợi ý của pipeline, không phải xác suất tự tin.
- Ghép một-một: một dự đoán không được tính đúng cho hai món thật. Món thừa là FP, món thiếu là FN.
- Precision = TP/(TP+FP); recall = TP/(TP+FN); F1 = 2TP/(2TP+FP+FN). Không có mẫu số thì ghi null, không biến thành 100%.
- Exact image: đủ và đúng mọi món, không có món thừa; ảnh không đồ ăn phải trả danh sách rỗng thành công. Lỗi API không được tính là từ chối ảnh đúng.
- `exact_rate` tính trên ảnh đã thử, bao gồm ảnh lỗi. `top1_exact_rate_planned` và `top3_exact_rate_planned` tính trên toàn bộ số ảnh dự kiến, để không che việc dừng sớm.
- Với lỗi API trên ảnh có món, các món thật vẫn được tính là FN. Luôn công bố số lỗi và tỷ lệ chạy đủ, kèm điểm theo nhóm tình huống.

Kết quả này chỉ đánh giá tên món, không xác minh số gram, kcal hay chất dinh dưỡng từ ảnh. Không trộn điểm dev, smoke và test thành một accuracy.

## Chạy thử công cụ bằng ảnh demo

Hai ảnh tổng hợp có sẵn chỉ thuộc split `smoke`:

```bash
python -m backend.evaluation freeze evaluation/smoke.json --root . --output .local/evaluation/smoke.lock.json
python -m backend.evaluation run .local/evaluation/smoke.lock.json --root . --split smoke --output .local/evaluation/smoke-run-01
```

Đây vẫn gọi API thật và có thể dùng quota, nhưng không được dùng kết quả hai ảnh để kết luận độ chính xác trên ảnh người dùng thật. Một số món có nhiều thành phần phụ; thống nhất nhãn ở cấp món hoặc thành phần trước khi khóa để tránh đánh giá không nhất quán.
