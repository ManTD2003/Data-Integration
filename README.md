# Tích hợp dữ liệu tuyển dụng — trọng tâm tích hợp kỹ năng

Hệ thống tích hợp tin tuyển dụng từ nhiều nguồn dị thể, trích chọn và tích hợp thông
tin kỹ năng, phục vụ tìm kiếm và phân tích nhu cầu kỹ năng. Đề tài và định hướng ở
`TOPIC.md`.

## Cài đặt

```bash
./run.sh setup
```

Script tự dò đường dẫn venv (`.venv/bin` trên Linux/macOS, `.venv/Scripts` trên Git
Bash) nên dùng được cả hai nền tảng. Bản pin trong `requirements.txt` cần Python 3.12;
3.13+ chưa có wheel sẵn cho `greenlet`/`lxml` nên sẽ phải biên dịch từ nguồn.

Không dùng `run.sh` thì làm tay:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Pipeline Mốc 1 — thu thập và tích hợp

`./run.sh crawl` chạy bước 1–3, `./run.sh build` chạy bước 4–10. Thứ tự là bắt buộc:
bước 8 gộp biến thể rồi ghi lại từ điển, bước 9 gắn phân cấp lên từ điển đó, nên chạy
lệch thứ tự sẽ mất phân cấp — `build_warehouse` kiểm tra ràng buộc và dừng nếu gặp
tình trạng này. Chạy tay từng bước:

```bash
# 1. Cào vieclam24h theo danh sách từ khoá trong config/queries.txt
.venv/bin/python -m src.ingestion.crawl --source vieclam24h --max-pages 5

# 2. Cào itviec (theo trang, có fetch mô tả công việc)
.venv/bin/python -m src.ingestion.crawl --source itviec --max-pages 10

# 3. Nạp dataset công khai (lukebarousse/data_jobs) làm nguồn thứ ba
.venv/bin/python -m src.ingestion.loaders.hf_dataset --limit 1500

# 4. Ánh xạ mọi nguồn về mediated schema (GAV)
.venv/bin/python -m src.integration.build_staging

# 5. Khử trùng lặp tin bằng string matching (blocking + rapidfuzz)
.venv/bin/python -m src.integration.dedup

# 6. Xây từ điển kỹ năng mầm (mined từ skills_given + bổ sung tay ngoài IT)
.venv/bin/python -m src.process.skill_dictionary

# 7. Trích xuất kỹ năng: dùng skills_given có sẵn hoặc gazetteer/fuzzy trên text
.venv/bin/python -m src.process.extract_skills

# 8. Entity resolution: gộp biến thể cùng một kỹ năng (react/ReactJS, mongo/MongoDB...)
.venv/bin/python -m src.process.resolve_variants

# 9. Phân cấp kỹ năng cụ thể -> tổng quát + closure table
.venv/bin/python -m src.process.build_hierarchy

# 10. Nạp star schema vào DuckDB (dim_job, dim_skill, fact_job_skill...)
.venv/bin/python -m src.warehouse.build_warehouse
```

Kết quả: `data/raw/*.jsonl` (dữ liệu thô mỗi nguồn), `data/staging/records.jsonl`
(bản chuẩn hoá schema), `data/staging/records_deduped.jsonl` (đã gắn nhóm trùng),
`data/staging/skill_dictionary.json` (từ điển kỹ năng, đã gộp biến thể và gắn
`parent_skill_id`), `data/staging/job_skills.jsonl` (cặp job-skill đã trích xuất),
`data/staging/skill_merge_log.json` (log các cụm biến thể đã gộp),
`data/staging/skill_closure.jsonl` (bảng closure ancestor/descendant cho phân cấp),
`data/warehouse.duckdb` (kho dữ liệu star schema).

## Cấu trúc

- `src/common/schema.py` — mediated schema `JobRecord` (đích của ánh xạ GAV).
- `src/ingestion/wrappers/` — wrapper cào từng site. `vieclam24h.py` đọc dữ liệu từ
  khối `__NEXT_DATA__` (Next.js) và phân trang theo metadata trả về.
- `src/ingestion/loaders/hf_dataset.py` — nạp dataset qua HuggingFace datasets-server.
- `src/integration/schema_mapping.py` — ánh xạ GAV từng nguồn; `FIELD_MAP` ghi lại
  quan hệ trường nguồn ↔ trường mediated; `suggest_field_matches` là name-based matcher.
- `src/integration/dedup.py` — gom bản ghi trùng theo union-find trên các block.
- `src/process/skill_dictionary.py` — từ điển kỹ năng: mining `skills_given` (itviec,
  data_jobs) gộp biến thể chữ hoa/thường + bổ sung tay kỹ năng mềm và kỹ năng ngoài
  IT (vieclam24h đa ngành). Ghi ra `data/staging/skill_dictionary.json`. `_slugify`
  phiên âm ký hiệu và chữ "đ" trước khi lọc ASCII, nên `C#`/`C++`/`C` ra ba id khác
  nhau (`c-sharp`/`c-plus-plus`/`c`) thay vì phụ thuộc thứ tự chèn.
- `src/process/extract_skills.py` — trích cặp (job, skill): dùng thẳng `skills_given`
  khi có (`source_provided`), còn lại đối sánh gazetteer theo n-gram trên
  title/requirements_raw/description (`exact_match`) rồi fuzzy match rapidfuzz cho
  từ đơn chưa khớp (`fuzzy_match`). Mỗi kết quả giữ `evidence` (đoạn văn bản gốc)
  để phục vụ tra cứu provenance sau này.
- `src/process/resolve_variants.py` — entity resolution biến thể kỹ năng: luật tách
  hậu tố `js`/`.js` (react/ReactJS/react.js -> react) cộng danh sách gộp thủ công cho
  viết tắt bất quy tắc (mongo -> MongoDB...). Đã thử TF-IDF ký tự n-gram trước nhưng
  không tách được ngưỡng an toàn (xem docstring trong file), nên chọn cách này.
- `src/process/build_hierarchy.py` — gán `parent_skill_id` theo `CATEGORY_MAP` (phân
  loại lĩnh vực soát tay qua từ điển đã gộp), gom tiếp các lĩnh vực vào `ROOT_MAP` để
  chuỗi cụ thể -> tổng quát có ba mức (Python -> Ngôn ngữ lập trình -> Kỹ năng công
  nghệ thông tin), rồi dựng `bridge_skill_closure` (`skill_closure.jsonl`) theo kiểu
  bắc cầu: mỗi skill sinh một dòng cho từng tổ tiên, không chỉ cho cha trực tiếp.
- `src/warehouse/build_warehouse.py` — nạp star schema vào `data/warehouse.duckdb`:
  `dim_job/dim_company/dim_location/dim_time/dim_skill/dim_skill_variant` +
  `fact_job_skill` + `bridge_skill_closure`. `check_integrity` chặn việc nạp khi
  staging không nhất quán (closure trỏ tới skill_id không tồn tại, phân cấp rỗng).
  `salary_raw` khác đơn vị theo nguồn (vieclam24h/itviec: khoảng lương tháng VNĐ;
  data_jobs: lương trung bình năm USD) nên giữ nguyên `salary_currency`/
  `salary_period` thay vì tự quy đổi tỷ giá.

## Công cụ tìm kiếm

```bash
# API: tìm việc theo kỹ năng (mở rộng phân cấp), tra cứu kỹ năng, thống kê OLAP
.venv/bin/uvicorn src.api.main:app --reload

# Web app (Streamlit) — gọi thẳng lớp truy vấn, không qua HTTP
.venv/bin/streamlit run src/app/streamlit_app.py
```

- `src/api/queries.py` — lớp truy vấn DuckDB dùng chung cho cả API và Streamlit
  (mỗi hàm nhận `con` để test độc lập với dữ liệu mẫu, không phụ thuộc kho thật).
- `src/api/main.py` — FastAPI: `/skills` (tìm kỹ năng theo tên/biến thể),
  `/skills/{id}` (chi tiết + provenance), `/jobs/search` (tìm việc theo kỹ năng,
  `expand=true` mở rộng qua closure table), `/stats/top-skills`,
  `/stats/hard-soft-ratio`.
- `src/app/streamlit_app.py` — 3 trang: tìm việc theo kỹ năng, tra cứu kỹ năng
  (canonical, biến thể, cha/con, ví dụ trích chọn), dashboard OLAP.

## Đánh giá

```bash
./run.sh eval            # bảng chỉ số
./run.sh eval --json     # kết quả thô để so giữa các lần chạy
```

- `src/eval/metrics.py` — `SetScore` (tp/fp/fn -> P/R/F1) và `reciprocal_rank`.
- `src/eval/extraction.py` — đo trích xuất kỹ năng bằng nhãn `skills_given` có sẵn của
  itviec/data_jobs: che nhãn đi, chạy bộ trích xuất trên text rồi so lại. Đây là
  **silver standard** kiểu distant supervision, không phải gold do người gán: nhãn của
  site không đầy đủ nên precision đo được là chặn dưới của precision thật, recall tin
  cậy hơn. Với data_jobs, `requirements_raw` chính là `job_skills` đã nối chuỗi nên
  nguồn này chỉ đo trên `title` — recall thấp là điều dự kiến. vieclam24h không có nhãn
  sẵn, muốn có số cho nó phải gán tay một mẫu tin.
- `src/eval/retrieval.py` — P@1/MRR của `search_skills` trên `data/eval/queries.jsonl`
  (35 truy vấn người soạn: viết tắt, thiếu dấu, ký hiệu, tên nhóm tổng quát; kỳ vọng
  viết theo ý người dùng chứ không theo kết quả hệ thống). Phần mở rộng phân cấp không
  cần nhãn: nó dựng lại tập hậu duệ từ `parent_skill_id` bằng Python rồi so với
  `bridge_skill_closure`, hai đường tính độc lập kiểm nhau.
- `src/eval/integrity.py` — ràng buộc khoá ngoại và bất biến phân cấp trên kho đã nạp.

## Kiểm thử

```bash
./run.sh test
```

`tests/test_eval_metrics.py` kiểm chính các hàm tính chỉ số trên ví dụ có đáp án tính
tay, để số đo không đẹp vì lỗi trong code đo.

## Nguồn dữ liệu

- vieclam24h.vn — cào trực tiếp, đọc khối `__NEXT_DATA__` (nguồn tiếng Việt đa ngành,
  có `job_requirement`/`other_requirement`).
- itviec.com — cào trực tiếp bằng bóc tách DOM + trang `/content` (nguồn IT tiếng Anh,
  có sẵn skill tags và mục "Your skills and experience").
- lukebarousse/data_jobs (HuggingFace) — nguồn tiếng Anh, schema khác, có sẵn `job_skills`.