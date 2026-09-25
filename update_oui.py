#!/usr/bin/env python3
"""下载 IEEE 官方 OUI 列表，写到脚本同目录的 oui.csv。

内置的 OUI 表只覆盖常见厂商，跑一次这个脚本就能获得全量厂商识别
（约 3.5 万条，离线可用，之后扫描不再需要联网）。

    python3 update_oui.py
"""

from __future__ import annotations

import csv
import os
import ssl
import sys
import urllib.request

SOURCES = [
    "https://standards-oui.ieee.org/oui/oui.csv",
    "https://raw.githubusercontent.com/wireshark/wireshark/master/manuf",
]
TARGET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oui.csv")


def download(url: str, timeout: float = 30.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "lan-scanner/1.0"})
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return response.read()


def main() -> int:
    for url in SOURCES:
        print(f"下载 {url} …")
        try:
            raw = download(url)
        except Exception as exc:  # noqa: BLE001
            print(f"  失败：{exc}")
            continue

        text = raw.decode("utf-8", "replace")
        rows: list[tuple[str, str, str]] = []
        if url.endswith("oui.csv"):
            reader = csv.reader(text.splitlines())
            next(reader, None)
            for row in reader:
                if len(row) >= 3 and len(row[1].strip()) >= 6:
                    rows.append((row[0], row[1].strip().upper(), row[2].strip()))
        else:
            # Wireshark manuf 格式：AA:BB:CC<TAB>厂商短名<TAB>厂商全名
            for line in text.splitlines():
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 2 and ":" in parts[0]:
                    prefix = parts[0].split("/")[0].replace(":", "").upper()
                    if len(prefix) >= 6:
                        rows.append(("MA-L", prefix, parts[-1].strip() or parts[1].strip()))

        if not rows:
            print("  内容为空，换下一个源")
            continue

        with open(TARGET, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["Registry", "Assignment", "Organization Name"])
            writer.writerows(rows)
        print(f"  已写入 {TARGET}（{len(rows)} 条厂商记录）")
        return 0

    print("所有源都失败了：请检查网络后重试，或继续使用内置厂商表。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
