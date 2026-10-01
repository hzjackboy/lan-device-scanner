# 局域网设备扫描服务 —— 容器镜像
#
# ⚠️ 关键：这个工具靠 ARP（二层广播域）发现设备，容器**必须用 host 网络**：
#     docker run --network host ...
#   默认 bridge 网络下容器被 NAT，ARP 只能看到 docker 网段，扫不到你的局域网。
#   详见 README 的「Docker 部署」一节。

FROM python:3.13-alpine

LABEL org.opencontainers.image.title="lan-device-scanner" \
      org.opencontainers.image.description="局域网设备扫描服务：零依赖扫描引擎 + 实时 Web 界面" \
      org.opencontainers.image.source="https://github.com/hzjackboy/lan-device-scanner" \
      org.opencontainers.image.version="1.4.0"

# iproute2 → ip 命令（识别网卡和网段）
# iputils  → 标准 ping（ICMP 扫描；busybox 的 ping 参数不全，代码虽会自动降级，但装全更稳）
# tzdata   → 让日志时间跟随 TZ
# ARP 走 /proc/net/arp，因此不需要 net-tools
RUN apk add --no-cache iproute2 iputils tzdata

ENV TZ=Asia/Shanghai \
    PYTHONUNBUFFERED=1
RUN cp "/usr/share/zoneinfo/${TZ}" /etc/localtime && echo "${TZ}" > /etc/timezone

WORKDIR /app
COPY server.py scanner.py mdns.py netbios.py oui.py update_oui.py ./
COPY static/ ./static/
RUN mkdir -p /app/data

# 台账 / 日志 / 定时重扫配置都写在 /app/data，挂卷持久化：
#   -v /你的路径/lan-scan-data:/app/data
# 想持久化厂商表就跑：docker exec <容器> python3 update_oui.py --out /app/data/oui.csv

EXPOSE 8765

# 用 /api/status 做健康检查（镜像里没有 curl，用标准库）
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/api/status',timeout=3).status==200 else 1)"

# 以 root 运行：ICMP 需要 NET_RAW（Docker 默认能力集已包含），
# 且读宿主 ARP 表、mDNS 组播在 host 网络下最省事。只在可信内网暴露本服务。
CMD ["python3", "server.py", "--host", "0.0.0.0", "--port", "8765"]
