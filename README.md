# 🏆 ĐỀ THI HACKATHON — AI Design Compliance Checker

> **Detect niche & kiểm tra vi phạm bản quyền từ file design**
>
> **Đơn vị tổ chức:** AI Hackathon
> **Mã dự án:** `AI_Design_Compliance_Checker_Hackathon`

---

## 1. Bối cảnh

Print-on-Demand (POD) và cross-border sellers upload hàng ngàn design mỗi ngày lên Etsy, Amazon Merch, Shopify, TikTok Shop… Mỗi design bị reject vì vi phạm trademark/copyright đồng nghĩa với:

- Mất phí upload, mất slot listing
- Bị flag tài khoản, nặng thì suspend cả store
- Mất công thiết kế lại từ đầu

Hiện tại việc check compliance vẫn phần lớn làm **thủ công** — designer/QA phải Google tên nhân vật, tra USPTO, kiểm tra logo hãng, đối chiếu với danh sách blacklist. Cách này **chậm, dễ sót, không scale**.

---

## 2. Đề bài

Xây dựng một **AI Agent** nhận đầu vào là design (đơn lẻ hoặc hàng loạt) và tự động:

1. **Phát hiện niche/chủ đề** của design
2. **Kiểm tra rủi ro vi phạm trademark & copyright**
3. Đưa ra **verdict** rõ ràng: `SAFE` / `RISKY` / `BLOCKED`

---

## 3. Đầu vào (Input)

Agent phải hỗ trợ nhiều cách nhập input, tối thiểu:

| Cách nhập | Mô tả |
| --- | --- |
| **Upload file** | Upload trực tiếp 1 hoặc nhiều file design (PNG, JPG, PSD, AI, PDF…) |
| **Import CSV** | Upload CSV chứa danh sách design (tên file, link, hoặc metadata) — batch xử lý hàng loạt |
| **Import link** | Nhập URL (Google Drive, Dropbox, S3, direct image URL, marketplace listing…) — agent tự fetch |
| *(Bonus)* **Import folder** | Kết nối Google Drive / Dropbox folder, agent scan toàn bộ design bên trong |

### Metadata tùy chọn kèm theo mỗi design

- **Thị trường target:** US, EU, JP… (mỗi thị trường có luật khác nhau)
- **Platform bán:** Etsy, Amazon Merch, TikTok Shop, Shopify… (mỗi nền tảng có policy riêng)

---

## 4. Đầu ra (Output)

Agent phải trả về báo cáo compliance cho từng design, gồm:

### 4.1. Niche Detection

- **Niche chính:** Christmas, Dog Lovers, Nurse, Fishing, Halloween, Anime…
- **Sub-niche / audience cụ thể:** Golden Retriever mom, ICU Nurse…
- **Style:** vintage, minimalist, cartoon, retro 90s…
- **Chủ đề phụ / motif:** skulls, flowers, guns, religious symbols…

### 4.2. Copyright & Trademark Check

Agent phải phát hiện được các nhóm rủi ro sau:

| Nhóm rủi ro | Ví dụ cần detect |
| --- | --- |
| **Nhân vật có bản quyền** | Mickey Mouse, Pikachu, Batman, anime characters, cartoon characters |
| **Logo / Brand** | Nike swoosh, Apple logo, Louis Vuitton monogram, sports team logos |
| **Câu chữ đã đăng ký trademark** | "Just Do It", "I ❤ NY", slogan phổ biến đã bị đăng ký |
| **Người nổi tiếng** | Ảnh/khuôn mặt/tên celebrity, athlete, chính trị gia |
| **Tác phẩm nghệ thuật có bản quyền** | Ảnh Disney, Marvel, Pixar, tranh nổi tiếng còn bản quyền |
| **Font có bản quyền thương mại** | Font cần license mà bị dùng miễn phí |
| **Nội dung nhạy cảm / bị cấm** | Vũ khí, ma túy, nội dung phân biệt, nội dung 18+ |

### 4.3. Verdict cuối cùng

Với mỗi design, agent trả về:

- 🟢 **SAFE** — không phát hiện rủi ro rõ ràng, có thể upload
- 🟡 **RISKY** — có yếu tố cần review thủ công (kèm lý do cụ thể)
- 🔴 **BLOCKED** — phát hiện vi phạm rõ ràng, không nên upload

Kèm theo:

- **Confidence score** cho verdict (0–100%)
- **Reasoning chi tiết:** vùng nào trên design có vấn đề, vi phạm cái gì, gợi ý cách sửa

### 4.4. Batch Report

Khi input là CSV / folder / nhiều file:

- Trả về **báo cáo tổng hợp** (dashboard hoặc file CSV/Excel export)
- Cho phép **filter** theo verdict, niche, loại vi phạm
- Có **thống kê nhanh:** bao nhiêu SAFE / RISKY / BLOCKED

📄 **File mẫu:** https://docs.google.com/spreadsheets/d/1cYEd83VKG0B-6zg8oYRqeAhx-JscnILOyj3J5uJ7GXo/edit?usp=sharing

---

## 5. Yêu cầu chức năng

> **Triết lý:** Ban tổ chức **không quy định cách làm**. Ban giám khảo chỉ chấm trên **độ chính xác của verdict** và **chất lượng báo cáo**.

Agent cần giải quyết được:

- **Đọc và hiểu design** — bao gồm cả text và hình ảnh trong design
- **OCR text** trong design (nếu có) và check trademark trên text
- **Object/character detection** — nhận diện được nhân vật, logo, brand trong ảnh
- **Cross-reference** với database trademark/copyright thực tế (USPTO, EUIPO, các nguồn public)
- **Highlight vùng vi phạm** trên design (bounding box hoặc mô tả vị trí)
- Xử lý được **nhiều format file** design phổ biến
- **Batch processing** — xử lý nhiều design cùng lúc từ CSV/folder/multi-upload

---

## 6. Ràng buộc tối thiểu

1. Phải hỗ trợ **ít nhất 3 cách nhập input**: upload file, import CSV, import link
2. Phải xử lý được **ít nhất PNG và JPG** (các format khác là bonus)
3. Verdict phải có **reasoning rõ ràng** — không được chỉ trả về "SAFE" mà không giải thích
4. Data trademark/copyright reference phải **real** — không hard-code kết quả cho design mẫu
5. Phải **chạy được trên máy giám khảo**, có **UI** cho người dùng

---

## 7. Công cụ — Tự do lựa chọn

Thí sinh tự do chọn Vision model (GPT-4V, Claude Vision, Gemini, Llava…), OCR engine, trademark database, framework, tech stack.

---

## 8. Output thí sinh phải nộp

1. **Repository GitHub** với source code
2. **README.md**: mô tả giải pháp, kiến trúc, hướng dẫn chạy (≤ 10 phút)
3. **Demo video 3–5 phút** walkthrough sản phẩm (phải demo đủ 3 cách nhập input)
4. **Bộ test 10 design mẫu** đã chạy qua agent, kèm báo cáo output — phải có đủ mix: SAFE, RISKY, BLOCKED
5. **Slide thuyết trình** cho vòng chung kết

---

## 9. Tiêu chí chấm điểm (Tổng: 100 điểm)

| Tiêu chí | Trọng số | Mô tả |
| --- | --- | --- |
| 🎯 **Độ chính xác của verdict** | **40 đ** | Phát hiện đúng vi phạm, không false positive/negative quá cao |
| 🔍 **Độ sâu của compliance check** | **20 đ** | Phát hiện được nhiều loại rủi ro (character, logo, text, celeb, font…) |
| 📊 **Chất lượng báo cáo & niche detection** | **15 đ** | Niche detect chính xác, reasoning rõ ràng, có bounding box/vị trí, có gợi ý sửa |
| ⚡ **Đa dạng input & batch processing** | **10 đ** | Hỗ trợ tốt cả 3 cách nhập input, batch report rõ ràng |
| 💎 **UX & Tính hoàn thiện** | **10 đ** | Giao diện, tốc độ, dễ dùng |
| ✨ **Sáng tạo & Khác biệt** | **5 đ** | Ý tưởng độc đáo, tính năng vượt mong đợi |

### Phương pháp chấm

Ban giám khảo đưa bộ test **15–20 design** (có mix SAFE/RISKY/BLOCKED) do BTC chuẩn bị, agent xử lý **live** theo cả 3 cách nhập input. Chấm trên **tỷ lệ verdict đúng** và **chất lượng reasoning**.

---

## 10. Quy định

1. **KHÔNG** hard-code kết quả cho design mẫu
2. **KHÔNG** dùng data trademark tự bịa — phải reference nguồn thật
3. **Cho phép** dùng mọi Vision API, OCR, database bên thứ ba
4. Vi phạm privacy (leak design của thí sinh khác) → **loại trực tiếp**
