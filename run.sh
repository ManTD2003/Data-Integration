#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Git Bash trên Windows đặt binary của venv ở Scripts/, Linux và macOS ở bin/
resolve_py() {
    if [ -f .venv/Scripts/python.exe ]; then
        PY=.venv/Scripts/python.exe
    else
        PY=.venv/bin/python
    fi
}
resolve_py

# Console Windows mặc định cp1252, không in được tên kỹ năng tiếng Việt
export PYTHONIOENCODING=utf-8

MAX_PAGES_VIECLAM24H=5
MAX_PAGES_ITVIEC=10
HF_LIMIT=1500

need_venv() {
    if [ ! -f "$PY" ]; then
        echo "Chưa có môi trường ảo. Chạy: ./run.sh setup" >&2
        exit 1
    fi
}

need_warehouse() {
    if [ ! -f data/warehouse.duckdb ]; then
        echo "Chưa có data/warehouse.duckdb. Chạy: ./run.sh build" >&2
        exit 1
    fi
}

cmd_setup() {
    # Các bản pin trong requirements.txt chưa có wheel cho Python 3.13+, phải giữ 3.12
    if command -v uv > /dev/null 2>&1; then
        uv venv --python 3.12 --allow-existing
        uv pip install -r requirements.txt
    else
        python3 -m venv .venv
        resolve_py
        "$PY" -m pip install --upgrade pip
        "$PY" -m pip install -r requirements.txt
    fi
}

cmd_crawl() {
    need_venv
    "$PY" -m src.ingestion.crawl --source vieclam24h --max-pages "$MAX_PAGES_VIECLAM24H"
    "$PY" -m src.ingestion.crawl --source itviec --max-pages "$MAX_PAGES_ITVIEC"
    "$PY" -m src.ingestion.loaders.hf_dataset --limit "$HF_LIMIT"
}

cmd_build() {
    need_venv
    "$PY" -m src.integration.build_staging
    "$PY" -m src.integration.dedup
    "$PY" -m src.process.skill_dictionary
    "$PY" -m src.process.extract_skills
    "$PY" -m src.process.resolve_variants
    "$PY" -m src.process.build_hierarchy
    "$PY" -m src.warehouse.build_warehouse
}

cmd_test() {
    need_venv
    "$PY" -m pytest tests/ -q
}

cmd_eval() {
    need_venv
    need_warehouse
    "$PY" -m src.eval.report "$@"
}

cmd_api() {
    need_venv
    need_warehouse
    "$PY" -m uvicorn src.api.main:app --reload
}

cmd_app() {
    need_venv
    need_warehouse
    # headless để streamlit bỏ qua bước hỏi email lần đầu chạy
    "$PY" -m streamlit run src/app/streamlit_app.py --server.headless true
}

usage() {
    cat <<'EOF'
Cách dùng: ./run.sh <lệnh>

  setup   Tạo .venv (Python 3.12) và cài dependencies
  crawl   Thu thập dữ liệu thô từ vieclam24h, itviec và dataset HuggingFace
  build   Tích hợp dữ liệu trong data/raw rồi nạp kho DuckDB
  all     crawl + build
  test    Chạy pytest
  eval    In bảng chỉ số đánh giá (thêm --json để lưu kết quả thô)
  api     Chạy FastAPI (http://127.0.0.1:8000, tài liệu ở /docs)
  app     Chạy web app Streamlit (http://localhost:8501)

Kho dữ liệu đã dựng sẵn nên chỉ cần `setup` rồi `app`. Chạy `crawl` khi muốn
lấy dữ liệu mới, sau đó `build` lại.
EOF
}

case "${1:-}" in
    setup) cmd_setup ;;
    crawl) cmd_crawl ;;
    build) cmd_build ;;
    all) cmd_crawl; cmd_build ;;
    test) cmd_test ;;
    eval) shift; cmd_eval "$@" ;;
    api) cmd_api ;;
    app) cmd_app ;;
    *) usage; exit 1 ;;
esac
