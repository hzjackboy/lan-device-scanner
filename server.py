#!/usr/bin/env python3
"""局域网设备扫描服务：Web 界面 + JSON API（纯标准库）。

    python3 server.py                 # 默认 0.0.0.0:8765
    python3 server.py --port 9000 --open

接口：
    GET    /                              页面
    GET    /api/status                    服务信息 & 本机网段
    GET    /api/interfaces                可扫描网段列表
    POST   /api/scan                      {"subnet": "10.0.0.0/24", "profile": "fast", "demo": false}
    GET    /api/scan/<id>                 当前结果快照
    GET    /api/scan/<id>/events          SSE 实时进度 + 结果
    DELETE /api/scan/<id>                 取消扫描
    GET    /api/scan/<id>/export?format=csv|json
    GET    /api/devices                   设备台账（含已掉线设备）
    POST   /api/devices/<key>             编辑台账里的设备（别名/分类/位置/标签/备注/类型）
    DELETE /api/devices/<key>             从台账删除
    GET    /api/devices/export            导出台账 csv|json
    GET    /api/history                   最近扫描记录
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import socket
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import oui  # noqa: E402
import scanner  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
VERSION = "1.0.0"

MANAGER = scanner.ScanManager(max_jobs=60)
# 设备台账：长期保存扫到过的设备（含已掉线的），支持人工编辑，落盘 data/devices.json
REGISTRY = scanner.DeviceRegistry(state_file=os.path.join(BASE_DIR, "data", "devices.json"))
def _archive_scan(job) -> None:
    if job.options.get("demo"):
        return                      # 演示模式的假设备不进真实台账
    REGISTRY.update_from_scan(job.snapshot(include_logs=False))

MANAGER.on_finish = _archive_scan
# 定时重扫：默认关，开启后由服务端按间隔自动跑（关掉页面也继续）
SCHEDULER = scanner.AutoScheduler(
    MANAGER,
    state_file=os.path.join(BASE_DIR, "data", "auto.json"),
    interval=3600,
)


def local_ips() -> list[str]:
    ips = []
    for iface in scanner.list_interfaces():
        if iface["ip"] not in ips:
            ips.append(iface["ip"])
    return ips


class Handler(BaseHTTPRequestHandler):
    server_version = f"LanScan/{VERSION}"
    protocol_version = "HTTP/1.1"

    # ---------------- 工具方法 ----------------
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        if self.path.startswith("/api/scan/") and "/events" in self.path:
            return
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str,
              extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, data: dict | list, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"ok": False, "error": message}, status)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return {}
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 65536))
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (ValueError, UnicodeDecodeError):
            return {}

    # ---------------- 路由 ----------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/status":
            self._json({
                "ok": True,
                "version": VERSION,
                "platform": sys.platform,
                "has_ping": scanner.HAS_PING,
                "is_root": os.geteuid() == 0 if hasattr(os, "geteuid") else False,
                "interfaces": scanner.list_interfaces(),
                "active_scan": (MANAGER.active().id if MANAGER.active() else None),
                "port_profiles": {k: len(v) for k, v in scanner.PORT_PROFILES.items()},
                "auto": SCHEDULER.snapshot(),
                "devices": REGISTRY.stats(),
            })
            return

        if path == "/api/auto":
            self._json({"ok": True, "auto": SCHEDULER.snapshot()})
            return

        if path == "/api/interfaces":
            self._json({"ok": True, "interfaces": scanner.list_interfaces()})
            return

        if path == "/api/devices":
            self._json({
                "ok": True,
                "devices": REGISTRY.list(),
                "stats": REGISTRY.stats(),
                "categories": REGISTRY.categories_list(),
            })
            return

        if path == "/api/devices/export":
            fmt = (query.get("format") or ["csv"])[0].lower()
            stamp = time.strftime("%Y%m%d-%H%M%S")
            if fmt == "json":
                body = json.dumps({"devices": REGISTRY.list(), "stats": REGISTRY.stats()},
                                  ensure_ascii=False, indent=2).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8", {
                    "Content-Disposition": f'attachment; filename="devices-{stamp}.json"',
                })
            else:
                body = scanner.export_registry_csv(REGISTRY).encode("utf-8-sig")
                self._send(200, body, "text/csv; charset=utf-8", {
                    "Content-Disposition": f'attachment; filename="devices-{stamp}.csv"',
                })
            return

        if path.startswith("/api/devices/"):
            key = urllib.parse.unquote(path[len("/api/devices/"):].strip("/"))
            rec = REGISTRY.get(key)
            if not rec:
                self._error("设备台账里没有这台设备", 404)
                return
            self._json({"ok": True, "device": rec})
            return

        if path == "/api/history":
            self._json({"ok": True, "scans": MANAGER.recent(60)})
            return

        if path == "/api/oui":
            mac = (query.get("mac") or [""])[0]
            self._json({"ok": True, "mac": mac, "vendor": oui.lookup(mac)})
            return

        if path.startswith("/api/scan/"):
            rest = path[len("/api/scan/"):]
            if rest.endswith("/events"):
                self._stream(rest[: -len("/events")])
                return
            if rest.endswith("/export"):
                self._export(rest[: -len("/export")], query)
                return
            job = MANAGER.get(rest)
            if not job:
                self._error("扫描任务不存在或已过期", 404)
                return
            self._json({"ok": True,
                        "scan": REGISTRY.apply_to_snapshot(job.snapshot())})
            return

        # 静态文件
        if path in ("/", "/index.html"):
            self._serve_file(os.path.join(STATIC_DIR, "index.html"))
            return
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            safe = os.path.normpath(rel).lstrip("/\\")
            if safe.startswith(".."):
                self._error("非法路径", 403)
                return
            self._serve_file(os.path.join(STATIC_DIR, safe))
            return

        self._error("Not Found", 404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/scan":
            payload = self._read_json()
            options = {
                "profile": payload.get("profile", "fast"),
                "demo": bool(payload.get("demo")),
                "ping": payload.get("ping", True),
                "mdns": payload.get("mdns", True),
                "netbios": payload.get("netbios", True),
                "resolve_names": payload.get("resolve_names", True),
            }
            if options["profile"] not in scanner.PORT_PROFILES:
                options["profile"] = "fast"
            try:
                job = MANAGER.start(payload.get("subnet") or "", options)
            except ValueError as exc:
                self._error(str(exc), 400)
                return
            except Exception as exc:  # noqa: BLE001
                self._error(f"启动扫描失败：{exc}", 500)
                return
            self._json({"ok": True, "scan_id": job.id, "subnet": job.subnet}, 201)
            return
        if parsed.path == "/api/auto":
            payload = self._read_json()
            try:
                state = SCHEDULER.configure(
                    enabled=payload.get("enabled"),
                    interval=payload.get("interval"),
                    subnet=payload.get("subnet"),
                    options=payload.get("options"),
                )
            except ValueError as exc:
                self._error(str(exc), 400)
                return
            if state["enabled"]:
                self.log_message("定时重扫已开启：每 %d 分钟一次 %s",
                                 max(1, state["interval"] // 60), state["subnet"] or "自动检测网段")
            else:
                self.log_message("定时重扫已关闭")
            self._json({"ok": True, "auto": state})
            return
        if parsed.path == "/api/auto/run":
            try:
                job = SCHEDULER.run_now()
            except ValueError as exc:
                self._error(str(exc), 409)
                return
            if not job:
                self._error(SCHEDULER.snapshot().get("last_error") or "无法启动扫描", 500)
                return
            self._json({"ok": True, "scan_id": job.id, "subnet": job.subnet}, 201)
            return
        if parsed.path.startswith("/api/devices/"):
            key = urllib.parse.unquote(parsed.path[len("/api/devices/"):].strip("/"))
            payload = self._read_json()
            rec = REGISTRY.update(key, payload, reset=bool(payload.get("reset")))
            if not rec:
                self._error("设备台账里没有这台设备", 404)
                return
            self._json({"ok": True, "device": rec})
            return
        self._error("Not Found", 404)

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/devices/"):
            key = urllib.parse.unquote(parsed.path[len("/api/devices/"):].strip("/"))
            if REGISTRY.delete(key):
                self._json({"ok": True})
            else:
                self._error("设备台账里没有这台设备", 404)
            return
        if parsed.path.startswith("/api/scan/"):
            scan_id = parsed.path[len("/api/scan/"):].strip("/")
            if MANAGER.cancel(scan_id):
                self._json({"ok": True})
            else:
                self._error("扫描任务不存在", 404)
            return
        self._error("Not Found", 404)

    # ---------------- 静态文件 ----------------
    def _serve_file(self, file_path: str) -> None:
        if not os.path.isfile(file_path):
            self._error("文件不存在", 404)
            return
        try:
            with open(file_path, "rb") as fh:
                body = fh.read()
        except OSError as exc:
            self._error(f"读取文件失败：{exc}", 500)
            return
        ctype, _ = mimetypes.guess_type(file_path)
        ctype = ctype or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, body, ctype)

    # ---------------- 导出 ----------------
    def _export(self, scan_id: str, query: dict) -> None:
        job = MANAGER.get(scan_id)
        if not job:
            self._error("扫描任务不存在", 404)
            return
        fmt = (query.get("format") or ["json"])[0].lower()
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(job.started_at))
        if fmt == "csv":
            body = scanner.export_csv(job).encode("utf-8-sig")
            self._send(200, body, "text/csv; charset=utf-8", {
                "Content-Disposition": f'attachment; filename="lan-scan-{stamp}.csv"',
            })
            return
        body = json.dumps(job.snapshot(include_logs=False), ensure_ascii=False,
                          indent=2).encode("utf-8")
        self._send(200, body, "application/json; charset=utf-8", {
            "Content-Disposition": f'attachment; filename="lan-scan-{stamp}.json"',
        })

    # ---------------- SSE ----------------
    def _stream(self, scan_id: str) -> None:
        job = MANAGER.get(scan_id)
        if not job:
            self._error("扫描任务不存在", 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        last_version = -1
        last_beat = time.time()
        try:
            while True:
                version = job.version
                if version != last_version:
                    last_version = version
                    payload = json.dumps(job.snapshot(), ensure_ascii=False)
                    self.wfile.write(f"event: scan\ndata: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    last_beat = time.time()
                    if job.state in ("done", "cancelled", "error"):
                        break
                elif time.time() - last_beat > 10:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    last_beat = time.time()
                time.sleep(0.25)
            self.wfile.write(b"event: end\ndata: {}\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def find_free_port(preferred: int) -> int:
    for port in (preferred, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("0.0.0.0", port))
                return probe.getsockname()[1]
        except OSError:
            continue
    return preferred


def main() -> int:
    parser = argparse.ArgumentParser(description="局域网设备扫描服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址，默认 0.0.0.0（局域网可访问）")
    parser.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")
    parser.add_argument("--open", action="store_true", help="启动后自动打开浏览器")
    args = parser.parse_args()

    port = args.port if args.port else find_free_port(0)
    try:
        httpd = Server((args.host, port), Handler)
    except OSError as exc:
        print(f"端口 {port} 无法绑定：{exc}", file=sys.stderr)
        fallback = find_free_port(0)
        httpd = Server((args.host, fallback), Handler)
        port = fallback
        print(f"已改用端口 {port}")

    print("=" * 58)
    print("  局域网设备扫描服务已启动")
    print("=" * 58)
    print(f"  本机访问 : http://127.0.0.1:{port}")
    for ip in local_ips():
        print(f"  局域网   : http://{ip}:{port}")
    print(f"  网段     : {', '.join(i['cidr'] for i in scanner.list_interfaces()) or '未检测到'}")
    print(f"  ping     : {'可用' if scanner.HAS_PING else '不可用（仅用 ARP/端口探测）'}")
    auto = SCHEDULER.snapshot()
    if auto["enabled"]:
        minutes = max(1, auto["interval"] // 60)
        print(f"  定时重扫 : 已开启，每 {minutes} 分钟一次"
              f"（{auto['subnet'] or '自动检测网段'}），下次约 "
              f"{max(0, (auto['next_run_in'] or 0)) // 60} 分钟后")
    else:
        print("  定时重扫 : 未开启（可在首页打开）")
    dev_stats = REGISTRY.stats()
    print(f"  设备台账 : 共 {dev_stats['total']} 台"
          f"（在线 {dev_stats['online']} / 离线 {dev_stats['offline']}）")
    print("  Ctrl+C 退出")
    print("=" * 58, flush=True)

    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        SCHEDULER.stop()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
