"""极简 mDNS（Bonjour）实现，只依赖标准库。

用途有两个：
1. 反查某个 IP 的 ``*.local`` 主机名；
2. 浏览常见服务类型（_airplay/_googlecast/_ipp/...），把设备名字和服务
   映射回 IP，用来判断"这台机器是什么"。
"""

from __future__ import annotations

import re
import socket
import struct
import threading
import time

MDNS_ADDR = "224.0.0.251"
MDNS_PORT = 5353

TYPE_A = 1
TYPE_PTR = 12
TYPE_TXT = 16
TYPE_AAAA = 28
TYPE_SRV = 33

# 常见服务类型：浏览它们能覆盖绝大多数消费级设备
DEFAULT_SERVICES = [
    "_services._dns-sd._udp.local",
    "_workstation._tcp.local",
    "_device-info._tcp.local",
    "_http._tcp.local",
    "_https._tcp.local",
    "_ssh._tcp.local",
    "_sftp-ssh._tcp.local",
    "_smb._tcp.local",
    "_afpovertcp._tcp.local",
    "_airplay._tcp.local",
    "_raop._tcp.local",
    "_googlecast._tcp.local",
    "_spotify-connect._tcp.local",
    "_ipp._tcp.local",
    "_ipps._tcp.local",
    "_printer._tcp.local",
    "_scanner._tcp.local",
    "_homekit._tcp.local",
    "_hap._tcp.local",
    "_hap._udp.local",
    "_mqtt._tcp.local",
    "_printer._tcp.local",
    "_companion-link._tcp.local",
    "_rdlink._tcp.local",
    "_sleep-proxy._udp.local",
    "_sonos._tcp.local",
    "_amzn-wplay._tcp.local",
    "_privet._tcp.local",
    "_nfs._tcp.local",
    "_daap._tcp.local",
    "_rfb._tcp.local",
    "_telnet._tcp.local",
    "_ftp._tcp.local",
    "_shelly._tcp.local",
    "_esphomelib._tcp.local",
    "_arduino._tcp.local",
    "_octoprint._tcp.local",
]


def _encode_name(name: str) -> bytes:
    out = bytearray()
    for label in name.rstrip(".").split("."):
        data = label.encode("utf-8", "replace")[:63]
        if not data:
            continue
        out.append(len(data))
        out += data
    out.append(0)
    return bytes(out)


def _decode_name(data: bytes, offset: int, depth: int = 0) -> tuple[str, int]:
    """解析域名，自动跟随压缩指针。返回 (name, 下一个字节位置)。"""
    labels: list[str] = []
    pos = offset
    next_pos = offset
    jumped = False
    while pos < len(data) and depth < 32:
        length = data[pos]
        if length == 0:
            pos += 1
            if not jumped:
                next_pos = pos
            break
        if length & 0xC0 == 0xC0:
            if pos + 1 >= len(data):
                break
            pointer = ((length & 0x3F) << 8) | data[pos + 1]
            if not jumped:
                next_pos = pos + 2
            jumped = True
            if pointer >= len(data):
                break
            inner, _ = _decode_name(data, pointer, depth + 1)
            if inner:
                labels.append(inner)
            pos += 2
            break
        pos += 1
        chunk = data[pos:pos + length]
        labels.append(chunk.decode("utf-8", "replace"))
        pos += length
    name = ".".join(labels).rstrip(".")
    return name, next_pos


def _build_query(names: list[str], qtype: int = TYPE_PTR) -> bytes:
    header = struct.pack("!HHHHHH", 0, 0x0000, len(names), 0, 0, 0)
    body = bytearray()
    for name in names:
        body += _encode_name(name)
        # qclass 最高位置 1 = QU，请求单播应答，方便我们用普通 UDP socket 收
        body += struct.pack("!HH", qtype, 0x8001)
    return header + bytes(body)


def _parse_records(data: bytes) -> list[dict]:
    if len(data) < 12:
        return []
    _, _, qdcount, ancount, nscount, arcount = struct.unpack("!HHHHHH", data[:12])
    pos = 12
    for _ in range(qdcount):
        _, pos = _decode_name(data, pos)
        pos += 4
    records: list[dict] = []
    for _ in range(ancount + nscount + arcount):
        if pos >= len(data):
            break
        try:
            name, pos = _decode_name(data, pos)
            if pos + 10 > len(data):
                break
            rtype, rclass, ttl, rdlength = struct.unpack("!HHIH", data[pos:pos + 10])
            pos += 10
            rdata = data[pos:pos + rdlength]
            pos += rdlength
        except Exception:
            break

        rec = {"name": name, "type": rtype, "ttl": ttl}
        try:
            if rtype == TYPE_A and len(rdata) == 4:
                rec["ip"] = socket.inet_ntoa(rdata)
            elif rtype == TYPE_AAAA and len(rdata) == 16:
                rec["ip6"] = socket.inet_ntop(socket.AF_INET6, rdata)
            elif rtype == TYPE_PTR:
                rec["target"], _ = _decode_name(data, pos - rdlength)
            elif rtype == TYPE_SRV and len(rdata) > 6:
                _, _, port = struct.unpack("!HHH", rdata[:6])
                rec["port"] = port
                rec["host"], _ = _decode_name(data, pos - rdlength + 6)
            elif rtype == TYPE_TXT:
                txt: dict[str, str] = {}
                idx = 0
                while idx < len(rdata):
                    ln = rdata[idx]
                    idx += 1
                    entry = rdata[idx:idx + ln].decode("utf-8", "replace")
                    idx += ln
                    if "=" in entry:
                        k, v = entry.split("=", 1)
                        txt[k] = v
                    elif entry:
                        txt[entry] = ""
                rec["txt"] = txt
        except Exception:
            pass
        records.append(rec)
    return records


def _open_socket(timeout: float) -> socket.socket | None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        except OSError:
            pass
        sock.settimeout(0.25)
        return sock
    except OSError:
        return None


def query(names: list[str], timeout: float = 1.2, qtype: int = TYPE_PTR,
          dest: tuple[str, int] = (MDNS_ADDR, MDNS_PORT)) -> list[dict]:
    """发一次 mDNS 查询并收集应答。任何异常都吞掉，返回已收到的记录。"""
    if not names:
        return []
    sock = _open_socket(timeout)
    if sock is None:
        return []
    records: list[dict] = []
    try:
        packet = _build_query(names, qtype)
        sock.sendto(packet, dest)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, _addr = sock.recvfrom(9000)
            except socket.timeout:
                # 再补发一次，UDP 丢包在无线网络很常见
                if time.time() < deadline - 0.2:
                    try:
                        sock.sendto(packet, dest)
                    except OSError:
                        break
                continue
            except OSError:
                break
            records.extend(_parse_records(data))
    except OSError:
        pass
    finally:
        sock.close()
    return records


def reverse_lookup(ip: str, timeout: float = 0.9) -> str | None:
    """通过 mDNS 反查 IP 的 .local 主机名。"""
    arpa = ".".join(reversed(ip.split("."))) + ".in-addr.arpa"
    for rec in query([arpa], timeout=timeout):
        if rec.get("type") == TYPE_PTR and rec.get("target"):
            host = rec["target"]
            if host.endswith(".local"):
                host = host[: -len(".local")]
            if host and not host.startswith("_"):
                return host
    return None


def browse(ip_filter: str | None = None, services: list[str] | None = None,
           timeout: float = 2.2) -> dict[str, dict]:
    """浏览常见服务，返回 {ip: {name, services, port, txt}}。

    ``ip_filter`` 传网段前缀（如 "10.0.0."）可只保留目标网段的设备。
    """
    services = services or DEFAULT_SERVICES
    records = query(services, timeout=timeout)

    instance_service: dict[str, str] = {}
    instance_srv: dict[str, tuple[str, int]] = {}
    instance_txt: dict[str, dict] = {}
    host_ip: dict[str, str] = {}
    service_instances: dict[str, list[str]] = {}

    for rec in records:
        rtype = rec.get("type")
        name = rec.get("name", "")
        target = rec.get("target", "")
        if rtype == TYPE_PTR and name and target:
            service_instances.setdefault(name, []).append(target)
            if name != "_services._dns-sd._udp.local":
                instance_service[target] = name
        elif rtype == TYPE_SRV and name:
            host = rec.get("host") or rec.get("target") or ""
            instance_srv[name] = (host, rec.get("port", 0))
        elif rtype == TYPE_TXT and name:
            instance_txt.setdefault(name, {}).update(rec.get("txt", {}))
        elif rtype == TYPE_A and name and rec.get("ip"):
            host_ip[name.lower()] = rec["ip"]
        elif rtype == TYPE_AAAA and name and rec.get("ip6"):
            host_ip.setdefault(name.lower(), rec["ip6"])

    result: dict[str, dict] = {}
    for instance, service in instance_service.items():
        srv = instance_srv.get(instance)
        ip = None
        port = 0
        host = ""
        if srv:
            host, port = srv
            ip = host_ip.get(host.lower())
        if not ip:
            ip = host_ip.get(instance.lower())
        if not ip or ":" in ip:
            continue
        if ip_filter and not ip.startswith(ip_filter):
            continue
        entry = result.setdefault(ip, {"name": "", "services": [], "port": 0, "txt": {}})
        label = _clean_instance(instance)
        if not label:
            label = host[:-6] if host.lower().endswith(".local") else host
        if label and not entry["name"]:
            entry["name"] = label
        service_label = service.replace("._tcp.local", "").replace("._udp.local", "")
        service_label = service_label.lstrip("_")
        if service_label and service_label not in entry["services"]:
            entry["services"].append(service_label)
        if port and not entry["port"]:
            entry["port"] = port
        entry["txt"].update(instance_txt.get(instance, {}))

    return result


_HEX_LABEL_RE = re.compile(r"^[0-9A-Fa-f\-]{10,}$")


def _clean_instance(instance: str) -> str:
    """把 "A1B2C3D4E5F6@Alice-MacBook._raop._tcp.local" 变成 "Alice-MacBook"。"""
    label = instance.split(".")[0].strip()
    if "@" in label:
        label = label.split("@", 1)[1].strip()
    if not label or _HEX_LABEL_RE.match(label):
        return ""
    return label


def mdns_name_for(ip: str, timeout: float = 0.9) -> str | None:
    """先试反向 PTR，再退回浏览缓存里的名字。"""
    name = reverse_lookup(ip, timeout=timeout)
    if name:
        return name
    prefix = ip.rsplit(".", 1)[0] + "."
    found = browse(ip_filter=prefix, timeout=timeout)
    entry = found.get(ip)
    return entry["name"] if entry else None


def parallel_reverse(ips: list[str], timeout: float = 1.0, workers: int = 24) -> dict[str, str]:
    """并发反查一批 IP 的 mDNS 名字。"""
    results: dict[str, str] = {}
    lock = threading.Lock()
    queue = list(ips)
    index = [0]

    def worker() -> None:
        while True:
            with lock:
                if index[0] >= len(queue):
                    return
                ip = queue[index[0]]
                index[0] += 1
            name = reverse_lookup(ip, timeout=timeout)
            if name:
                with lock:
                    results[ip] = name

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(min(workers, max(1, len(queue))))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout + 1.0)
    return results
