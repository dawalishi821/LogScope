"""Flask application and JSON/CSV API for the access-log dashboard."""
from __future__ import annotations

import io
from pathlib import Path
from threading import RLock

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from log_analyzer import analyze_lines, export_anomalies_csv, load_rules

ROOT = Path(__file__).resolve().parent
SAMPLE_PATH = ROOT / "data" / "sample_access.log"
ALLOWED_EXTENSIONS = {".log", ".txt"}
MAX_UPLOAD_BYTES = 16 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
RULES = load_rules()
_STATE_LOCK = RLock()


def _analyze_sample() -> dict:
    with SAMPLE_PATH.open("r", encoding="utf-8", errors="replace") as stream:
        return analyze_lines(stream, RULES, SAMPLE_PATH.name)


_CURRENT = _analyze_sample()


def _filtered_anomalies(params) -> list[dict]:
    with _STATE_LOCK:
        rows = list(_CURRENT["anomalies"])
    severity = (params.get("severity") or "").strip().lower()
    category = (params.get("category") or "").strip()
    query = (params.get("q") or "").strip().lower()
    if severity in {"high", "medium", "low"}:
        rows = [row for row in rows if row["severity"] == severity]
    if category:
        rows = [row for row in rows if row["category"] == category]
    if query:
        rows = [row for row in rows if query in " ".join(str(row.get(key, "")) for key in (
            "ip", "path", "rule_name", "category", "reason", "user_agent", "status"
        )).lower()]
    return rows


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "LogScope", "version": "1.0.0"})


@app.get("/api/summary")
def summary():
    with _STATE_LOCK:
        response = {key: value for key, value in _CURRENT.items() if key != "anomalies"}
        response["categories"] = sorted({item["category"] for item in _CURRENT["anomalies"]})
    return jsonify(response)


@app.get("/api/anomalies")
def anomalies():
    rows = _filtered_anomalies(request.args)
    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = max(1, min(100, int(request.args.get("page_size", "20"))))
    except ValueError:
        return jsonify({"error": "page 和 page_size 必须是整数。"}), 400
    start = (page - 1) * page_size
    return jsonify({
        "items": rows[start:start + page_size],
        "total": len(rows), "page": page, "page_size": page_size,
        "pages": max(1, (len(rows) + page_size - 1) // page_size),
    })


@app.get("/api/anomalies/export.csv")
def export_csv():
    content = export_anomalies_csv(_filtered_anomalies(request.args)).encode("utf-8")
    return send_file(
        io.BytesIO(content), mimetype="text/csv; charset=utf-8",
        as_attachment=True, download_name="logscope-anomalies.csv",
        max_age=0,
    )


def _replace_analysis(result: dict) -> None:
    global _CURRENT
    with _STATE_LOCK:
        _CURRENT = result


@app.post("/api/sample")
def load_sample():
    _replace_analysis(_analyze_sample())
    return jsonify({"ok": True, "source_name": SAMPLE_PATH.name, "stats": _CURRENT["stats"]})


@app.post("/api/upload")
def upload_log():
    uploaded = request.files.get("logfile")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "请选择一个 .log 或 .txt 日志文件。"}), 400
    safe_name = secure_filename(uploaded.filename)
    if Path(safe_name).suffix.lower() not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "文件格式不支持，请上传 .log 或 .txt 文件。"}), 400
    payload = uploaded.stream.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        return jsonify({"error": "文件超过 16 MB 限制。"}), 413
    try:
        text = payload.decode("utf-8-sig", errors="replace")
    except UnicodeDecodeError:
        return jsonify({"error": "文件无法按 UTF-8 编码读取。"}), 400
    result = analyze_lines(text.splitlines(), RULES, safe_name or "uploaded.log")
    if not result["stats"]["parsed_lines"]:
        return jsonify({"error": "没有解析到有效日志。请检查是否为 Nginx/Apache combined 或 common 格式。"}), 422
    _replace_analysis(result)
    return jsonify({"ok": True, "source_name": result["source_name"], "stats": result["stats"]})


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "文件超过 16 MB 限制。"}), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
