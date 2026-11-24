from __future__ import annotations

import unittest
from pathlib import Path

from log_analyzer import analyze_lines, load_rules, parse_access_log, parse_log_line

ROOT = Path(__file__).resolve().parents[1]


def make_line(ip="192.0.2.9", stamp="21/Nov/2026:09:30:00 +0800", method="GET",
              path="/index.html", status=200, size=123, ua="Mozilla/5.0"):
    return f'{ip} - - [{stamp}] "{method} {path} HTTP/1.1" {status} {size} "-" "{ua}"'


class ParserTests(unittest.TestCase):
    def test_parses_combined_fields(self):
        record = parse_log_line(make_line(path="/search?q=key", method="POST", status=401), 7)
        self.assertIsNotNone(record)
        self.assertEqual(record["line_number"], 7)
        self.assertEqual(record["ip"], "192.0.2.9")
        self.assertEqual(record["method"], "POST")
        self.assertEqual(record["path"], "/search?q=key")
        self.assertEqual(record["status"], 401)
        self.assertEqual(record["bytes"], 123)
        self.assertEqual(record["user_agent"], "Mozilla/5.0")

    def test_accepts_common_format_without_combined_tail(self):
        line = '192.0.2.8 - - [21/Nov/2026:10:00:00 +0800] "GET / HTTP/1.0" 200 -'
        record = parse_log_line(line)
        self.assertEqual(record["bytes"], 0)
        self.assertEqual(record["referer"], "-")
        self.assertEqual(record["user_agent"], "-")

    def test_malformed_lines_are_counted_and_skipped(self):
        records, malformed, total = parse_access_log([make_line(), "bad input", "\n"])
        self.assertEqual((len(records), malformed, total), (1, 1, 3))


class DetectionTests(unittest.TestCase):
    def test_config_has_at_least_five_request_signatures(self):
        rules = load_rules(ROOT / "config" / "detection_rules.json")
        self.assertGreaterEqual(len(rules["request_patterns"]), 5)

    def test_detects_encoded_sql_injection_and_traversal(self):
        lines = [
            make_line(ip="203.0.113.20", path="/p?id=1%20UNION%20SELECT%20password"),
            make_line(ip="203.0.113.21", path="/download?file=%2e%2e%2fetc%2fpasswd", status=404),
        ]
        result = analyze_lines(lines)
        names = {item["rule_name"] for item in result["anomalies"]}
        self.assertIn("SQL 注入：UNION SELECT", names)
        self.assertIn("路径遍历：目录穿越特征", names)

    def test_detects_failed_login_burst_followed_by_success(self):
        lines = [make_line(ip="203.0.113.30", stamp=f"21/Nov/2026:09:{minute:02d}:00 +0800",
                           method="POST", path="/login", status=401, ua="Hydra/9.4")
                 for minute in range(8)]
        lines.append(make_line(ip="203.0.113.30", stamp="21/Nov/2026:09:09:00 +0800",
                               method="POST", path="/login", status=200, ua="Hydra/9.4"))
        result = analyze_lines(lines)
        alert = next(item for item in result["anomalies"] if item["category"] == "暴力破解")
        self.assertEqual(alert["severity"], "high")
        self.assertIn("随后出现 200", alert["reason"])

    def test_sample_has_over_ten_thousand_lines_and_parses(self):
        sample = ROOT / "data" / "sample_access.log"
        with sample.open(encoding="utf-8") as stream:
            result = analyze_lines(stream, source_name=sample.name)
        self.assertEqual(result["stats"]["total_lines"], 10_301)
        self.assertEqual(result["stats"]["parsed_lines"], 10_300)
        self.assertEqual(result["stats"]["malformed_lines"], 1)
        self.assertGreater(result["stats"]["anomaly_count"], 0)
        self.assertGreater(len(result["trend"]), 10)
        self.assertEqual(len(result["top_ips"]), 10)

    def test_csv_escapes_formula_like_values(self):
        from log_analyzer import export_anomalies_csv
        content = export_anomalies_csv([{
            "severity": "high", "severity_label": "高", "path": "=1+1", "ip": "192.0.2.1"
        }])
        self.assertTrue(content.startswith("\ufeff"))
        self.assertIn("'=1+1", content)


if __name__ == "__main__":
    unittest.main()
