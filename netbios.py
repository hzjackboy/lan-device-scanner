"""NetBIOS 名称服务（NBNS）查询，用来拿 Windows 机器名。

只实现 node status request（QTYPE=NBSTAT），命中率对 Windows/Samba
主机很高，且不需要任何依赖。
"""

from __future__ import annotations

import socket
import struct

NBNS_PORT = 137


def _encode_wildcard() -> bytes:
    """把 "*" 编码成 NetBIOS 第一级名字（32 字节十六进制半字节形式）。"""
    raw = b"*" + b"\x00" * 15
    out = bytearray([0x20])
    for byte in raw:
        out.append(0x41 + (byte >> 4))
        out.append(0x41 + (byte & 0x0F))
    out.append(0x00)
    return bytes(out)


def _build_request(tx_id: int) -> bytes:
    header = struct.pack("!HHHHHH", tx_id, 0x0000, 1, 0, 0, 0)
    return header + _encode_wildcard() + struct.pack("!HH", 0x0021, 0x0001)


def _decode_nb_name(raw: bytes) -> str:
    return raw.decode("ascii", "replace").rstrip(" \x00")


def node_status(ip: str, timeout: float = 0.6) -> str | None:
    """返回该 IP 的 NetBIOS 工作站名，失败返回 None。"""
    tx_id = 0x4A21
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(_build_request(tx_id), (ip, NBNS_PORT))
        data, _ = sock.recvfrom(2048)
        sock.close()
    except OSError:
        return None

    try:
        if len(data) < 12:
            return None
        _tid, _flags, qdcount, ancount, _ns, _ar = struct.unpack("!HHHHHH", data[:12])
        if ancount < 1:
            return None
        pos = 12
        # 有些实现不回显 question 段，按 header 里的 qdcount 跳过才靠谱
        for _ in range(qdcount):
            while pos < len(data) and data[pos] != 0:
                pos += data[pos] + 1
            pos += 1 + 4
        # 应答里的名字（可能是压缩指针）
        if pos + 2 <= len(data) and data[pos] & 0xC0 == 0xC0:
            pos += 2
        else:
            while pos < len(data) and data[pos] != 0:
                pos += data[pos] + 1
            pos += 1
        if pos + 10 > len(data):
            return None
        _rtype, _rclass, _ttl, rdlength = struct.unpack("!HHIH", data[pos:pos + 10])
        pos += 10
        rdata = data[pos:pos + rdlength]
        if not rdata:
            return None
        count = rdata[0]
        best: str | None = None
        for i in range(count):
            start = 1 + i * 18
            if start + 18 > len(rdata):
                break
            name = _decode_nb_name(rdata[start:start + 15])
            suffix = rdata[start + 15]
            flags = struct.unpack("!H", rdata[start + 16:start + 18])[0]
            is_group = bool(flags & 0x8000)
            if not name or name == "*" or is_group:
                continue
            # 0x00 工作站、0x20 文件服务器
            if suffix in (0x00, 0x20):
                if best is None or suffix == 0x00:
                    best = name
        return best
    except Exception:
        return None
