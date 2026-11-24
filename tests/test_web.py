from __future__ import annotations

import io
import unittest

import app as webapp


class WebApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = webapp.app.test_client()

    def test_dashboard_and_summary_load(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("LogScope", page.get_data(as_text=True))
        summary = self.client.get("/api/summary")
        self.assertEqual(summary.status_code, 200)
        self.assertGreater(summary.json["stats"]["total_requests"], 10_000)

    def test_filtering_csv_and_upload_validation(self):
        high = self.client.get("/api/anomalies?severity=high&page_size=5")
        self.assertEqual(high.status_code, 200)
        self.assertLessEqual(len(high.json["items"]), 5)
        self.assertTrue(all(item["severity"] == "high" for item in high.json["items"]))

        csv_response = self.client.get("/api/anomalies/export.csv?severity=high")
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("text/csv", csv_response.content_type)
        self.assertTrue(csv_response.data.startswith(b"\xef\xbb\xbf"))

        rejected = self.client.post("/api/upload", data={
            "logfile": (io.BytesIO(b"bad"), "notes.csv")
        }, content_type="multipart/form-data")
        self.assertEqual(rejected.status_code, 400)

    def test_upload_combined_log(self):
        sample_line = b'192.0.2.2 - - [21/Nov/2026:09:00:00 +0800] "GET / HTTP/1.1" 200 120 "-" "Mozilla/5.0"\n'
        uploaded = self.client.post("/api/upload", data={
            "logfile": (io.BytesIO(sample_line), "quick-check.log")
        }, content_type="multipart/form-data")
        self.assertEqual(uploaded.status_code, 200)
        self.assertEqual(uploaded.json["stats"]["total_requests"], 1)
        self.client.post("/api/sample")


if __name__ == "__main__":
    unittest.main()
