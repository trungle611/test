# Báo cáo đánh giá nhận diện bằng ảnh có nhãn

Chỉ điền bằng file kết quả thực tế sau khi nhóm đã duyệt dữ liệu.

## Thông tin lần chạy

- Người chạy, người duyệt nhãn và ngày giờ:
- Repo/commit UETCS, phiên bản prompt, model yêu cầu và model version thực tế:
- Hash manifest đã khóa và số ảnh dev/test:
- Nguồn ảnh, quyền sử dụng, nhóm tình huống và cách tránh ảnh gần trùng giữa các split:
- Các lần chỉnh prompt trên dev, ngày chốt cấu hình:
- Tên thư mục chạy test cuối; đã chạy đủ hay dừng sớm:

## Kết quả

| Chỉ số | Top 1 | Top 3 |
| --- | --- | --- |
| TP / FP / FN | Điền từ summary | Điền từ summary |
| Precision / recall / F1 | Điền từ summary | Điền từ summary |
| Ảnh đúng toàn bộ / ảnh dự kiến | Điền từ summary | Điền từ summary |

Ghi thêm số ảnh đã thử/tổng ảnh, số lỗi theo nguyên nhân, kết quả ảnh không có đồ ăn và kết quả từng category. Không điền số của smoke hoặc dev vào kết quả test cuối.

## Phân tích lỗi và giới hạn

Chọn cả ví dụ đúng và sai, ghi case_id, nhãn khóa, tên Gemini trả, loại lỗi và nhận xét. Không sửa file response/nhãn cũ sau khi xem điểm. Nếu dịch vụ lỗi hoặc kết quả chưa đạt, báo đúng trạng thái; không chỉ chọn lần chạy tốt nhất mà bỏ các lần còn lại.

## Minh chứng đính kèm

Đính kèm manifest đã khóa, run.json, results.jsonl, summary.json, checksums.json và các phản hồi tương ứng. Chụp terminal lệnh chạy có thời gian, ảnh minh họa được phép chia sẻ và link commit/PR UETCS của các phần đã tích hợp.

Nếu chưa có tập test thật hoặc chưa chạy đủ, ghi rõ công việc còn lại và chưa đánh dấu hoàn tất task đánh giá cuối.
