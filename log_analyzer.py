"""Parse and analyze Nginx/Apache combined access logs."""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote_plus

ROOT = Path(__file__).resolve().parent
DEFAULT_RULES_PATH = ROOT / "config" / "detection_rules.json"

# Combined format: remote ident user [time] "request" status bytes "referer" "ua".
# Referer and User-Agent are optional so the parser also accepts common-format logs.
COMBINED_RE = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^]]+)\]\s+'
    r'"(?P<request>[^"]*)"\s+(?P<status>\d{3})\s+(?P<bytes>\S+)'
    r'(?:\s+"(?P<referer>[^"]*)"(?:\s+"(?P<user_agent>[^"]*)")?)?.*$'
)
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
SEVERITY_LABEL = {"high": "高", "medium": "中", "low": "低"}


def load_rules(path: str | Path = DEFAULT_RULES_PATH) -> dict:
    """Read and validate the JSON rule set."""
    with Path(path).open(encoding="utf-8") as stream:
        rules = json.load(stream)
    for rule in rules.get("request_patterns", []):
        re.compile(rule["pattern"], re.IGNORECASE)
    return rules


def _parse_timestamp(value: str) -> datetime:
    for fmt in ("%d/%b/%Y:%H:%M:%S %z", "%d/%b/%Y:%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError("unsupported timestamp")


def parse_log_line(line: str, line_number: int = 1) -> dict | None:
    """Parse a single combined or common access-log line; return None if malformed."""
    match = COMBINED_RE.match(line.rstrip("\r\n"))
    if not match:
        return None
    fields = match.groupdict()
    request = fields["request"].strip()
    request_parts = request.split()
    if len(request_parts) >= 2:
        method, path = request_parts[0].upper(), request_parts[1]
        protocol = request_parts[2] if len(request_parts) > 2 else ""
    else:
        method, path, protocol = "OTHER", request or "-", ""
    try:
        timestamp = _parse_timestamp(fields["time"])
        status = int(fields["status"])
        size = None if fields["bytes"] == "-" else int(fields["bytes"])
    except (ValueError, TypeError):
        return None
    if size is not None and size < 0:
        return None
    return {
        "line_number": line_number,
        "ip": fields["ip"],
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "_datetime": timestamp,
        "method": method,
        "path": path,
        "protocol": protocol,
        "status": status,
        "bytes": size or 0,
        "referer": fields.get("referer") or "-",
        "user_agent": fields.get("user_agent") or "-",
    }


def parse_access_log(lines: Iterable[str]) -> tuple[list[dict], int, int]:
    records: list[dict] = []
    total_lines = 0
    malformed = 0
    for total_lines, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        record = parse_log_line(line, total_lines)
        if record is None:
            malformed += 1
        else:
            records.append(record)
    return records, malformed, total_lines


def _public_record(record: dict) -> dict:
    return {key: value for key, value in record.items() if key != "_datetime"}


def _anomaly(record: dict | None, *, ip: str, severity: str, category: str,
             rule_name: str, reason: str, path: str = "-", status: int | None = None,
             method: str = "-", user_agent: str = "-", line_number: int | None = None,
             timestamp: str | None = None) -> dict:
    if record:
        ip = record["ip"]
        path = record["path"]
        status = record["status"]
        method = record["method"]
        user_agent = record["user_agent"]
        line_number = record["line_number"]
        timestamp = record["timestamp"]
    return {
        "ip": ip, "timestamp": timestamp or "-", "method": method, "path": path,
        "status": status if status is not None else "-", "user_agent": user_agent,
        "severity": severity, "severity_label": SEVERITY_LABEL[severity],
        "category": category, "rule_name": rule_name, "reason": reason,
        "line_number": line_number or "-",
    }


def _decoded_path(value: str) -> str:
    # Decode twice to catch common double-encoded traversal attempts.
    decoded = unquote_plus(unquote_plus(value))
    return decoded.lower()


def _detect_record_rules(record: dict, rules: dict) -> list[dict]:
    hits = []
    for rule in rules.get("request_patterns", []):
        subject = record.get(rule.get("field", "path"), "")
        if rule.get("field") == "path":
            subject = _decoded_path(subject)
        if re.search(rule["pattern"], subject, re.IGNORECASE):
            hits.append(_anomaly(
                record, ip=record["ip"], severity=rule["severity"],
                category=rule["category"], rule_name=rule["name"],
                reason=f"请求字段命中可配置特征规则 {rule['id']}。",
            ))
    ua = (record.get("user_agent") or "").strip().lower()
    matched_ua = next((entry for entry in rules.get("user_agents", [])
                       if entry["keyword"].lower() in ua), None)
    if matched_ua:
        hits.append(_anomaly(
            record, ip=record["ip"], severity=matched_ua["severity"],
            category="可疑 User-Agent", rule_name=matched_ua["name"],
            reason=f"User-Agent 包含特征词 “{matched_ua['keyword']}”。",
        ))
    elif (not ua or ua == "-") and rules.get("empty_user_agent", {}).get("enabled"):
        empty_rule = rules["empty_user_agent"]
        hits.append(_anomaly(
            record, ip=record["ip"], severity=empty_rule["severity"],
            category="可疑 User-Agent", rule_name=empty_rule["name"],
            reason="请求未提供 User-Agent；需结合来源、频率和路径复核。",
        ))
    return hits


def analyze_records(records: list[dict], malformed: int = 0, total_lines: int | None = None,
                    rules: dict | None = None, source_name: str = "sample_access.log") -> dict:
    """Return chart aggregates and heuristic anomalies for parsed records."""
    rules = rules or load_rules()
    total_lines = len(records) + malformed if total_lines is None else total_lines
    if not records:
        return {
            "source_name": source_name,
            "stats": {"total_requests": 0, "unique_ips": 0, "anomaly_count": 0,
                      "error_rate": 0, "parsed_lines": 0, "total_lines": total_lines,
                      "malformed_lines": malformed, "total_bytes": 0, "time_range": "暂无有效日志"},
            "trend": [], "status_distribution": [], "method_distribution": [],
            "top_ips": [], "top_urls": [], "anomaly_categories": [],
            "severity_distribution": [], "anomalies": [],
        }

    ip_counts = Counter(r["ip"] for r in records)
    url_counts = Counter(r["path"] for r in records)
    status_counts = Counter(str(r["status"]) for r in records)
    method_counts = Counter(r["method"] for r in records)
    hourly = Counter(r["_datetime"].strftime("%Y-%m-%d %H:00") for r in records)
    ip_status = defaultdict(Counter)
    ip_records = defaultdict(list)
    for record in records:
        ip_status[record["ip"]][record["status"]] += 1
        ip_records[record["ip"]].append(record)

    anomalies: list[dict] = []
    for record in records:
        anomalies.extend(_detect_record_rules(record, rules))

    thresholds = rules.get("thresholds", {})
    for ip, items in ip_records.items():
        count = len(items)
        statuses = ip_status[ip]
        newest = max(items, key=lambda r: r["_datetime"])
        if count >= int(thresholds.get("high_frequency_requests", 120)):
            anomalies.append(_anomaly(
                newest, ip=ip, severity="high", category="高频访问",
                rule_name="单 IP 高频访问", reason=f"该 IP 在当前日志中出现 {count} 次请求，超过阈值。",
            ))
        err4 = sum(n for code, n in statuses.items() if 400 <= code < 500)
        err5 = sum(n for code, n in statuses.items() if 500 <= code < 600)
        if count >= int(thresholds.get("ip_error_min_requests", 10)):
            rate4 = err4 / count
            if rate4 >= float(thresholds.get("ip_4xx_rate", 0.72)):
                anomalies.append(_anomaly(
                    newest, ip=ip, severity="high" if rate4 >= 0.9 else "medium",
                    category="状态码异常", rule_name="单 IP 4xx 错误率偏高",
                    reason=f"该 IP 的 4xx 占比为 {rate4:.0%}（{err4}/{count}）。",
                ))
        if count >= int(thresholds.get("ip_5xx_min_requests", 10)):
            rate5 = err5 / count
            if rate5 >= float(thresholds.get("ip_5xx_rate", 0.25)):
                anomalies.append(_anomaly(
                    newest, ip=ip, severity="high", category="状态码异常",
                    rule_name="单 IP 5xx 错误率偏高",
                    reason=f"该 IP 的 5xx 占比为 {rate5:.0%}（{err5}/{count}）。",
                ))

        login_items = [r for r in items if r["method"] == "POST" and
                       re.search(r"(?:login|signin|auth)", r["path"], re.IGNORECASE)]
        failures = [r for r in login_items if r["status"] in (401, 403)]
        successes = [r for r in login_items if r["status"] == 200]
        fail_threshold = int(thresholds.get("login_failure_count", 8))
        if len(failures) >= fail_threshold:
            success_after = bool(successes and failures and
                                 min(r["_datetime"] for r in successes) > max(r["_datetime"] for r in failures))
            event = max(login_items, key=lambda r: r["_datetime"])
            anomalies.append(_anomaly(
                event, ip=ip, severity="high" if success_after else "medium",
                category="暴力破解", rule_name="登录失败次数异常",
                reason=(f"登录接口出现 {len(failures)} 次 401/403 失败" +
                        ("，随后出现 200 成功响应，需优先核查。" if success_after else "，建议核查是否为自动化尝试。")),
            ))

    # Keep one logical alert per rule event; individual matching requests remain inspectable.
    severity_counts = Counter(a["severity"] for a in anomalies)
    category_counts = Counter(a["category"] for a in anomalies)
    anomalies.sort(key=lambda a: (
        SEVERITY_ORDER.get(a["severity"], 9), a["timestamp"] == "-", a["timestamp"],
        a["line_number"] if isinstance(a["line_number"], int) else 0,
    ), reverse=False)
    # Highest risk first, then recent timestamps within the same risk level.
    anomalies.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 9), a["timestamp"]), reverse=False)

    times = [r["_datetime"] for r in records]
    error_total = sum(n for code, n in status_counts.items() if code.startswith(("4", "5")))
    trend_keys = sorted(hourly)
    if trend_keys and len(trend_keys) <= 744:
        start = datetime.strptime(trend_keys[0], "%Y-%m-%d %H:%M")
        end = datetime.strptime(trend_keys[-1], "%Y-%m-%d %H:%M")
        all_hours = []
        cursor = start
        while cursor <= end:
            all_hours.append(cursor.strftime("%Y-%m-%d %H:00"))
            cursor += timedelta(hours=1)
        trend_keys = all_hours
    top_items = lambda counter, limit=10: [
        {"name": name, "value": value} for name, value in counter.most_common(limit)
    ]
    range_start, range_end = min(times), max(times)
    stats = {
        "total_requests": len(records), "unique_ips": len(ip_counts),
        "anomaly_count": len(anomalies), "error_rate": round(error_total / len(records) * 100, 2),
        "parsed_lines": len(records), "total_lines": total_lines, "malformed_lines": malformed,
        "total_bytes": sum(r["bytes"] for r in records),
        "time_range": f"{range_start.strftime('%Y-%m-%d %H:%M')} 至 {range_end.strftime('%Y-%m-%d %H:%M')}",
        "high_anomalies": severity_counts.get("high", 0),
        "medium_anomalies": severity_counts.get("medium", 0),
        "low_anomalies": severity_counts.get("low", 0),
    }
    return {
        "source_name": source_name,
        "stats": stats,
        "trend": [{"time": key, "value": hourly.get(key, 0)} for key in trend_keys],
        "status_distribution": [{"name": name, "value": value} for name, value in
                                sorted(status_counts.items(), key=lambda pair: int(pair[0]))],
        "method_distribution": top_items(method_counts),
        "top_ips": top_items(ip_counts),
        "top_urls": top_items(url_counts),
        "anomaly_categories": [{"name": name, "value": value} for name, value in
                                category_counts.most_common()],
        "severity_distribution": [
            {"name": SEVERITY_LABEL[level], "value": severity_counts.get(level, 0)}
            for level in ("high", "medium", "low") if severity_counts.get(level, 0)
        ],
        "anomalies": anomalies,
    }


def analyze_lines(lines: Iterable[str], rules: dict | None = None,
                  source_name: str = "uploaded.log") -> dict:
    records, malformed, total_lines = parse_access_log(lines)
    return analyze_records(records, malformed, total_lines, rules, source_name)


def export_anomalies_csv(anomalies: Iterable[dict]) -> str:
    """Serialize anomaly rows as UTF-8 with a BOM for spreadsheet compatibility."""
    import io
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["风险等级", "检测类别", "规则名称", "客户端 IP", "时间", "方法", "请求路径", "状态码", "User-Agent", "日志行号", "判断说明"])
    for item in anomalies:
        writer.writerow([
            item.get("severity_label", SEVERITY_LABEL.get(item.get("severity"), "")),
            item.get("category", ""), item.get("rule_name", ""), item.get("ip", ""),
            item.get("timestamp", ""), item.get("method", ""), item.get("path", ""),
            item.get("status", ""), item.get("user_agent", ""), item.get("line_number", ""),
            item.get("reason", ""),
        ])
    return "\ufeff" + output.getvalue()
