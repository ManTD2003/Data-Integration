# Quy ước gán nhãn skill extraction

Mỗi task tương ứng với một tin tuyển dụng. Nhãn của task là tập canonical skill
được nhắc trực tiếp trong `title`, `requirements_raw` hoặc `description`. Không
xem source tags và không xem prediction của hệ thống khi gán nhãn.

## Nhãn được chọn

- Ngôn ngữ lập trình, framework, database, platform, công cụ và phương pháp
  chuyên môn được yêu cầu hoặc dùng để thực hiện công việc.
- Ngoại ngữ và soft skill khi văn bản nêu trực tiếp.
- Kỹ năng được ghi là optional, preferred hoặc "là một lợi thế".
- Kỹ năng xuất hiện bằng alias được gán về canonical skill tương ứng. Một
  canonical skill chỉ chọn một lần dù xuất hiện nhiều lần.

Tên chức danh không tự tạo thêm nhãn. `Data Engineer` không kéo theo SQL hoặc
Python nếu văn bản không nhắc hai kỹ năng đó. Nếu chính title chứa tên kỹ năng,
chẳng hạn `Python Developer`, Python vẫn được chọn vì nó xuất hiện trực tiếp.

Không chọn tên doanh nghiệp, lĩnh vực kinh doanh, phúc lợi, bằng cấp hoặc nhiệm
vụ chung khi chúng không biểu thị một kỹ năng. Một từ trùng alias nhưng mang
nghĩa khác trong context cũng không được chọn.

## Kỹ năng OOV

Nếu kỹ năng được nhắc rõ nhưng không có trong danh sách canonical skill, ghi
canonical name của nó vào ô OOV, mỗi dòng một mục. Không chọn một kỹ năng gần
nghĩa chỉ để tránh OOV. Khi tính metric, OOV thuộc gold và trở thành false
negative nếu hệ thống không trích được.

## Development và test

Gán hết development split trước. Có thể dùng lỗi trên split này để sửa rule,
threshold hoặc dictionary. Sau khi chốt hệ thống, chạy:

```bash
./run.sh annotate freeze
```

Từ thời điểm đó không sửa dictionary hoặc extractor cho tới khi gán xong test
split và chạy `score`. Nếu phát hiện lỗi trong quy ước gán nhãn, sửa nhãn nhưng
ghi lý do vào ô ghi chú; không điều chỉnh hệ thống theo kết quả test.
