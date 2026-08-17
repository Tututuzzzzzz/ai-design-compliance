# Bộ test design

**Ảnh design không được commit vào repo** — phần lớn ảnh dùng để test BLOCKED chứa tài sản có
bản quyền của bên thứ ba, commit chúng lên chính là hành vi mà agent này đi phát hiện.

## A. Dùng bộ mẫu của ban tổ chức (khuyến nghị)

Sheet mẫu có sẵn expected verdict, niche, sub-niche, style, motifs và loại vi phạm cho 30
design — đúng là rubric chấm điểm. Cơ cấu: **20 BLOCKED / 10 SAFE**, không có RISKY.

Loại vi phạm trong sheet được map sang 7 nhóm rủi ro của agent:

| Sheet | Agent (chấp nhận bất kỳ cái nào) |
|---|---|
| Character | `copyrighted_character` |
| Logo | `brand_logo` |
| Brand Name | `brand_logo` · `trademarked_phrase` |
| Text/Band Name | `trademarked_phrase` · `brand_logo` · `copyrighted_character` |
| Celebrity Likeness | `public_figure` |
| Artwork/Copyright | `copyrighted_artwork` · `copyrighted_character` |

Mỗi nhãn map sang một **tập** chứ không phải một category duy nhất, vì từ vựng của BTC thô
hơn 7 nhóm của agent. Tên ban nhạc trên áo vừa là wordmark đã đăng ký, vừa là brand, lại
thường đi kèm logo hoặc linh vật — ép về đúng `trademarked_phrase` sẽ chấm một phát hiện
đúng thành sai chỉ vì xếp khác mục. Chỉ riêng việc sửa mapping này đã đưa category từ 50%
lên 80%.

**Một lệnh là xong:**

```bash
docker compose exec api python -m data.fetch_sheet_designs \
  1cYEd83VKG0B-6zg8oYRqeAhx-JscnILOyj3J5uJ7GXo --gid 256492005
docker compose exec api python -m data.evaluate --manifest /srv/var/designs/manifest.csv
```

Ảnh chèn đè lên ô không click phải lưu được, không có trong export CSV/XLSX, và Sheets API
đòi OAuth. Bản export **web page (zip)** thì có — dưới dạng thẻ `<img>` trỏ tới URL
googleusercontent công khai. Script đọc đúng chỗ đó và cắt hậu tố kích thước để lấy bản gốc
310px thay vì thumbnail 108px.

Nếu bạn đã có sẵn ảnh trong một thư mục (đặt tên theo số dòng: `1.png`, `2.png`, …), dùng
`import_sheet` với file CSV export thay vì tải lại:

```bash
docker compose exec api python -m data.import_sheet /srv/var/sheet.csv --designs /srv/var/designs
```

`import_sheet` báo rõ dòng nào chưa có ảnh khớp, nên bạn làm dần từng đợt cũng được.

## B. Tự dựng bộ test

1. Tạo `samples/designs/` và bỏ 10 file design vào đó.
2. Gợi ý cơ cấu để phủ hết các nhánh của verdict engine:

| # | Kỳ vọng | Loại design | Nhóm rủi ro nhắm tới |
|---|---|---|---|
| 1 | SAFE | Chữ hand-lettered niche dog mom | — |
| 2 | SAFE | Hoa văn Giáng sinh vẽ tay | — |
| 3 | SAFE | Typo nghề nghiệp (nurse / teacher) | — |
| 4 | RISKY | Headline dùng font script thương mại | `licensed_font` |
| 5 | RISKY | Cụm từ phổ biến có thể đã đăng ký | `trademarked_phrase` |
| 6 | RISKY | Khuôn mặt cách điệu giống người nổi tiếng | `public_figure` |
| 7 | BLOCKED | Nhân vật hoạt hình có bản quyền | `copyrighted_character` |
| 8 | BLOCKED | Logo thương hiệu / trade dress | `brand_logo` |
| 9 | BLOCKED | Slogan đã đăng ký (vd. "Just Do It") | `trademarked_phrase` |
| 10 | BLOCKED | Vũ khí / nội dung bị cấm trên Amazon Merch | `prohibited_content` |

3. Chạy cả 10 qua agent bằng **cả ba cách nhập input** để quay demo:

```bash
# Cách 1 — upload nhiều file
curl -X POST http://localhost:8000/api/analyze/upload \
  $(for f in samples/designs/*; do echo -n "-F files=@$f "; done) \
  -F 'metadata={"markets":["US"],"platforms":["etsy","amazon_merch"]}'

# Cách 2 — CSV (đính kèm luôn file mà CSV tham chiếu)
curl -X POST http://localhost:8000/api/analyze/csv \
  -F "file=@samples/batch.csv" \
  $(for f in samples/designs/*; do echo -n "-F attachments=@$f "; done) \
  -F 'metadata={"markets":["US"],"platforms":["etsy"]}'

# Cách 3 — link
curl -X POST http://localhost:8000/api/analyze/links \
  -H 'Content-Type: application/json' \
  -d '{"urls":["https://.../design1.png","https://.../design2.png"],
       "metadata":{"markets":["US"],"platforms":["etsy"]}}'
```

4. Xuất báo cáo kết quả vào `samples/output/`:

```bash
JOB=<job_id>
curl -o samples/output/report.xlsx "http://localhost:8000/api/jobs/$JOB/export.xlsx"
curl -o samples/output/report.csv  "http://localhost:8000/api/jobs/$JOB/export.csv"
```

## Kiểm tra không cần API key

`backend/data/smoke_test.py` chạy ba case tổng hợp (SAFE / RISKY / BLOCKED) qua toàn bộ
pipeline với vision provider giả lập — dùng để xác nhận verdict engine, policy layer,
annotation và export hoạt động mà không tốn quota:

```bash
cd backend && python -m data.smoke_test
```
