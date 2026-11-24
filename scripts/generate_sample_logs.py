"""Create a deterministic, fictional Nginx combined log for the classroom demo."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "sample_access.log"
SEED = 20261124
START = datetime(2026, 11, 21, tzinfo=timezone(timedelta(hours=8)))

NORMAL_IPS = [f"192.0.2.{n}" for n in range(10, 210)]
NORMAL_PATHS = [
    "/", "/index.html", "/products", "/products/widget", "/products/gadget",
    "/search?q=monitor", "/search?q=keyboard", "/about", "/contact",
    "/assets/site.css", "/assets/app.js", "/assets/logo.svg",
    "/api/products", "/api/profile", "/login",
]
NORMAL_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
]


def line(ip: str, dt: datetime, method: str, path: str, status: int, size: int,
         ua: str, referer: str = "-") -> str:
    stamp = dt.strftime("%d/%b/%Y:%H:%M:%S %z")
    return f'{ip} - - [{stamp}] "{method} {path} HTTP/1.1" {status} {size} "{referer}" "{ua}"'


def build_lines() -> list[str]:
    rng = random.Random(SEED)
    rows: list[tuple[datetime, str]] = []

    # Ten thousand ordinary requests span one day and produce a useful hourly curve.
    for _ in range(10_007):
        minute = rng.randrange(24 * 60)
        second = rng.randrange(60)
        dt = START + timedelta(minutes=minute, seconds=second)
        method = rng.choices(["GET", "POST", "HEAD", "OPTIONS", "PUT"], [0.79, 0.10, 0.07, 0.025, 0.015])[0]
        path = rng.choice(NORMAL_PATHS)
        status = rng.choices([200, 206, 301, 304, 400, 401, 403, 404, 429, 500, 502],
                             [0.78, 0.03, 0.055, 0.075, 0.008, 0.004, 0.004, 0.035, 0.002, 0.004, 0.003])[0]
        if path == "/login" and method == "POST":
            status = rng.choices([200, 401], [0.82, 0.18])[0]
        size = rng.randint(180, 18_000) if status not in (204, 304) else 0
        referer = rng.choice(["-", "-", "https://shop.example.test/", "https://shop.example.test/products"])
        rows.append((dt, line(rng.choice(NORMAL_IPS), dt, method, path, status, size,
                              rng.choice(NORMAL_UAS), referer)))

    # Directory scanner: 220 404-heavy probes in a short interval.
    scan_paths = ["/.git/config", "/.env", "/phpmyadmin/", "/backup.zip", "/wp-login.php",
                  "/server-status", "/config.php", "/admin/", "/robots.txt", "/vendor/.env"]
    for i in range(220):
        dt = START + timedelta(hours=3, minutes=17, seconds=i * 5)
        path = scan_paths[i % len(scan_paths)] if i < len(scan_paths) else f"/admin/guess-{i:03d}"
        status = 200 if i in (4, 37) else 404
        rows.append((dt, line("198.51.100.23", dt, "GET", path, status, 282 if status == 404 else 1240,
                              "dirsearch/0.4.3")))

    # SQL injection probes include UNION, time delay and metadata signatures.
    sqli_paths = [
        "/products?id=1%20UNION%20SELECT%20password%20FROM%20users",
        "/search?q=%27%20OR%201%3D1--",
        "/products?id=1%20AND%20SLEEP%285%29",
        "/products?id=1%20information_schema.tables",
    ]
    for i in range(36):
        dt = START + timedelta(hours=3, minutes=39, seconds=i * 11)
        path = sqli_paths[i % len(sqli_paths)]
        status = 500 if i % 9 == 0 else 200
        rows.append((dt, line("203.0.113.44", dt, "GET", path, status, 1680,
                              "sqlmap/1.7.2#stable")))

    # Traversal attempts use both plain and percent-encoded variants.
    for i in range(22):
        dt = START + timedelta(hours=4, minutes=4, seconds=i * 13)
        path = "/download?file=../../../../etc/passwd" if i % 2 == 0 else "/download?file=%2e%2e%2f%2e%2e%2fetc%2fpasswd"
        rows.append((dt, line("203.0.113.58", dt, "GET", path, 404, 162, NORMAL_UAS[0])))

    # Login burst followed by a success: a high-priority scenario for the demo.
    for i in range(14):
        dt = START + timedelta(hours=4, minutes=35, seconds=i * 19)
        rows.append((dt, line("203.0.113.77", dt, "POST", "/login", 401, 189, "Hydra/9.4")))
    dt = START + timedelta(hours=4, minutes=40, seconds=45)
    rows.append((dt, line("203.0.113.77", dt, "POST", "/login", 200, 1204, "Hydra/9.4")))

    rows.sort(key=lambda item: item[0])
    return [text for _, text in rows] + ["this line is intentionally malformed to demonstrate parser tolerance"]


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(build_lines()) + "\n"
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Wrote {content.count(chr(10)):,} lines to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
