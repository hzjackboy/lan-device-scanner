"""局域网设备扫描引擎（纯标准库，不需要 root）。

发现思路（非 root 也能拿到 MAC）：
1. 读 ARP 缓存，先把已知设备列出来；
2. 向整个网段发 UDP 包"逼"内核做 ARP 解析，再读一次 ARP 表 —— 这一步能发现
   禁 ping 的设备，在局域网里非常有效；
3. ICMP 并发 ping，拿到延迟，同时补上 ARP 表里没有的在线设备；
4. mDNS 浏览常见服务（AirPlay/GoogleCast/IPP/HomeKit...），把设备名和服务映射到 IP；
5. 反向 DNS / NetBIOS 取名，再对常见 TCP 端口做 connect 扫描做设备指纹。
"""

from __future__ import annotations

import csv
import io
import ipaddress
import json
import os
import platform
import random
import re
import shutil
import socket
import subprocess
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field

import mdns
import netbios
import oui

IS_MACOS = platform.system() == "Darwin"
HAS_PING = shutil.which("ping") is not None

# 扫描档位：fast 只探最常见的端口，full 覆盖更多
PORT_PROFILES: dict[str, list[int]] = {
    "fast": [22, 80, 443, 445, 3389, 5000, 554, 8080, 62078, 9100],
    "full": [
        9, 21, 22, 23, 25, 53, 80, 111, 135, 139, 161, 443, 445, 515, 548, 554,
        587, 631, 873, 902, 993, 1080, 1194, 1433, 1723, 1883, 2049, 2375, 3000,
        3128, 3306, 3389, 5000, 5001, 5060, 5357, 5432, 5555, 5672, 5683, 5900,
        5984, 6379, 6443, 7000, 8000, 8008, 8009, 8060, 8080, 8081, 8123, 8443,
        8883, 8888, 9000, 9090, 9100, 9200, 10000, 11211, 27017, 32400, 37777,
        49152, 49153, 62078,
    ],
}

MAX_HOSTS = 4096



# --------------------------------------------------------------------------
# 本机网络信息
# --------------------------------------------------------------------------

def _parse_macos_ifconfig(text: str) -> list[dict]:
    ifaces: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        if line and not line[0].isspace():
            name = line.split(":", 1)[0].strip()
            flags = ""
            m = re.search(r"flags=\d+<([^>]*)>", line)
            if m:
                flags = m.group(1)
            current = {"name": name, "flags": flags, "ip": "", "netmask": "", "broadcast": ""}
            ifaces.append(current)
            continue
        if current is None:
            continue
        m = re.search(r"\sinet (\d+\.\d+\.\d+\.\d+)", line)
        if m and not current["ip"]:
            current["ip"] = m.group(1)
            nm = re.search(r"netmask (\S+)", line)
            if nm:
                current["netmask"] = nm.group(1)
            bc = re.search(r"broadcast (\d+\.\d+\.\d+\.\d+)", line)
            if bc:
                current["broadcast"] = bc.group(1)
    return ifaces


def _parse_linux_ifconfig(text: str) -> list[dict]:
    ifaces: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        if line and not line[0].isspace():
            current = {"name": line.split()[0].split(":")[0], "flags": "", "ip": "",
                       "netmask": "", "broadcast": ""}
            ifaces.append(current)
            continue
        if current is None or current["ip"]:
            continue
        m = re.search(r"inet (?:addr:)?(\d+\.\d+\.\d+\.\d+)", line)
        if m:
            current["ip"] = m.group(1)
            nm = re.search(r"(?:Mask|netmask):?(\d+\.\d+\.\d+\.\d+)", line)
            if nm:
                current["netmask"] = nm.group(1)
            bc = re.search(r"(?:Bcast|broadcast):?(\d+\.\d+\.\d+\.\d+)", line)
            if bc:
                current["broadcast"] = bc.group(1)
    return ifaces


def _netmask_to_prefix(mask: str) -> int:
    if not mask:
        return 24
    if mask.startswith("0x"):
        try:
            value = int(mask, 16)
        except ValueError:
            return 24
        return bin(value).count("1")
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
    except Exception:
        return 24


def default_interface() -> str:
    """默认路由所用网卡名。"""
    try:
        if IS_MACOS:
            out = subprocess.run(["route", "-n", "get", "default"], capture_output=True,
                                 text=True, timeout=3).stdout
            m = re.search(r"interface:\s*(\S+)", out)
            return m.group(1) if m else ""
        out = subprocess.run(["ip", "route", "show", "default"], capture_output=True,
                             text=True, timeout=3).stdout
        m = re.search(r"dev\s+(\S+)", out)
        return m.group(1) if m else ""
    except Exception:
        return ""


def list_interfaces() -> list[dict]:
    """列出所有可扫描的 IPv4 网段，默认网卡排在最前。"""
    try:
        if IS_MACOS:
            out = subprocess.run(["ifconfig", "-a"], capture_output=True, text=True,
                                 timeout=5).stdout
            raw = _parse_macos_ifconfig(out)
        else:
            try:
                out = subprocess.run(["ip", "-o", "-4", "addr", "show"], capture_output=True,
                                     text=True, timeout=5).stdout
                raw = []
                for line in out.splitlines():
                    m = re.match(r"\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", line)
                    if m:
                        raw.append({"name": m.group(1), "flags": "UP", "ip": m.group(2),
                                    "netmask": "/" + m.group(3), "broadcast": ""})
            except FileNotFoundError:
                out = subprocess.run(["ifconfig", "-a"], capture_output=True, text=True,
                                     timeout=5).stdout
                raw = _parse_linux_ifconfig(out)
    except Exception:
        raw = []

    default_if = default_interface()
    skip_prefixes = ("lo", "utun", "gif", "stf", "awdl", "llw", "anpi", "ap", "vmenet", "docker", "br-")
    result: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        name = item["name"]
        ip = item.get("ip") or ""
        if not ip or ip.startswith("127.") or ":" in ip:
            continue
        if any(name.startswith(p) for p in skip_prefixes):
            continue
        mask = item.get("netmask") or ""
        prefix = int(mask[1:]) if mask.startswith("/") else _netmask_to_prefix(mask)
        try:
            netmask = str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)
        except Exception:
            prefix, netmask = 24, "255.255.255.0"
        try:
            network = ipaddress.IPv4Network(f"{ip}/{prefix}", strict=False)
        except Exception:
            continue
        if network.num_addresses < 4:
            continue
        cidr = str(network)
        key = f"{name}|{cidr}"
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "name": name,
            "ip": ip,
            "netmask": netmask,
            "prefix": prefix,
            "cidr": cidr,
            "hosts": max(0, network.num_addresses - 2),
            "is_default": name == default_if,
            "is_private": network.is_private,
        })

    result.sort(key=lambda x: (not x["is_default"], not x["is_private"], x["name"]))
    return result


def hosts_in_subnet(cidr: str) -> list[str]:
    network = ipaddress.IPv4Network(cidr, strict=False)
    if network.num_addresses > MAX_HOSTS:
        raise ValueError(f"网段太大（{network.num_addresses} 个地址），请用 /20 以内的网段")
    if network.prefixlen >= 31:
        return [str(h) for h in network.hosts()] or [str(network.network_address)]
    return [str(h) for h in network.hosts()]


# --------------------------------------------------------------------------
# 底层探测
# --------------------------------------------------------------------------

def normalize_mac(raw: str) -> str:
    """把 MAC 统一成 "AA:BB:CC:DD:EE:FF"（具体解析在 oui.normalize）。"""
    hexs = oui.normalize(raw)
    if not hexs:
        return ""
    return ":".join(hexs[i:i + 2] for i in range(0, 12, 2))


def arp_table() -> dict[str, dict]:
    """读系统 ARP 表，返回 {ip: {mac, iface}}。"""
    table: dict[str, dict] = {}
    try:
        out = subprocess.run(["arp", "-an"], capture_output=True, text=True, timeout=6).stdout
    except Exception:
        out = ""
    for line in out.splitlines():
        m = re.match(r"\S*\s*\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+(\S+)(?:\s+on\s+(\S+))?", line)
        if not m:
            continue
        ip, mac, iface = m.group(1), m.group(2), m.group(3) or ""
        if mac.lower().startswith("(incomplete") or mac.lower().startswith("incomplete"):
            continue
        normalized = normalize_mac(mac)
        if not normalized:
            continue
        table[ip] = {"mac": normalized, "iface": iface}
    if not table and os.path.exists("/proc/net/arp"):
        try:
            with open("/proc/net/arp", encoding="utf-8") as fh:
                next(fh, None)
                for line in fh:
                    parts = line.split()
                    if len(parts) >= 6 and parts[3] != "00:00:00:00:00:00":
                        table[parts[0]] = {"mac": parts[3].lower(), "iface": parts[5]}
        except Exception:
            pass
    return table


def arp_prime(ips: list[str], workers: int = 64) -> None:
    """对每个 IP 发一个 UDP 包，触发内核 ARP 解析（不需要 root）。"""
    def probe(ip: str) -> None:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.05)
            sock.connect((ip, 9))
            sock.send(b"\x00")
        except OSError:
            pass
        finally:
            if sock is not None:
                sock.close()

    with ThreadPoolExecutor(max_workers=min(workers, max(1, len(ips)))) as pool:
        list(pool.map(probe, ips))


def ping_once(ip: str, timeout_ms: int = 800) -> tuple[bool, float | None]:
    """返回 (是否在线, 延迟毫秒)。"""
    if not HAS_PING:
        return False, None
    if IS_MACOS:
        cmd = ["ping", "-c", "1", "-n", "-W", str(timeout_ms), "-t", "2", ip]
    else:
        cmd = ["ping", "-c", "1", "-n", "-W", str(max(1, int(round(timeout_ms / 1000)))), ip]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout_ms / 1000 + 2.5)
    except Exception:
        return False, None
    if proc.returncode != 0:
        return False, None
    m = re.search(r"time[=<]([\d.]+)\s*ms", proc.stdout)
    return True, float(m.group(1)) if m else None


def tcp_probe(ip: str, port: int, timeout: float = 0.4) -> bool:
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        return sock.connect_ex((ip, port)) == 0
    except OSError:
        return False
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def reverse_dns(ip: str, timeout: float = 0.8) -> str | None:
    result: list[str] = []

    def work() -> None:
        try:
            name = socket.gethostbyaddr(ip)[0]
            result.append(name)
        except Exception:
            pass

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(timeout)
    if not result:
        return None
    name = result[0].rstrip(".")
    if name.endswith(".local"):
        name = name[: -len(".local")]
    elif "." in name:
        # 普通域名取主机名部分更好看
        name = name.split(".")[0]
    return name or None


def guess_kind_from_services(services: list[str], hostname: str = "") -> str:
    """仅按 mDNS 服务名 + 主机名推断（真正的合并逻辑在 oui.infer_kind）。"""
    return oui.infer_kind("", hostname, [], services)


_JUNK_HOSTNAMES = {
    "", "-", "none", "(none)", "(none)-2", "unknown", "localhost", "localdomain",
    "workgroup", "mshome", "home", "*", "nan", "null", "host", "android",
}
_HOSTNAME_RE = re.compile(r"^[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff._\- ()]{0,48}$")


def clean_hostname(name: str | None) -> str:
    """过滤掉 "(none)"、"WORKGROUP" 这类没用的名字。"""
    if not name:
        return ""
    text = str(name).strip().strip(".")
    if text.lower() in _JUNK_HOSTNAMES:
        return ""
    if not _HOSTNAME_RE.match(text):
        return ""
    if text.lower().startswith(("(none", "unknown", "n/a")):
        return ""
    return text


# --------------------------------------------------------------------------
# 设备与任务
# --------------------------------------------------------------------------

@dataclass
class Device:
    ip: str
    mac: str = ""
    vendor: str = ""
    hostname: str = ""
    kind: str = ""
    ports: list[int] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    rtt_ms: float | None = None
    iface: str = ""
    online: bool = True
    confirmed: bool = False          # 是否被 ping/端口/ARP 明确确认过
    only_arp: bool = False           # 只有 ARP 缓存，可能是过期记录
    sources: list[str] = field(default_factory=list)
    note: str = ""
    last_seen: float = field(default_factory=time.time)

    def merge_source(self, source: str) -> None:
        if source not in self.sources:
            self.sources.append(source)


class ScanJob:
    """一次扫描任务，进度和结果都可以随时快照给前端。"""

    def __init__(self, scan_id: str, subnet: str, options: dict | None = None):
        self.id = scan_id
        self.subnet = subnet
        self.options = {
            "profile": "fast",
            "ping": True,
            "mdns": True,
            "netbios": True,
            "resolve_names": True,
            "demo": False,
        }
        if options:
            self.options.update({k: v for k, v in options.items() if v is not None})
        self.state = "pending"          # pending | running | done | cancelled | error
        self.phase = "排队中"
        self.error = ""
        self.started_at = time.time()
        self.finished_at: float | None = None
        self.progress = {"done": 0, "total": 0, "percent": 0}
        self.devices: dict[str, Device] = {}
        self.logs: deque[dict] = deque(maxlen=400)
        self.total_hosts = 0
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._version = 0
        self._phase_range = (0, 5)

    # ---------------- 内部状态 ----------------
    @property
    def version(self) -> int:
        """每次结果变化都会 +1，前端据此判断要不要重绘。"""
        return self._version

    def touch(self) -> None:
        with self._lock:
            self._version += 1

    def log(self, message: str, level: str = "info") -> None:
        with self._lock:
            self.logs.append({"ts": time.time(), "level": level, "msg": message})
            self._version += 1

    def set_phase(self, name: str, start: int, end: int) -> None:
        with self._lock:
            self.phase = name
            self._phase_range = (start, end)
            self.progress["done"] = 0
            self.progress["total"] = 0
            self.progress["percent"] = start
            self._version += 1

    def bump(self, done: int | None = None, total: int | None = None) -> None:
        with self._lock:
            if done is not None:
                self.progress["done"] = done
            if total is not None:
                self.progress["total"] = total
            start, end = self._phase_range
            t = self.progress["total"]
            d = self.progress["done"]
            ratio = (d / t) if t else 0
            self.progress["percent"] = int(start + (end - start) * min(1.0, max(0.0, ratio)))
            self._version += 1

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self) -> None:
        self._cancel.set()
        self.log("收到取消请求，正在停止…", "warn")
        self.touch()

    def device(self, ip: str) -> Device:
        with self._lock:
            dev = self.devices.get(ip)
            if dev is None:
                dev = Device(ip=ip)
                self.devices[ip] = dev
                self._version += 1
            dev.last_seen = time.time()
            return dev

    # ---------------- 快照 ----------------
    def stats(self) -> dict:
        devices = list(self.devices.values())
        kinds: dict[str, int] = {}
        vendors: dict[str, int] = {}
        for dev in devices:
            if dev.kind:
                kinds[dev.kind] = kinds.get(dev.kind, 0) + 1
            if dev.vendor:
                vendors[dev.vendor] = vendors.get(dev.vendor, 0) + 1
        return {
            "total": len(devices),
            "online": sum(1 for d in devices if d.online and not d.only_arp),
            "arp_only": sum(1 for d in devices if d.only_arp),
            "with_mac": sum(1 for d in devices if d.mac),
            "named": sum(1 for d in devices if d.hostname),
            "kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
            "vendors": dict(sorted(vendors.items(), key=lambda kv: -kv[1])[:12]),
        }

    def snapshot(self, include_logs: bool = True) -> dict:
        with self._lock:
            devices = []
            for dev in self.devices.values():
                record = asdict(dev)
                if not record["vendor"]:
                    record["vendor"] = oui.lookup(record["mac"]) if record["mac"] else "—"
                if not record["kind"]:
                    record["kind"] = oui.infer_kind(record["vendor"], record["hostname"],
                                                    record["ports"], record["services"])
                devices.append(record)
            devices.sort(key=lambda d: tuple(int(x) for x in d["ip"].split(".")) if
                         all(p.isdigit() for p in d["ip"].split(".")) else (0,))
            payload = {
                "id": self.id,
                "subnet": self.subnet,
                "state": self.state,
                "phase": self.phase,
                "error": self.error,
                "progress": dict(self.progress),
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "duration": (self.finished_at or time.time()) - self.started_at,
                "total_hosts": self.total_hosts,
                "options": dict(self.options),
                "devices": devices,
                "stats": self.stats(),
                "version": self._version,
            }
            if include_logs:
                payload["logs"] = list(self.logs)[-60:]
            return payload

    # ---------------- 主流程 ----------------
    def run(self) -> None:
        try:
            self.state = "running"
            self.log(f"开始扫描 {self.subnet}（档位：{self.options['profile']}）")
            if self.options.get("demo"):
                self._run_demo()
            else:
                self._run_real()
            if self.cancelled() and self.state == "running":
                self.state = "cancelled"
                self.phase = "已取消"
            elif self.state == "running":
                self.state = "done"
                self.phase = "完成"
                self.progress["percent"] = 100
        except Exception as exc:  # noqa: BLE001
            self.state = "error"
            self.error = str(exc)
            self.log(f"扫描出错：{exc}", "error")
        finally:
            self.finished_at = time.time()
            self.touch()

    def _run_real(self) -> None:
        hosts = hosts_in_subnet(self.subnet)
        self.total_hosts = len(hosts)
        self.log(f"目标网段共 {len(hosts)} 个地址")
        prefix = ".".join(hosts[0].split(".")[:3]) + "."

        # ---- 1. ARP 缓存 ----
        self.set_phase("读取 ARP 缓存", 0, 4)
        cached = arp_table()
        host_set = set(hosts)
        in_subnet = {ip: info for ip, info in cached.items() if ip in host_set}
        self.log(f"ARP 缓存中有 {len(in_subnet)} 条属于目标网段的记录")
        for ip, info in in_subnet.items():
            dev = self.device(ip)
            dev.mac = info["mac"]
            dev.vendor = oui.lookup(info["mac"])
            dev.iface = info["iface"]
            dev.only_arp = True
            dev.merge_source("arp-cache")
        self.bump(done=1, total=1)

        if self.cancelled():
            return

        # ---- 2. UDP 触发 ARP，发现禁 ping 设备 ----
        self.set_phase("ARP 探测整个网段", 4, 30)
        self.log("发送 UDP 探测包以触发 ARP 解析…")
        self.bump(done=0, total=len(hosts))
        batch = 256
        for start in range(0, len(hosts), batch):
            if self.cancelled():
                return
            chunk = hosts[start:start + batch]
            arp_prime(chunk)
            self.bump(done=min(len(hosts), start + len(chunk)))
        time.sleep(0.4)
        fresh = arp_table()
        added = 0
        fresh_in_subnet = 0
        for ip, info in fresh.items():
            if ip not in host_set or not info["mac"]:
                continue
            fresh_in_subnet += 1
            dev = self.device(ip)
            if not dev.mac:
                added += 1
            dev.mac = info["mac"]
            dev.vendor = oui.lookup(info["mac"])
            dev.iface = info["iface"] or dev.iface
            dev.only_arp = False
            dev.confirmed = True
            dev.merge_source("arp")
        self.log(f"ARP 应答设备 {fresh_in_subnet} 台（新增 {added} 台）")

        if self.cancelled():
            return

        # ---- 3. ICMP 扫描 ----
        if self.options.get("ping", True) and HAS_PING:
            self.set_phase("ICMP 扫描", 30, 55)
            self.log("开始 ping 扫描，拿延迟数据…")
            workers = min(160, max(32, len(hosts) // 2))
            done = 0
            self.bump(done=0, total=len(hosts))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(ping_once, ip, 800): ip for ip in hosts}
                for future in as_completed(futures):
                    ip = futures[future]
                    done += 1
                    if done % 8 == 0 or done == len(hosts):
                        self.bump(done=done)
                    if self.cancelled():
                        for f in futures:
                            f.cancel()
                        return
                    try:
                        alive, rtt = future.result()
                    except Exception:
                        alive, rtt = False, None
                    if alive:
                        dev = self.device(ip)
                        dev.rtt_ms = rtt
                        dev.online = True
                        dev.confirmed = True
                        dev.only_arp = False
                        dev.merge_source("icmp")
            self.log(f"ping 通 {len([d for d in self.devices.values() if 'icmp' in d.sources])} 台")
        elif not HAS_PING:
            self.log("系统里没有 ping 命令，跳过 ICMP 扫描", "warn")

        # ping 之后内核一定已经把应答方的 ARP 条目写进缓存了，补一次 MAC
        missing = [d.ip for d in self.devices.values() if not d.mac]
        if missing:
            time.sleep(0.3)
            late = arp_table()
            filled = 0
            for ip in missing:
                info = late.get(ip)
                if not info or not info["mac"]:
                    continue
                dev = self.device(ip)
                dev.mac = info["mac"]
                dev.vendor = oui.lookup(info["mac"])
                dev.iface = dev.iface or info["iface"]
                dev.merge_source("arp")
                filled += 1
            if filled:
                self.log(f"从 ARP 表补全 {filled} 台设备的 MAC 地址")

        if self.cancelled():
            return

        # ---- 4. mDNS 浏览 ----
        if self.options.get("mdns", True):
            self.set_phase("mDNS / Bonjour 浏览", 55, 70)
            self.bump(done=0, total=1)
            try:
                found = mdns.browse(ip_filter=prefix, timeout=2.2)
            except Exception as exc:  # noqa: BLE001
                found = {}
                self.log(f"mDNS 浏览失败：{exc}", "warn")
            for ip, info in found.items():
                dev = self.device(ip)
                name = clean_hostname(info.get("name"))
                if name and not dev.hostname:
                    dev.hostname = name
                    dev.merge_source("mdns")
                if info.get("services"):
                    dev.services = sorted(set(dev.services) | set(info["services"]))
                txt = info.get("txt") or {}
                model = txt.get("model") or txt.get("md") or txt.get("ty")
                if model and not dev.note:
                    dev.note = model
                dev.merge_source("mdns")
            self.log(f"mDNS 发现 {len(found)} 台有服务的设备")
            self.bump(done=1, total=1)

        if self.cancelled():
            return

        # ---- 5. 逐台补充信息：主机名 ----
        targets = sorted(self.devices.values(),
                         key=lambda d: tuple(int(x) for x in d.ip.split(".")))
        ports = PORT_PROFILES.get(self.options.get("profile", "fast"), PORT_PROFILES["fast"])
        self.set_phase("解析主机名", 70, 80)
        self.bump(done=0, total=max(1, len(targets)))
        self._run_pool(targets, self._enrich)

        if self.cancelled():
            return

        # ---- 6. 端口指纹 ----
        if ports:
            self.set_phase("端口指纹扫描", 80, 99)
            pairs = [(dev.ip, ports) for dev in targets]
            self.bump(done=0, total=max(1, len(pairs)))
            done = 0
            workers = min(24, max(4, len(pairs)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(self._scan_ports, ip, port_list) for ip, port_list in pairs]
                for future in as_completed(futures):
                    done += 1
                    self.bump(done=done)
                    if self.cancelled():
                        for f in futures:
                            f.cancel()
                        return
                    try:
                        future.result()
                    except Exception as exc:  # noqa: BLE001
                        self.log(f"端口扫描出错：{exc}", "warn")
        else:
            self.set_phase("完成扫描", 80, 99)
            self.bump(done=1, total=1)

        # ---- 收尾：ARP 缓存里没确认过的条目降级 ----
        for dev in self.devices.values():
            if dev.only_arp and not dev.confirmed:
                dev.note = dev.note or "仅 ARP 缓存记录，未确认在线"
        self.devices = {ip: d for ip, d in self.devices.items() if d.mac or d.confirmed}

    def _run_pool(self, devices: list["Device"], func) -> None:
        """并发跑一批 ip，并更新进度。"""
        if not devices:
            return
        done = 0
        workers = min(48, max(4, len(devices)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(func, dev.ip): dev.ip for dev in devices}
            for future in as_completed(futures):
                done += 1
                self.bump(done=done)
                if self.cancelled():
                    for f in futures:
                        f.cancel()
                    return
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001
                    self.log(f"{futures[future]} 补充扫描失败：{exc}", "warn")

    def _enrich(self, ip: str) -> None:
        """补充主机名（反向 DNS → NetBIOS → mDNS）。"""
        dev = self.device(ip)
        options = self.options

        if options.get("resolve_names", True) and not dev.hostname:
            try:
                name = clean_hostname(reverse_dns(ip, timeout=0.8))
                if name:
                    dev.hostname = name
                    dev.merge_source("dns")
            except Exception:
                pass

        if options.get("netbios", True) and not dev.hostname:
            try:
                nb = clean_hostname(netbios.node_status(ip, timeout=0.6))
                if nb:
                    dev.hostname = nb
                    dev.note = dev.note or "NetBIOS 名称"
                    dev.merge_source("netbios")
            except Exception:
                pass

        if options.get("mdns", True) and not dev.hostname:
            try:
                name = clean_hostname(mdns.reverse_lookup(ip, timeout=0.8))
                if name:
                    dev.hostname = name
                    dev.merge_source("mdns")
            except Exception:
                pass

        dev.vendor = dev.vendor or (oui.lookup(dev.mac) if dev.mac else "")
        self.touch()

    def _scan_ports(self, ip: str, ports: list[int]) -> None:
        dev = self.device(ip)
        open_ports: list[int] = []
        with ThreadPoolExecutor(max_workers=min(12, len(ports))) as pool:
            futures = {pool.submit(tcp_probe, ip, port, 0.4): port for port in ports}
            for future in as_completed(futures):
                port = futures[future]
                try:
                    if future.result():
                        open_ports.append(port)
                except Exception:
                    pass
        if open_ports:
            dev.ports = sorted(open_ports)
            dev.confirmed = True
            dev.online = True
            dev.only_arp = False
            dev.merge_source("tcp")
        elif dev.mac and not dev.confirmed:
            # ARP 已经证明设备在，只是没开常见端口 / 屏蔽了 ICMP
            dev.online = True
            dev.confirmed = True
            dev.merge_source("arp")
        dev.kind = dev.kind or oui.infer_kind(dev.vendor, dev.hostname, dev.ports, dev.services)
        self.touch()

    # ---------------- 演示模式 ----------------
    def _run_demo(self) -> None:
        """没有真实局域网也能看效果：编造一批合理设备，边扫边出。"""
        network = ipaddress.IPv4Network(self.subnet, strict=False)
        base = str(network.network_address).rsplit(".", 1)[0]
        samples = [
            ("1", "3C:46:D8:11:22:33", "TP-Link", ["80", "443", "53"], "gateway.local", "路由器 / 网关", 1.2),
            ("2", "A4:83:E7:11:22:33", "小米", ["80", "8080"], "xiaomi-router", "路由器 / AP", 2.4),
            ("12", "F0:18:98:AA:BB:CC", "Apple", ["62078", "22"], "MacBook-Pro", "电脑", 3.1),
            ("15", "B8:27:EB:44:55:66", "Raspberry Pi", ["22", "8123", "1883"], "homeassistant", "智能家居中枢 (Home Assistant)", 0.9),
            ("18", "DC:A6:32:77:88:99", "Raspberry Pi", ["22", "80"], "pi-hole", "Linux 服务器", 1.4),
            ("23", "8C:85:90:12:34:56", "Apple", ["62078"], "iPhone-15", "手机", 5.6),
            ("24", "3C:5A:B4:65:43:21", "Google", ["8008", "8009"], "Chromecast-客厅", "Chromecast / 投屏", 8.2),
            ("31", "00:17:88:AB:CD:EF", "Signify (Philips Hue)", ["80", "443"], "Hue-Bridge", "智能灯", 2.8),
            ("42", "B0:95:75:11:22:33", "TP-Link", ["9999"], "smart-plug", "物联网设备", 12.5),
            ("55", "AC:84:C6:DE:AD:BE", "TP-Link", ["80", "443"], "wifi-ap-2f", "路由器 / AP", 4.4),
            ("77", "00:1B:A9:12:34:56", "Brother", ["9100", "515", "631"], "BRW-Printer", "打印机", 6.7),
            ("88", "44:19:B6:AA:BB:CC", "海康威视", ["554", "8000", "80"], "IPC-门口", "网络摄像头", 3.9),
            ("101", "24:0A:C4:33:44:55", "Espressif", ["1883"], "esp32-sensor", "MQTT 物联网设备", 15.3),
            ("120", "78:11:DC:66:77:88", "小米", ["54321"], "yeelight-卧室", "智能灯", 9.8),
            ("150", "54:60:09:AA:BB:CC", "Google", ["8009"], "Google-Home", "智能音箱", 7.1),
            ("200", "00:1C:B3:12:34:56", "Apple", ["22", "445"], "TimeCapsule", "NAS / 存储", 2.0),
            ("233", "1C:39:47:99:88:77", "Lenovo", ["3389", "445", "139"], "DESKTOP-7F3K2", "Windows 电脑 / NAS", 1.8),
        ]
        ports_total = max(1, len(samples) * 10)
        self.total_hosts = network.num_addresses - 2

        self.set_phase("读取 ARP 缓存", 0, 4)
        self.log("演示模式：使用内置示例设备，不发送任何真实网络请求", "warn")
        time.sleep(0.3)
        self.bump(done=1, total=1)

        self.set_phase("ARP 探测整个网段", 4, 30)
        self.bump(done=0, total=self.total_hosts)
        for i in range(0, self.total_hosts, 16):
            if self.cancelled():
                return
            self.bump(done=min(self.total_hosts, i + 16))
            time.sleep(0.05)
        self.log(f"ARP 应答设备 {len(samples)} 台")

        self.set_phase("ICMP 扫描", 30, 55)
        self.bump(done=0, total=self.total_hosts)
        for i in range(0, self.total_hosts, 16):
            if self.cancelled():
                return
            self.bump(done=min(self.total_hosts, i + 16))
            time.sleep(0.04)

        self.set_phase("mDNS / Bonjour 浏览", 55, 70)
        self.bump(done=0, total=1)
        time.sleep(0.5)
        self.bump(done=1, total=1)

        self.set_phase("主机名与端口指纹", 70, 99)
        self.bump(done=0, total=ports_total)
        done = 0
        for host, mac, vendor, open_ports, hostname, kind, rtt in samples:
            if self.cancelled():
                return
            dev = self.device(f"{base}.{host}")
            dev.mac = mac
            dev.vendor = vendor
            dev.hostname = hostname
            dev.kind = kind
            dev.ports = [int(p) for p in open_ports]
            dev.rtt_ms = rtt
            dev.online = True
            dev.confirmed = True
            dev.merge_source("demo")
            self.log(f"发现 {dev.ip}  {vendor}  {hostname}")
            done += 10
            self.bump(done=min(ports_total, done))
            time.sleep(0.22)


# --------------------------------------------------------------------------
# 任务管理
# --------------------------------------------------------------------------

class ScanManager:
    def __init__(self, max_jobs: int = 30, on_finish=None):
        self._jobs: dict[str, ScanJob] = {}
        self._order: deque[str] = deque()
        self._lock = threading.RLock()
        self._max_jobs = max_jobs
        self.on_finish = on_finish          # 每次扫描结束后回调，用来归档设备

    def start(self, subnet: str, options: dict | None = None) -> ScanJob:
        subnet = (subnet or "").strip()
        if not subnet:
            ifaces = list_interfaces()
            if not ifaces:
                raise ValueError("没有找到可用的局域网网段，请手动填写")
            subnet = ifaces[0]["cidr"]
        if "/" not in subnet:
            subnet = subnet + "/24"
        network = ipaddress.IPv4Network(subnet, strict=False)
        scan_id = uuid.uuid4().hex[:12]
        job = ScanJob(scan_id, str(network), options)
        with self._lock:
            self._jobs[scan_id] = job
            self._order.append(scan_id)
            while len(self._order) > self._max_jobs:
                old = self._order.popleft()
                old_job = self._jobs.get(old)
                if old_job and old_job.state == "running":
                    self._order.append(old)
                    break
                self._jobs.pop(old, None)

        def runner() -> None:
            try:
                job.run()
            finally:
                if self.on_finish is not None:
                    try:
                        self.on_finish(job)
                    except Exception:  # noqa: BLE001
                        pass

        thread = threading.Thread(target=runner, name=f"scan-{scan_id}", daemon=True)
        thread.start()
        return job

    def get(self, scan_id: str) -> ScanJob | None:
        with self._lock:
            return self._jobs.get(scan_id)

    def cancel(self, scan_id: str) -> bool:
        job = self.get(scan_id)
        if not job:
            return False
        job.cancel()
        return True

    def recent(self, limit: int = 20) -> list[dict]:
        with self._lock:
            ids = list(self._order)[-limit:][::-1]
            jobs = [self._jobs[i] for i in ids if i in self._jobs]
        out = []
        for job in jobs:
            snap = job.snapshot(include_logs=False)
            out.append({
                "id": snap["id"],
                "subnet": snap["subnet"],
                "state": snap["state"],
                "started_at": snap["started_at"],
                "finished_at": snap["finished_at"],
                "duration": snap["duration"],
                "stats": snap["stats"],
                "demo": snap["options"].get("demo", False),
                "auto": snap["options"].get("auto", False),
            })
        return out

    def active(self) -> ScanJob | None:
        with self._lock:
            for scan_id in reversed(self._order):
                job = self._jobs.get(scan_id)
                if job and job.state == "running":
                    return job
        return None


class AutoScheduler:
    """定时自动重扫（默认一小时一次）。

    跑在服务端，所以关掉浏览器页面也会继续；配置会落到 json 文件，
    服务重启后仍在。首页只负责显示下次时间、开关和改间隔。
    """

    MIN_INTERVAL = 60          # 最小 1 分钟，防止误设成 0 把网络刷爆
    MAX_INTERVAL = 7 * 24 * 3600

    def __init__(self, manager: ScanManager, state_file: str | None = None,
                 interval: int = 3600):
        self.manager = manager
        self.state_file = state_file
        self.interval = max(self.MIN_INTERVAL, int(interval))
        self.enabled = False
        self.subnet = ""
        self.options: dict = {"profile": "fast", "demo": False}
        self.next_run_at: float | None = None
        self.last_run_at: float | None = None
        self.last_scan_id: str | None = None
        self.run_count = 0
        self.last_error = ""
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._load()
        self._thread = threading.Thread(target=self._loop, name="auto-scanner", daemon=True)
        self._thread.start()

    # ---------------- 配置 ----------------
    def configure(self, enabled: bool | None = None, interval: int | None = None,
                  subnet: str | None = None, options: dict | None = None) -> dict:
        with self._lock:
            if enabled is not None:
                self.enabled = bool(enabled)
            if interval is not None:
                try:
                    value = int(interval)
                except (TypeError, ValueError):
                    raise ValueError("间隔必须是整数秒") from None
                if not self.MIN_INTERVAL <= value <= self.MAX_INTERVAL:
                    raise ValueError(f"间隔需要在 {self.MIN_INTERVAL} 秒到 "
                                     f"{self.MAX_INTERVAL // 3600} 小时之间")
                self.interval = value
            if subnet is not None:
                subnet = subnet.strip()
                if subnet:
                    if "/" not in subnet:
                        subnet += "/24"
                    self.subnet = str(ipaddress.IPv4Network(subnet, strict=False))
            if options:
                clean = {k: v for k, v in options.items() if k in
                         ("profile", "ping", "mdns", "netbios", "resolve_names", "demo")}
                self.options.update(clean)
            if self.options.get("profile") not in PORT_PROFILES:
                self.options["profile"] = "fast"

            if self.enabled:
                self.next_run_at = time.time() + self.interval
            else:
                self.next_run_at = None
                job = self.manager.active()
                if job and job.options.get("auto"):
                    job.cancel()
        self._save()
        self._wake.set()
        return self.snapshot()

    def run_now(self) -> ScanJob | None:
        """立刻跑一次（不影响后续排期）。"""
        return self._start_scan(manual=True)

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    # ---------------- 状态 ----------------
    def snapshot(self) -> dict:
        with self._lock:
            now = time.time()
            remaining = None
            if self.enabled and self.next_run_at:
                remaining = max(0, int(round(self.next_run_at - now)))
            return {
                "enabled": self.enabled,
                "interval": self.interval,
                "subnet": self.subnet,
                "options": dict(self.options),
                "next_run_at": self.next_run_at,
                "next_run_in": remaining,
                "last_run_at": self.last_run_at,
                "last_scan_id": self.last_scan_id,
                "run_count": self.run_count,
                "last_error": self.last_error,
                "min_interval": self.MIN_INTERVAL,
            }

    # ---------------- 内部 ----------------
    def _start_scan(self, manual: bool = False) -> ScanJob | None:
        if self.manager.active() is not None:
            if manual:
                raise ValueError("已经有扫描在跑了")
            return None
        with self._lock:
            subnet = self.subnet
            options = dict(self.options)
            if manual:
                options = dict(options)
            else:
                options["auto"] = True
        try:
            job = self.manager.start(subnet, options)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self.last_error = str(exc)
            return None
        with self._lock:
            self.last_error = ""
            self.last_scan_id = job.id
            if not manual:
                # 「立即扫描一次」不算进自动扫描的排期和计数
                self.last_run_at = time.time()
                self.run_count += 1
        return job

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(timeout=1.0)
            self._wake.clear()
            if self._stop.is_set():
                return
            with self._lock:
                if not self.enabled:
                    continue
                if self.next_run_at is None:
                    self.next_run_at = time.time() + self.interval
                    continue
                due = time.time() >= self.next_run_at
                interval = self.interval
            if not due:
                continue
            if self.manager.active() is not None:
                # 有扫描在跑（可能是手动的），等它结束再来
                with self._lock:
                    self.next_run_at = time.time() + 30
                continue
            job = self._start_scan()
            with self._lock:
                self.next_run_at = time.time() + interval
            if job:
                self._save()

    # ---------------- 持久化 ----------------
    def _save(self) -> None:
        if not self.state_file:
            return
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with self._lock:
                payload = {
                    "enabled": self.enabled,
                    "interval": self.interval,
                    "subnet": self.subnet,
                    "options": self.options,
                    "last_run_at": self.last_run_at,
                    "run_count": self.run_count,
                }
            with open(self.state_file, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def _load(self) -> None:
        if not self.state_file or not os.path.isfile(self.state_file):
            return
        try:
            with open(self.state_file, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        self.enabled = bool(data.get("enabled"))
        try:
            self.interval = min(self.MAX_INTERVAL,
                                max(self.MIN_INTERVAL, int(data.get("interval", self.interval))))
        except (TypeError, ValueError):
            pass
        self.subnet = str(data.get("subnet") or "")
        options = data.get("options")
        if isinstance(options, dict):
            self.options.update({k: v for k, v in options.items() if k != "auto"})
        try:
            self.last_run_at = float(data["last_run_at"]) if data.get("last_run_at") else None
        except (TypeError, ValueError):
            self.last_run_at = None
        try:
            self.run_count = int(data.get("run_count") or 0)
        except (TypeError, ValueError):
            self.run_count = 0
        if self.enabled:
            # 服务重启后接着原来的节奏走；已经过点就尽快补一次
            base = self.last_run_at or time.time()
            self.next_run_at = max(time.time() + 5, base + self.interval)


def export_csv(job: ScanJob) -> str:
    snap = job.snapshot(include_logs=False)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["IP", "MAC", "厂商", "主机名", "设备类型", "开放端口", "延迟(ms)",
                     "网卡", "状态", "发现方式", "备注"])
    for dev in snap["devices"]:
        writer.writerow([
            dev["ip"], dev["mac"], dev["vendor"], dev["hostname"], dev["kind"],
            " ".join(str(p) for p in dev["ports"]),
            "" if dev["rtt_ms"] is None else dev["rtt_ms"],
            dev["iface"],
            "在线" if dev["online"] else "离线",
            "/".join(dev["sources"]),
            dev["note"],
        ])
    return buffer.getvalue()


def random_mac() -> str:
    """生成一个看起来合理的 MAC（演示/测试用）。"""
    prefix = random.choice([k for k in list(oui._TABLE)[:200]])
    tail = [random.randint(0, 255) for _ in range(3)]
    return ":".join([prefix[0:2], prefix[2:4], prefix[4:6]] + [f"{b:02X}" for b in tail])


# --------------------------------------------------------------------------
# 设备台账：把每次扫到的设备攒起来，掉线的也留着，支持人工编辑
# --------------------------------------------------------------------------

DEFAULT_CATEGORIES = [
    "未分类", "电脑", "手机 / 平板", "路由器 / 网络", "智能家居",
    "摄像头 / 安防", "打印机", "存储 / NAS", "影音设备", "其他",
]

# 用户可以改的字段
EDITABLE_FIELDS = ("name", "category", "location", "tags", "note", "kind",
                   "starred", "ignored")


def device_key(dev: dict) -> str:
    """有 MAC 用 MAC 做键（IP 会变，MAC 不会），没有就退回 IP。"""
    mac = normalize_mac(dev.get("mac") or "")
    if mac:
        return mac
    return "ip:" + str(dev.get("ip") or "")


class DeviceRegistry:
    """扫描结果的长期台账。

    - 每次扫描结束归档一次：见过的更新信息并标记在线，这次没出现的标记掉线，
      但记录保留（"曾经扫到过、现在掉线"的设备都在）；
    - 人工编辑的字段（别名/分类/位置/标签/备注/类型/关注）单独存在 custom 里，
      重新扫描不会覆盖；
    - 落盘到 data/devices.json，服务重启不丢。
    """

    def __init__(self, state_file: str | None = None):
        self.state_file = state_file
        self.devices: dict[str, dict] = {}
        self.categories: list[str] = list(DEFAULT_CATEGORIES)
        self.updated_at: float | None = None
        self._lock = threading.RLock()
        self._load()

    # ---------------- 查询 ----------------
    def stats(self) -> dict:
        with self._lock:
            records = list(self.devices.values())
            online = sum(1 for r in records if r.get("online"))
            edited = sum(1 for r in records if r.get("custom") and any(r["custom"].values()))
            starred = sum(1 for r in records if r["custom"].get("starred"))
            ignored = sum(1 for r in records if r["custom"].get("ignored"))
            cats: dict[str, int] = {}
            for rec in records:
                cat = rec["custom"].get("category") or "未分类"
                cats[cat] = cats.get(cat, 0) + 1
            return {
                "total": len(records),
                "online": online,
                "offline": len(records) - online,
                "edited": edited,
                "starred": starred,
                "ignored": ignored,
                "categories": cats,
                "updated_at": self.updated_at,
            }

    def list(self) -> list[dict]:
        with self._lock:
            return [self._flatten(rec) for rec in self.devices.values()]

    def get(self, key: str) -> dict | None:
        with self._lock:
            rec = self.devices.get(key) or self.devices.get(key.upper())
            return self._flatten(rec) if rec else None

    def categories_list(self) -> list[str]:
        with self._lock:
            known = list(self.categories)
            for rec in self.devices.values():
                cat = rec["custom"].get("category")
                if cat and cat not in known:
                    known.append(cat)
            return known

    def _flatten(self, rec: dict) -> dict:
        custom = rec.get("custom") or {}
        auto_kind = rec.get("kind") or ""
        name = (custom.get("name") or "").strip()
        display = name or rec.get("hostname") or rec.get("vendor") or "未知设备"
        return {
            "key": rec["key"],
            "mac": rec.get("mac", ""),
            "ip": rec.get("ip", ""),
            "ips": list(rec.get("ips") or []),
            "vendor": rec.get("vendor", ""),
            "hostname": rec.get("hostname", ""),
            "name": display,
            "custom_name": name,
            "auto_kind": auto_kind,
            "kind": custom.get("kind") or auto_kind or "未知设备",
            "category": custom.get("category") or "未分类",
            "location": custom.get("location") or "",
            "tags": list(custom.get("tags") or []),
            "note": custom.get("note") or "",
            "starred": bool(custom.get("starred")),
            "ignored": bool(custom.get("ignored")),
            "edited": bool(name or custom.get("kind") or custom.get("category") not in (None, "", "未分类")
                           or custom.get("location") or custom.get("tags") or custom.get("note")
                           or custom.get("starred") or custom.get("ignored")),
            "ports": list(rec.get("ports") or []),
            "services": list(rec.get("services") or []),
            "iface": rec.get("iface", ""),
            "first_seen": rec.get("first_seen"),
            "last_seen": rec.get("last_seen"),
            "seen_count": rec.get("seen_count", 0),
            "online": bool(rec.get("online")),
            "offline_since": rec.get("offline_since"),
            "last_scan_id": rec.get("last_scan_id", ""),
        }

    # ---------------- 归档 ----------------
    def update_from_scan(self, snapshot: dict) -> dict:
        """把一次扫描结果并进台账，返回统计信息。

        只有落在本次扫描网段里的设备才会被判成"掉线"——扫别的网段不该影响
        本网段设备的在线状态。
        """
        now = time.time()
        devices = snapshot.get("devices") or []
        try:
            scanned = ipaddress.IPv4Network(snapshot.get("subnet") or "", strict=False)
        except (ValueError, TypeError):
            scanned = None
        seen: set[str] = set()
        added = 0
        with self._lock:
            for dev in devices:
                key = device_key(dev)
                if not key or key == "ip:":
                    continue
                mac = normalize_mac(dev.get("mac") or "")
                ip = str(dev.get("ip") or "")
                # 之前只记到 IP、这次拿到 MAC 了：把人工信息迁过去，别出现两条
                legacy = "ip:" + ip
                if mac and legacy in self.devices and key not in self.devices:
                    moved = self.devices.pop(legacy)
                    moved["key"] = key
                    moved["mac"] = mac
                    self.devices[key] = moved
                rec = self.devices.get(key)
                if rec is None:
                    rec = {
                        "key": key, "mac": mac, "ip": ip, "ips": [ip] if ip else [],
                        "vendor": "", "hostname": "", "kind": "", "ports": [], "services": [],
                        "iface": "", "first_seen": now, "last_seen": now, "seen_count": 0,
                        "online": True, "offline_since": None, "last_scan_id": "",
                        "custom": {field: ([] if field == "tags" else (False if field in ("starred", "ignored") else ""))
                                   for field in EDITABLE_FIELDS},
                    }
                    self.devices[key] = rec
                    added += 1
                if mac:
                    rec["mac"] = mac
                if ip:
                    rec["ip"] = ip
                    ips = rec.setdefault("ips", [])
                    if ip not in ips:
                        ips.append(ip)
                        del ips[:-5]                      # 最多留最近 5 个 IP
                for field in ("vendor", "hostname", "iface"):
                    value = dev.get(field)
                    if value:
                        rec[field] = value
                if dev.get("kind"):
                    rec["kind"] = dev["kind"]
                if dev.get("services"):
                    rec["services"] = sorted(set(dev["services"]))
                if dev.get("ports"):
                    rec["ports"] = sorted(set(dev["ports"]))
                rec["last_seen"] = dev.get("last_seen") or now
                rec["seen_count"] = int(rec.get("seen_count") or 0) + 1
                rec["online"] = True
                rec["offline_since"] = None
                rec["last_scan_id"] = snapshot.get("id", "")
                seen.add(key)

            went_offline = 0
            for key, rec in self.devices.items():
                if key in seen:
                    continue
                if scanned is not None:
                    try:
                        if ipaddress.ip_address(rec.get("ip") or "0.0.0.0") not in scanned:
                            continue          # 不在本次扫描范围，不动它的状态
                    except ValueError:
                        continue
                if rec.get("online"):
                    rec["online"] = False
                    rec["offline_since"] = now
                    went_offline += 1
            self.updated_at = now
        if devices:
            self._save()
        return {"added": added, "seen": len(seen), "offline": went_offline,
                "total": len(self.devices)}

    # ---------------- 编辑 ----------------
    def update(self, key: str, fields: dict, reset: bool = False) -> dict | None:
        with self._lock:
            rec = self.devices.get(key) or self.devices.get(key.upper())
            if rec is None:
                return None
            custom = rec.setdefault("custom", {})
            if reset:
                for field in EDITABLE_FIELDS:
                    custom[field] = [] if field == "tags" else (False if field in ("starred", "ignored") else "")
            for field in EDITABLE_FIELDS:
                if field not in fields:
                    continue
                value = fields[field]
                if field == "tags":
                    if isinstance(value, str):
                        value = [t.strip() for t in re.split(r"[,，;；]", value) if t.strip()]
                    custom[field] = [str(t) for t in (value or [])][:12]
                elif field in ("starred", "ignored"):
                    custom[field] = bool(value)
                else:
                    text = str(value or "").strip()[:200]
                    custom[field] = text
            if fields.get("category"):
                cat = str(fields["category"]).strip()[:40]
                if cat and cat not in self.categories:
                    self.categories.append(cat)
            self.updated_at = time.time()
            result = self._flatten(rec)
        self._save()
        return result

    def delete(self, key: str) -> bool:
        with self._lock:
            removed = self.devices.pop(key, None) or self.devices.pop(key.upper(), None)
            if removed is None:
                return False
            self.updated_at = time.time()
        self._save()
        return True

    def apply_to_snapshot(self, snapshot: dict) -> dict:
        """把台账里的人工信息（别名/分类/关注）贴到扫描结果上，页面直接用。"""
        with self._lock:
            by_mac = {rec["mac"]: rec for rec in self.devices.values() if rec.get("mac")}
            by_ip = {rec.get("ip"): rec for rec in self.devices.values() if rec.get("ip")}
            for dev in snapshot.get("devices") or []:
                rec = by_mac.get(normalize_mac(dev.get("mac") or "")) or by_ip.get(dev.get("ip"))
                if not rec:
                    continue
                custom = rec.get("custom") or {}
                dev["managed"] = True
                dev["alias"] = custom.get("name") or ""
                dev["category"] = custom.get("category") or "未分类"
                dev["location"] = custom.get("location") or ""
                dev["tags"] = list(custom.get("tags") or [])
                dev["starred"] = bool(custom.get("starred"))
                dev["ignored"] = bool(custom.get("ignored"))
                if custom.get("kind"):
                    dev["kind"] = custom["kind"]
        return snapshot

    # ---------------- 落盘 ----------------
    def _save(self) -> None:
        if not self.state_file:
            return
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with self._lock:
                payload = {
                    "version": 1,
                    "updated_at": self.updated_at,
                    "categories": self.categories,
                    "devices": self.devices,
                }
            tmp = self.state_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self.state_file)
        except OSError:
            pass

    def _load(self) -> None:
        if not self.state_file or not os.path.isfile(self.state_file):
            return
        try:
            with open(self.state_file, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        devices = data.get("devices")
        if isinstance(devices, dict):
            for key, rec in devices.items():
                if not isinstance(rec, dict):
                    continue
                rec.setdefault("key", key)
                custom = rec.setdefault("custom", {})
                for field in EDITABLE_FIELDS:
                    custom.setdefault(field, [] if field == "tags" else
                                      (False if field in ("starred", "ignored") else ""))
                self.devices[key] = rec
        cats = data.get("categories")
        if isinstance(cats, list):
            self.categories = list(DEFAULT_CATEGORIES)
            for cat in cats:
                if cat and cat not in self.categories:
                    self.categories.append(str(cat))
        try:
            self.updated_at = float(data["updated_at"]) if data.get("updated_at") else None
        except (TypeError, ValueError):
            self.updated_at = None


def export_registry_csv(registry: DeviceRegistry) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["状态", "名称", "分类", "位置", "标签", "IP", "MAC", "厂商",
                     "自动识别类型", "当前类型", "开放端口", "首次发现", "最近在线",
                     "出现次数", "备注"])
    for rec in sorted(registry.list(), key=lambda r: tuple(int(x) for x in r["ip"].split("."))
                      if r["ip"] and all(p.isdigit() for p in r["ip"].split(".")) else (999,)):
        fmt = lambda ts: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else ""  # noqa: E731
        writer.writerow([
            "在线" if rec["online"] else "离线", rec["name"], rec["category"], rec["location"],
            " ".join(rec["tags"]), rec["ip"], rec["mac"], rec["vendor"], rec["auto_kind"],
            rec["kind"], " ".join(str(p) for p in rec["ports"]),
            fmt(rec["first_seen"]), fmt(rec["last_seen"]), rec["seen_count"], rec["note"],
        ])
    return buffer.getvalue()
