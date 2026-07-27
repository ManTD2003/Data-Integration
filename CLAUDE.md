# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Bối cảnh thư mục

Đây là thư mục học tập cho môn **IT5420 – Tích hợp dữ liệu** (Data Integration),
chương trình Thạc sĩ, Trường CNTT&TT – ĐH Bách Khoa Hà Nội (GV: Vũ Tuyết Trinh,
trinhvt@soict.hust.edu.vn). Đây **không phải codebase phần mềm** — hiện chỉ chứa
slide bài giảng và đề Bài tập lớn (BTL). Ngôn ngữ làm việc mặc định: **tiếng Việt**.

Cấu trúc:
- `slide/` — slide bài giảng dạng PDF (xem "Nội dung môn học" bên dưới).
- `De_bai_BTL.md` — đề Bài tập lớn.
- `slide/IT5420_updated.pdf` — syllabus + lịch học.

## Đề Bài tập lớn (BTL — chiếm 40% điểm môn)

**Đề tài:** Tích hợp thông tin việc làm/tuyển dụng, **tập trung vào tích hợp kỹ năng làm việc**.

- **Nguồn dữ liệu:** vieclam24h.vn, topcv.vn… hoặc nguồn khác, hoặc dùng dataset đã thu thập/xây dựng sẵn.
- **Yêu cầu cốt lõi:**
  1. Tích hợp dữ liệu từ nhiều nguồn tin tuyển dụng.
  2. Phân tích & tích hợp **yêu cầu về kỹ năng**: kỹ năng cứng vs kỹ năng mềm;
     kỹ năng cụ thể vs kỹ năng tổng quát (ví dụ: *lập trình* → *lập trình Python, Java…*).
  3. Xây **công cụ tìm kiếm** khai thác thông tin kỹ năng đã tích hợp — cho phép tìm
     kiếm theo cách tổ chức/thông tin kỹ năng đã trích chọn và tích hợp được.
- **Nhóm:** 3–4 học viên. Chọn **định hướng: NLP / ML / (Distributed) Systems / Application**.
- Báo cáo Project: cả ngày (theo lịch trong syllabus).

Khi triển khai BTL, bám sát các kỹ thuật đã học (xem bên dưới): wrapper để trích xuất
tin tuyển dụng, string/schema/data matching để hợp nhất kỹ năng đồng nghĩa và xây phân
cấp kỹ năng (cụ thể→tổng quát), mediated schema + query reformulation hoặc data
warehouse để tích hợp và truy vấn.

## Nội dung môn học (khung lý thuyết để đối chiếu khi làm BTL)

Kiến trúc tổng thể: **virtual integration** (mediated schema + wrappers + query
reformulation) vs **data warehouse** (ETL + materialization). Heterogeneity (schema
& data) là vấn đề trung tâm ở cả hai.

- `1_Introduction.pdf` — Kiến trúc tích hợp, mediated schema, virtual vs warehouse, ôn tập RDBMS/conjunctive queries/datalog.
- `2_Data source.pdf` (+ `2_Data source (added).pdf`) — Mô tả nguồn dữ liệu, schema mapping: **GAV / LAV / GLAV**, query reformulation (unfolding), certain answers.
- `3_wrapper.pdf` — Xây **wrapper** trích xuất dữ liệu từ HTML: HLRT, Stalker, RoadRunner, Lixto; wrapper thủ công vs học tự động.
- `4_matching_mapping.pdf` — **String matching** (edit distance, overlap, TF/IDF, inverted index) và **data matching** (rule-based, logistic regression, clustering, scale-up).
- `4_matching_mapping(Part2).pdf` — **Schema matching & mapping**: name-based/instance-based matchers, classifiers, A* search, multi-strategy learning, từ matching sang mapping.
- `5_DW_OLAP.pdf` — **Data warehouse & OLAP**: ETL, star/fact-constellation schema, data cube, OLAP operations, iceberg cube, join indices.
- `5_DW_Caching.pdf` — Kiến trúc DW, **data exchange** (universal solutions), materialization/caching, MapReduce dataflow.

## Làm việc với slide PDF

Máy chưa có `pdftotext`/poppler. Để trích text từ PDF, dùng PyMuPDF (đã cài qua
`--break-system-packages`):

```bash
python3 -c "import fitz; d=fitz.open('slide/1_Introduction.pdf'); print('\n'.join(d[i].get_text() for i in range(d.page_count)))"
```

Nếu `import fitz` lỗi: `python3 -m pip install --break-system-packages pymupdf`.
Tool `Read` không render được PDF trong môi trường này (thiếu poppler) — dùng PyMuPDF thay thế.

## Quy tắc bản nộp — KHÔNG lộ dấu vết AI (bắt buộc khi tạo mã/tài liệu nộp)

Mọi mã nguồn, báo cáo, README, comment sinh ra phải đọc như người viết:
- Không log/print thừa để debug trong mã nộp.
- Không comment/docstring kiểu hướng dẫn máy sinh (bỏ comment hiển nhiên, bỏ "Bước 1/Bước 2…" giải thích quá đà); comment ngắn, giải thích *tại sao*.
- Không emoji, không tiêu đề trang trí, không câu "Đây là…"/"Chúc bạn…" trong README/báo cáo; văn phong tiếng Việt tự nhiên, học thuật.
- Không để TODO/placeholder, block "example usage" thừa, tên biến chung chung do AI sinh.
- Thống nhất phong cách xuyên suốt; chạy formatter (black/isort).

Chi tiết & checklist rà soát: xem mục 10 trong `KE_HOACH_BTL.md`.

## Ghi chú

- Chưa có build/lint/test — thư mục chưa chứa code. Khi bắt đầu code BTL, cập nhật lại
  mục này với lệnh build/run/test tương ứng.
- Repo hiện **không phải git**; khởi tạo git nếu bắt đầu triển khai BTL.
- Kế hoạch chi tiết BTL: `TOPIC.md`.
