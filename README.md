# AI Design Compliance Agent

Nhận vào design (đơn lẻ hoặc hàng loạt), tự động **phát hiện niche** và **rà soát rủi ro
trademark / copyright / quyền hình ảnh / chính sách nền tảng**, rồi trả verdict rõ ràng:
🟢 **SAFE** · 🟡 **RISKY** · 🔴 **BLOCKED** — kèm confidence score, bounding box vùng vi phạm,
lý do chi tiết và gợi ý sửa.

---

## 1. Chạy trong 5 phút

```bash
git clone <repo-url> && cd ai-design-compliance
cp .env.example .env          # điền MỘT API key (xem bên dưới)
docker compose up --build     # ~4 phút lần đầu
```

Mở **http://localhost:3000**. API docs ở **http://localhost:8000/docs**.

### API key — chọn một

| Provider | Biến môi trường | Lấy key ở đâu |
|---|---|---|
| **Claude** (mặc định) | `ANTHROPIC_API_KEY` | https://console.anthropic.com/ |
| Gemini | `GOOGLE_API_KEY` + `VISION_PROVIDER=gemini` | https://aistudio.google.com/apikey |
| Ollama (offline) | `VISION_PROVIDER=ollama`, `ollama pull llama3.2-vision` | không cần key |

Thanh trạng thái trên UI hiển thị provider nào đang chạy, OCR engine nào, và những register
nhãn hiệu nào đang trả lời được — nếu cấu hình sai bạn thấy ngay chứ không phải đoán.

**Tên model thay đổi theo thời gian và theo từng key.** Nếu gặp lỗi 404 model, liệt kê những
model key của bạn thực sự gọi được:

```bash
docker compose exec api python -m data.check_models          # liệt kê
docker compose exec api python -m data.check_models --probe  # gửi ảnh thật vào từng model
```

Đừng chọn model theo tốc độ — **chọn theo độ chính xác verdict** (mục 2 bên dưới).

Free tier trả 503/429 khá thường xuyên. `VISION_FALLBACK_MODELS` trong `.env` liệt kê các model
dự phòng: agent retry với backoff, hết retry thì chuyển model kế tiếp, còn lỗi không đáng retry
(sai key, sai tên model) thì bỏ qua ngay. Không có nó, một lúc provider quá tải sẽ biến design
sạch thành dòng RISKY "analysis failed".

### Register nhãn hiệu US — không cần key, không cần tải gì

Mặc định agent tra **register USPTO hiện hành** qua endpoint công khai mà chính trang
`tmsearch.uspto.gov` dùng. Không API key, không bulk download, không bước setup nào:

```
POST https://tmsearch.uspto.gov/prod-stage-v1-0-0/tmsearch
```

Nó cũng trả **Nice class**, và đó là lý do nó là nguồn US chính: một nhãn hiệu đã đăng ký cho
nhóm hàng khác được báo là *đầu mối cần kiểm tra* chứ không chặn listing. Không có class thì
mọi từ điển-từ nào có người đăng ký đều thành một finding chặn hàng — `SUPREME` của Ford
(nhóm 012, xe hơi) từng bị gán làm chủ quyền của một cái áo thun.

Tắt bằng `USPTO_TMSEARCH_LOOKUP=false`. Đây là interface công khai nhưng **không phải contract
có tài liệu**: nếu USPTO ngừng nhận traffic thì agent báo ít hit hơn và ghi rõ trong report,
chứ không treo.

`USPTO_API_KEY` (ODP, miễn phí tại https://data.uspto.gov/apis/getting-started) là **tuỳ
chọn** — nó chạy như fallback phía sau và không trả class.

> **Không còn index bulk cục bộ.** Snapshot chỉ đúng tới ngày build nó, và một snapshot cũ tệ
> hơn là không có: bản dump 2010 trả `ROXY` ở nhóm 036 của "Quiksilver, Inc" trong khi register
> hiện hành có đúng nhãn đó ở nhóm 025 dưới tên Boardriders — và vì snapshot được tra trước,
> nó *che* mất câu trả lời đúng thay vì bổ sung.

### Bật register EU (EUIPO)

USPTO không có thẩm quyền với thị trường EU. Nếu design của bạn bán ở EU, thêm credential
EUIPO — **miễn phí**, lấy trong khoảng 2 phút:

1. Đăng ký ở https://dev.euipo.europa.eu
2. Tạo một app, subscribe app đó vào **Trademark Search API**
3. Điền vào `.env`:

```bash
EUIPO_CLIENT_ID=...        # trong UI của EUIPO hiển thị là "API Key"
EUIPO_CLIENT_SECRET=...
```

Không có credential thì check EU bị bỏ qua và `/api/health` báo `registers.euipo: false` —
không im lặng coi như đã kiểm tra.

Register chỉ được gọi theo đúng thị trường của design: `US` → USPTO, `EU` → EUIPO. Gọi cả hai
cho mọi design chỉ tiêu quota để lấy bằng chứng không áp dụng được cho nơi design đang bán.
**`UK` cố ý không dùng EUIPO** — sau Brexit nhãn hiệu UK tách khỏi register EU, nên một hit
EUIPO không phải thẩm quyền cho listing bán ở UK; việc đó cần UKIPO, hiện chưa nối.

> **JPO thì sao?** Đã kiểm tra và **không khả thi**: API trademark của JPO đòi key item khớp
> *tuyệt đối* (kể cả khoảng trắng, hoa/thường) nên không dùng được cho text OCR, phải đăng ký
> bằng form và chờ cấp credential khoảng một tuần, và vẫn đang ở giai đoạn trial có giới hạn
> truy cập. Market `JP` vì vậy chỉ có policy layer, không có register.

---

## 2. Đo độ chính xác (chọn model bằng số liệu)

Bộ eval chấm agent trên các design có verdict biết trước, và tách riêng hai loại lỗi vì chúng
không tệ ngang nhau:

- **MISS** — design vi phạm bị trả SAFE. Đây là lỗi khiến seller bị khoá shop, cần triệt tiêu trước.
- **FALSE ALARM** — design sạch bị trả BLOCKED. Lỗi này làm người dùng mất tin và bỏ công cụ.

```bash
# chấm bộ synthetic dựng sẵn bằng model đang cấu hình
docker compose exec api python -m data.evaluate

# so sánh nhiều model, xếp hạng theo MISS rồi tới accuracy
docker compose exec api python -m data.evaluate \
  --models gemini-3.1-flash-lite gemini-3.5-flash-lite gemini-3-flash-preview

# chấm chính bộ 10 design của bạn
docker compose exec api python -m data.evaluate --manifest /path/manifest.csv
```

Manifest cần các cột: `filename`, `expected` (nhiều verdict chấp nhận được thì ngăn bằng `|`),
`expected_category`, `expected_niche`, `expected_sub_niche`, `markets`, `platforms`, `note`.
Cột `markets`/`platforms` cho phép mỗi design chấm theo đúng ngữ cảnh bán của nó.

**Kéo thẳng bộ mẫu của ban tổ chức về, một lệnh:**

```bash
docker compose exec api python -m data.fetch_sheet_designs <spreadsheet-id> --gid <gid>
docker compose exec api python -m data.evaluate --manifest /srv/var/designs/manifest.csv
```

Ảnh chèn đè lên ô trong Google Sheets không click phải lưu được, không có trong bản export
CSV/XLSX, và Sheets API thì đòi OAuth. Nhưng bản export **web page (zip)** có chúng dưới dạng
thẻ `<img>` trỏ tới URL googleusercontent công khai — script khai thác đúng đường đó, đồng
thời cắt hậu tố `=s145-w145-h144` để lấy bản gốc thay vì thumbnail 108px.

Niche được chấm bằng so khớp lỏng theo từ khoá, không so chuỗi chính xác — "Music Fan" và
"Classic Rock / Band Merch" là cùng một câu trả lời viết khác nhau, so chuỗi cứng sẽ chấm sai
thành trượt.

### Kết quả trên bộ 30 design của ban tổ chức

Đo thật, không phải ước lượng — `gemini-3.1-flash-lite`, 20 BLOCKED / 10 SAFE:

| Chỉ số | Kết quả |
|---|---|
| **Verdict accuracy** | **27/30 (90%)** |
| Risk category | 16/20 (80%) |
| Niche | 24/30 (80%) |
| MISS (vi phạm bị trả SAFE) | **1** |
| False alarm (sạch bị BLOCKED) | 2 |
| Latency p50 | 3.8s |

Ba điều cần nói thẳng về con số này:

1. **Có dao động giữa các lần chạy ±1–2 design.** Model là stochastic; các lần đo cho 87–90%.
   Chỉ có `6.jpg` (logo Chrome Hearts) là MISS lặp lại ổn định.
2. **Ảnh chỉ 310px.** Đó là kích thước sheet lưu, không phải bản gốc. Giám khảo chấm bằng file
   đầy đủ thì độ chính xác thực tế nhiều khả năng cao hơn — logo nhỏ và chữ mảnh dễ nhận hơn.
3. **Category từng đo được 50%, nhưng đó là lỗi của tôi chứ không phải của agent.** Nhãn
   "Text/Band Name" của BTC bị tôi map hẹp thành `trademarked_phrase`; tên ban nhạc trên áo
   đồng thời là wordmark, là brand, và thường đi kèm logo/linh vật — agent gắn `brand_logo`
   hay `copyrighted_character` là đúng, chỉ khác cách xếp mục. Sau khi cho mỗi nhãn BTC map
   sang **tập** category chấp nhận được, con số là 80%.

### Bộ synthetic 8 design (dùng để so sánh model)

| Model | Verdict | Category | Niche | MISS | False alarm | p50 |
|---|---|---|---|---|---|---|
| **gemini-3.1-flash-lite** | **100%** | **100%** | 88% | 0 | 0 | 4.4s |
| gemini-3.5-flash-lite | 100% | 75% | — | 0 | 0 | 4.4s |
| gemini-3.5-flash | 100%* | 67% | — | 0 | 0 | 21.0s |
| gemini-3-flash-preview | 75% | 50% | — | 0 | **2** | 10.1s |

\* chỉ chấm được 5/8 — ba design còn lại dính 503.

Đó là lý do mặc định là `gemini-3.1-flash-lite`. Lưu ý: 8 hình vẽ tổng hợp là bộ test nhỏ và
dễ; 100% ở đây **không** đảm bảo 100% trên design thật của giám khảo. Giá trị nằm ở chỗ chọn
model có bằng chứng, và chạy lại được với design thật.

## 3. Kiến trúc

```
                    ┌──────────────────────────────────────┐
  Upload 1..N ─────▶│                                      │
  Import CSV  ─────▶│   Next.js dashboard (:3000)          │
  Import link ─────▶│   /api/* proxy → FastAPI             │
  Drive folder ────▶│                                      │
                    └───────────────┬──────────────────────┘
                                    │
                    ┌───────────────▼──────────────────────┐
                    │   FastAPI (:8000)                    │
                    │   thread-pool queue, N workers       │
                    └───────────────┬──────────────────────┘
                                    │  mỗi design
        ┌───────────────────────────▼─────────────────────────────┐
        │ 1. loader     PNG/JPG/WEBP/HEIC/PSD/AI/PDF → RGB PNG    │
        │ 2. ocr        RapidOCR (offline, có bbox)               │
        │ 3. vision     Claude / Gemini / Ollama → JSON schema    │
        │               niche + findings + bbox                   │
        │ 4. trademark  USPTO FTS5 index + live USPTO / EUIPO     │
        │ 5. rules      policy Etsy/Amazon/TikTok × US/EU/UK/JP   │
        │ 6. verdict    rule engine (deterministic) → verdict     │
        │ 7. annotate   vẽ bounding box lên ảnh                   │
        └───────────────────────────┬─────────────────────────────┘
                                    │
                            SQLite  │  CSV / Excel export
```

### Quyết định thiết kế đáng chú ý

**Vision model tìm bằng chứng, code ra quyết định.** LLM không được hỏi "verdict là gì". Nó
liệt kê những gì *nhìn thấy* (character, logo, slogan, khuôn mặt, nội dung cấm) kèm bbox và
confidence. Verdict do [`verdict.py`](backend/app/pipeline/verdict.py) tính bằng luật thuần —
nên cùng một bằng chứng luôn ra cùng một verdict, và phần reasoning in ra chính là luật đã
kích hoạt, không phải văn của model.

**Không bao giờ fabricate dữ liệu trademark.** Prompt cấm model bịa số đăng ký. Mọi số serial,
chủ sở hữu, trạng thái đều đến từ register thật đang chạy, và mỗi finding mang theo
`evidence[]` ghi rõ nguồn + link TSDR để kiểm chứng. `evidence[].covers_goods` nói thẳng
register đó có thẩm quyền với loại hàng này hay không, nên một hit lệch nhóm không bao giờ
lặng lẽ biến thành lý do chặn.

**Nền flatten chọn theo mực in, không mặc định trắng.** Design POD được cấp ở dạng trong
suốt để in lên áo màu nào cũng được, và phần rất lớn dùng **mực trắng** cho áo tối. Ghép ảnh
đó lên nền trắng là xoá sạch thiết kế — model nhìn thấy canvas trắng và trả SAFE, đúng kiểu
thất bại tệ nhất mà công cụ này có thể mắc.

[`loader.py`](backend/app/pipeline/loader.py) vì vậy đo *nền nào sẽ xoá mất bao nhiêu phần
artwork* rồi chọn nền tránh cả hai phía: nhiều mực trắng → nền tối, nhiều mực đậm → nền trắng,
có cả hai → xám trung tính. Cách hỏi cũ ("có phần nào đủ tối để đọc trên trắng?", dùng
percentile 5) sai đúng ở loại design phổ biến nhất: một wordmark 75% chữ trắng kèm icon màu
vẫn "đạt" test, rồi mất toàn bộ phần chữ. Đo trên 60 design thật: **30% bị nền trắng xoá gần
hết nội dung**, 25% mất phần mực trắng. Một trong số đó là logo golf `BOGEY BROS GOLF CO` —
trước: OCR đọc được `'3 GOLF co'` → SAFE 88%; sau: `'BOGEYABROS GOLFCO'` → BLOCKED 96% kèm
bounding box và tên chủ sở hữu.

**Autocrop có code, nhưng mặc định TẮT — vì đo ra không có lợi.** Design POD là canvas cỡ
in với artwork nằm ở một góc; logo golf gây ra thí nghiệm này chiếm **1.6%** của file
4200×4800, nên sau khi giới hạn `RENDER_MAX_EDGE` nó co theo tỉ lệ canvas chứ không theo tỉ lệ
của chính nó. Crop về vùng artwork đưa chữ **to hơn ~3.3 lần** — nghe như thắng chắc.

Đo thì không. [`data/ab_crop.py`](backend/data/ab_crop.py) chạy 4 design × 3 lần × 2 chế độ:
**6/12 phát hiện khi tắt, 5/12 khi bật**. Ba design được lợi nhẹ, nhưng design chỉ-có-logo tụt
từ **6/6 xuống 0/6** — model gọi bản crop sát là "original work on a generic subject". Một logo
lấp kín khung đọc như *logo asset*; cùng logo đó trên canvas in đọc như *design đang được bán*.
Mất khung ngữ cảnh đắt hơn phần nét thu được, và nó hỏng đúng ở loại case mà brand logo là vi
phạm duy nhất.

Nên `AUTOCROP_TRANSPARENT=false` là mặc định, code vẫn ở đó cho catalogue artwork siêu nhỏ trên
canvas siêu lớn — kèm script để đo trước khi tin.

**Fail → RISKY, không phải SAFE.** Design phân tích lỗi (link chết, format hỏng, API timeout)
được báo RISKY kèm lý do. Không bao giờ có chuyện một check thất bại lại được đọc là "an toàn
để đăng".

**Evidence chỉ do pipeline gắn, không do model.** Trong thử nghiệm thật, model tự điền
`evidence: uspto_local_index` cho một tra cứu chưa từng xảy ra. Nên [run.py](backend/app/pipeline/run.py)
**xoá sạch** `evidence[]` model trả về rồi tự đóng dấu — model đóng góp *finding*, nguồn thì
do code xác lập.

**Chất lượng bằng chứng chặn trên mức hậu quả.** Với `trademarked_phrase`, register mới là
thẩm quyền chứ không phải model. Một cụm từ không register nào xác nhận được sẽ bị
[cap ở mức MEDIUM](backend/app/pipeline/verdict.py) — tối đa là RISKY, không bao giờ tự mình
gây BLOCKED. Cap chạy *sau* policy nên escalation cũng không đẩy ngược lên được. Đây là thứ
giữ cho "DOG MOM" không bị chặn nhầm.

**Nhiều platform không cộng dồn severity.** Bán trên cả Etsy lẫn Amazon Merch không làm design
vi phạm gấp đôi — platform khắt khe nhất quyết định. [rules.py](backend/app/pipeline/rules.py)
nâng severity một lần cho mỗi trục (platform / market), không phải mỗi lần tick thêm một ô.

**Cùng art, khác verdict theo ngữ cảnh.** Một design skull có thể SAFE trên Shopify và BLOCKED
trên Amazon Merch. [`rules.py`](backend/app/pipeline/rules.py) nâng severity theo policy của
từng nền tảng/thị trường và ghi lại link policy gốc trong report.

---

## 4. Bốn cách nhập input

| Cách | Endpoint | Ghi chú |
|---|---|---|
| **Upload file** | `POST /api/analyze/upload` | 1..N file, multipart |
| **Import CSV** | `POST /api/analyze/csv` | manifest + (tuỳ chọn) file đính kèm |
| **Import link** | `POST /api/analyze/links` | Drive / Dropbox / S3 / URL ảnh trực tiếp |
| **Connect folder** *(bonus)* | `POST /api/analyze/folder` | quét cả folder Google Drive |

### Định dạng CSV

Cột đọc được (không phân biệt hoa thường / dấu cách), thứ tự tuỳ ý:

| Cột | Bắt buộc | Ý nghĩa |
|---|---|---|
| `url` / `link` | một trong hai | URL để agent tự tải |
| `filename` / `file` | một trong hai | khớp với file đính kèm cùng request |
| `title` | không | tiêu đề listing, đưa vào ngữ cảnh phân tích |
| `markets` | không | `US,EU` — ghi đè mặc định cho riêng dòng này |
| `platforms` | không | `etsy,amazon_merch` |
| `notes` | không | ghi chú thêm cho model |

Xem [`samples/batch.csv`](samples/batch.csv).

### Link được hỗ trợ

Agent tự chuyển share-link sang direct-download: Google Drive `/file/d/<id>/view` →
`uc?export=download`, Dropbox `?dl=0` → `?dl=1`, S3 và URL ảnh trực tiếp dùng nguyên trạng.
Nếu link trả về trang HTML thay vì file, report nói rõ "link chưa được chia sẻ public" chứ
không im lặng thất bại.

---

## 5. Báo cáo đầu ra

Mỗi design trả về ([`models.py`](backend/app/models.py) là contract đầy đủ):

- **Niche** — niche chính, sub-niche/audience, style, motif phụ
- **Findings** — mỗi rủi ro có: category (1 trong 7 nhóm), severity, confidence, chủ sở hữu
  quyền, **bounding box chuẩn hoá 0..1**, mô tả vị trí bằng lời, danh sách `evidence[]`, và
  **gợi ý sửa cụ thể**
- **Verdict** SAFE / RISKY / BLOCKED + confidence 0–100
- **Reasoning** — liệt kê từng finding: vùng nào, vi phạm gì, sửa thế nào
- **Ảnh annotate** — bounding box vẽ sẵn, đổi màu theo severity
- **Register matches** — bảng khớp trademark kèm link TSDR để verify

### Batch report

Dashboard có thống kê nhanh SAFE/RISKY/BLOCKED và filter theo **verdict**, **loại vi phạm**,
**niche**. Export:

- `GET /api/jobs/{id}/export.csv` — một dòng một design
- `GET /api/jobs/{id}/export.xlsx` — 3 sheet: Summary, Designs (auto-filter, tô màu theo
  verdict), Findings (một dòng một vi phạm)

Filter đang chọn được áp vào file export.

---

## 6. Bảy nhóm rủi ro được rà soát

| Nhóm | Ví dụ | Nguồn đối chiếu |
|---|---|---|
| Nhân vật có bản quyền | Mickey Mouse, Pikachu, Batman, anime | vision model |
| Logo / brand | Nike swoosh, Apple, LV monogram, logo đội thể thao | vision model + USPTO / EUIPO |
| Câu chữ đã đăng ký | "Just Do It", "I ❤ NY" | **USPTO + EUIPO register** (exact + fuzzy) |
| Người nổi tiếng | khuôn mặt / tên celebrity, VĐV, chính trị gia | vision model |
| Tác phẩm có bản quyền | ảnh Disney/Marvel/Pixar, tranh còn bản quyền | vision model |
| Font thương mại | font cần license bị dùng free | vision model (đánh dấu cần review tay) |
| Nội dung nhạy cảm | vũ khí, ma tuý, phân biệt, 18+ | vision model + policy nền tảng |

Text trong design được kiểm tra ở cả mức **nguyên dòng** và **n-gram 2–4 từ** — slogan đã đăng
ký thường chỉ là một đoạn trong câu chữ dài hơn trên áo, kiểm tra theo dòng thôi sẽ bỏ sót.

---

## 7. Chạy dev (không Docker)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-ocr.txt        # tuỳ chọn: OCR offline có bbox
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn app.main:app --reload --port 8000

# Frontend (terminal khác)
cd frontend && npm install && npm run dev
```

### Kiểm tra pipeline không cần API key

```bash
cd backend && python -m data.smoke_test      # pipeline end-to-end, vision giả lập
cd backend && python -m data.test_registers  # tầng register: USPTO + EUIPO, HTTP giả lập
```

`smoke_test` chạy toàn bộ pipeline với vision provider giả lập — kiểm tra verdict engine, policy
layer, annotation và export.

`test_registers` kiểm tra riêng tầng tra cứu register: cách dựng RSQL, parse response, lọc mark
đã chết, cache/huỷ token OAuth, gating theo thị trường, budget riêng cho từng register, và
**nguồn bằng chứng được đóng dấu đúng register**. Cả hai đều không cần key, không cần mạng.

---

## 8. Cấu hình

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `VISION_PROVIDER` | `anthropic` | `anthropic` \| `gemini` \| `ollama` |
| `ANTHROPIC_MODEL` | `claude-opus-5` | |
| `WORKER_CONCURRENCY` | `4` | số design xử lý song song |
| `MAX_UPLOAD_MB` | `60` | giới hạn mỗi file |
| `RENDER_MAX_EDGE` | `1600` | cạnh dài ảnh gửi lên model (px) |
| `USPTO_TMSEARCH_LOOKUP` | `true` | register US công khai, không cần key — nguồn chính |
| `USPTO_LIVE_LOOKUP` | `true` | ODP có key, fallback phía sau (không trả class) |

---

## 9. Giới hạn đã biết

- **Font license không thể xác nhận từ pixel.** Nhóm `licensed_font` luôn là lead cần review
  tay, không bao giờ tự động BLOCKED một mình.
- **Bounding box do model trả về không đáng tin tuyệt đối.** Gemini phát toạ độ trên lưới
  0–1000, model khác trả pixel. [`BBox.rescale()`](backend/app/models.py) tự nhận diện và quy
  về 0..1 theo đúng kích thước ảnh model đã nhìn; box không cứu được thì bị bỏ, finding vẫn
  giữ `location_hint`. Một box hỏng không được phép làm hỏng cả phân tích.
- **Register US không cần key nữa.** Endpoint công khai của `tmsearch.uspto.gov` là nguồn
  chính; ODP có key (`api.uspto.gov`) chỉ là fallback phía sau và trả 401 nếu thiếu
  `USPTO_API_KEY`. Mỗi register có ngân sách lỗi riêng: một register chết không tiêu quota của
  register khác, và agent báo ít hit hơn chứ không treo.
- **Cụm từ chỉ được tra 12 lượt live mỗi design** (`MAX_LIVE_LOOKUPS`). Design nhiều chữ sẽ
  không được tra hết mọi cụm.
- **Nhãn hiệu >4 từ nằm trong một dòng dài hơn thì không bắt được.** Candidate chỉ tới 4-gram
  cộng cả dòng, nên một slogan 6 từ lọt giữa câu khác sẽ trượt.
- **Drive folder cần API key.** Google không có endpoint list folder ẩn danh.
- Đây là công cụ hỗ trợ sàng lọc, **không phải tư vấn pháp lý**.
