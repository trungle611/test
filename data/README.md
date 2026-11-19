# Danh mục thực phẩm và món ăn

| File | Nội dung | Cơ sở dinh dưỡng |
| --- | --- | --- |
| `foods_team_unverified.csv` | 329 thực phẩm | Theo 100 g |
| `serving_items_team_unverified.csv` | 99 món ăn và 2 đồ uống | Theo khẩu phần ghi trong từng dòng |

CSV dùng UTF-8, dấu phẩy phân tách cột và dấu chấm cho phần thập phân. ID là chuỗi như `F_0001`, phải giữ nguyên và duy nhất trên cả hai file. Danh mục có tổng cộng 430 ID.

## Trường dùng chung

| Trường | Ý nghĩa |
| --- | --- |
| `id`, `name` | ID ổn định và tên tiếng Việt |
| `source_type` | Loại nguồn dữ liệu |
| `source_reference` | Thông tin nguồn và giới hạn đối chiếu |
| `data_version` | Phiên bản dữ liệu |
| `is_verified` | `true` hoặc `false`, trạng thái kiểm chứng |
| `avoid_tags` | Thành phần cần tránh, phân tách bằng dấu `;` nếu có nhiều giá trị |
| `aliases` | Tên gọi khác, phân tách bằng dấu `;` |

`avoid_tags` trống có nghĩa là chưa có nhãn được ghi, không xác nhận món không chứa thành phần cần tránh.

## Thực phẩm theo 100 g

`kcal_100g` là năng lượng tính bằng kcal. `protein_100g`, `carb_100g` và `fat_100g` tính bằng g. Tất cả là giá trị trên 100 g thực phẩm.

Với lượng ăn `grams`, tính từng chỉ số:

```text
dinh_duong = gia_tri_100g × grams / 100
```

## Món ăn và đồ uống theo khẩu phần

| Trường | Ý nghĩa |
| --- | --- |
| `item_type` | `dish` hoặc `beverage` |
| `basis_label` | Mô tả khẩu phần, ví dụ `1 tô (500g)` |
| `basis_amount`, `basis_unit` | Số lượng và đơn vị làm cơ sở tính |
| `reference_mass_g` | Khối lượng tham chiếu của khẩu phần, nếu có |
| `reference_volume_ml` | Thể tích tham chiếu của khẩu phần, nếu có |
| `kcal_basis` | Năng lượng của khẩu phần cơ sở, tính bằng kcal |
| `protein_basis`, `carb_basis`, `fat_basis` | Chất đạm, carbohydrate và chất béo của khẩu phần cơ sở, tính bằng g |

Khi lượng ăn dùng cùng `basis_unit`:

```text
dinh_duong = gia_tri_basis × so_luong_an / basis_amount
```

Ví dụ Phở gà có cơ sở 1 tô (500 g), 400 kcal. Ăn 2 tô được tính là 800 kcal theo dữ liệu này. Đây là giá trị ước lượng theo khẩu phần, chưa phải số liệu đo riêng từng tô.

Đơn vị đếm như tô, quả, đĩa, chén hoặc phần dùng số nguyên dương. Đơn vị g và ml có thể dùng số thập phân. Chỉ đổi sang g hoặc ml khi có thông tin tham chiếu tương ứng, không tự coi mọi đơn vị là gram.

## Nguồn và trạng thái tích hợp

Hai CSV được giữ nguyên từ [BTL-AI tại commit 46f262f](https://github.com/trungle611/BTL-AI/tree/46f262f62473ad77d742e1b60d39ca535fe09efb/data). Các cột nguồn ghi tệp nhóm tổng hợp và ngày nhận. Toàn bộ bản ghi hiện là `is_verified=false` vì chưa có tài liệu nguồn để đối chiếu độc lập.

Đã kiểm tra cấu trúc cột, trường bắt buộc, ID trùng trên cả hai file, giá trị dinh dưỡng hữu hạn/không âm, đơn vị và định lượng khẩu phần. Kiểm tra này xác nhận định dạng phù hợp để tích hợp, không xác nhận độ chính xác dinh dưỡng ngoài thực tế.

Đợt này chỉ bổ sung dữ liệu. Backend hiện vẫn là khung và chưa nạp CSV vào database. Không lưu database hoặc ảnh người dùng trong thư mục này.
