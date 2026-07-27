# Tích hợp dữ liệu tuyển dụng — trọng tâm tích hợp kỹ năng

Hệ thống tích hợp tin tuyển dụng từ nhiều nguồn dị thể, trích chọn và tích hợp thông
tin kỹ năng, phục vụ tìm kiếm và phân tích nhu cầu kỹ năng. Xem kế hoạch tổng thể ở
`KE_HOACH_BTL.md`.

## Cài đặt

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Pipeline Mốc 1 — thu thập và tích hợp

Chạy tuần tự từ thư mục gốc dự án:

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
```

Kết quả: `data/raw/*.jsonl` (dữ liệu thô mỗi nguồn), `data/staging/records.jsonl`
(bản chuẩn hoá schema), `data/staging/records_deduped.jsonl` (đã gắn nhóm trùng),
`data/staging/skill_dictionary.json` (từ điển kỹ năng), `data/staging/job_skills.jsonl`
(cặp job-skill đã trích xuất).

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
  IT (vieclam24h đa ngành). Ghi ra `data/staging/skill_dictionary.json`.
- `src/process/extract_skills.py` — trích cặp (job, skill): dùng thẳng `skills_given`
  khi có (`source_provided`), còn lại đối sánh gazetteer theo n-gram trên
  title/requirements_raw/description (`exact_match`) rồi fuzzy match rapidfuzz cho
  từ đơn chưa khớp (`fuzzy_match`). Mỗi kết quả giữ `evidence` (đoạn văn bản gốc)
  để phục vụ tra cứu provenance sau này.

## Kiểm thử

```bash
.venv/bin/python -m pytest tests/ -q
```

## Nguồn dữ liệu

- vieclam24h.vn — cào trực tiếp, đọc khối `__NEXT_DATA__` (nguồn tiếng Việt đa ngành,
  có `job_requirement`/`other_requirement`).
- itviec.com — cào trực tiếp bằng bóc tách DOM + trang `/content` (nguồn IT tiếng Anh,
  có sẵn skill tags và mục "Your skills and experience").
- lukebarousse/data_jobs (HuggingFace) — nguồn tiếng Anh, schema khác, có sẵn `job_skills`.

topcv.vn trả 403 với client HTTP thuần (anti-bot), cần trình duyệt thật (Playwright)
nếu muốn bổ sung; hiện chưa dùng.
