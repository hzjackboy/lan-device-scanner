# 局域网设备扫描服务

**零依赖的局域网设备扫描器**：Python 标准库后端 + 原生 JS 前端。
不需要 root，不装任何第三方包，一条 `docker run` 起来，浏览器打开就能用。

打开页面就能看到局域网里所有联网设备——**IP、MAC、厂商、主机名、设备类型、开放端口、延迟**，
并且把它们**长期记成一本可编辑的台账**：掉线的设备不删除，谁来过、谁什么时候走的都查得到。

> 路由器后台只给你一份 DHCP 租约列表（IP + 主机名），既没有厂商也没有历史。
> 这个工具补的就是这块：**认出是什么设备，并且记住它**。

---

## 快速开始

```bash
docker run -d --name lan-scan --network host \
  -v lan-scan-data:/app/data \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  hzjackboy/lan-device-scanner:latest
```

然后浏览器打开 **<http://127.0.0.1:8765>**，选网段 → 点「开始扫描」。

同一个局域网的手机、平板也能访问：`http://<宿主机IP>:8765`。

### ⚠️ `--network host` 是硬要求，不是可选项

这个工具靠 **ARP（二层广播域）** 发现设备——读宿主机 ARP 表 + 发 UDP 触发 ARP 解析。
Docker 默认的 bridge 网络里容器被 NAT，容器的 `/proc/net/arp` 里只有 docker 网段那几个地址，
**扫不到你的局域网**。

| 部署位置 | ARP 发现 | 说明 |
| --- | --- | --- |
| Linux 主机（`--network host`） | ✅ | 推荐，能拿到真实 MAC |
| 软路由 / NAS / 群晖（host 网络） | ✅ | 长期挂着跑最合适 |
| K8s（`hostNetwork: true`） | ✅ | — |
| **macOS 上的 Docker（含 colima）** | ❌ | host 网络也只是虚拟机内网，实测容器看到的是 `192.168.x.x` 而不是宿主机的 `10.0.0.x`；**macOS 上请在宿主机直接跑 Python** |

用了 host 网络后不能再写 `-p` 端口映射，容器直接占用宿主机的 8765。

---

## 功能

**设备识别**

- 发现手段：ARP 缓存 → UDP 触发 ARP 解析（非 root 拿真实 MAC，能发现**禁 ping** 的设备）→
  并发 ICMP → mDNS/Bonjour 浏览 → 反向 DNS → NetBIOS 名称查询 → TCP 端口指纹
- 厂商识别：内置 2600+ 常见厂商，另可加载 IEEE 全量 OUI（4 万条）
- 设备类型推断按可信度排序：强特征端口 → 主机名关键词 → 端口组合 → mDNS 服务 → 厂商 → 弱端口兜底。
  所以 NAS 不会被 554 端口认成摄像头，开着 AirPlay 的 MacBook 也不会被认成 Apple TV
- 手机隐私地址（随机 MAC）如实显示「私有/随机 MAC」，**不瞎猜厂商**

**设备台账**

- 按 MAC 为主键长期记录，掉线的设备保留记录并标记离线
- 每台可人工编辑：别名、分类、位置、标签、备注、设备类型覆盖、**图标**、关注、忽略
- **重扫不会覆盖你填的内容**；「恢复自动识别」一键清空
- 导出 CSV / JSON（CSV 带 BOM，Excel 直接打开不乱码）

**Web 界面**

- 首页：在线/离线环形饼图 + 设备总览，**四种展示密度**（列表 / 大图标 / 中图标 / 小图标）
- 实时进度：SSE 推送，设备一台台冒出来，不用等扫描结束
- 网段占用热力图、扫描历史（最近 60 次）、按分类/类型/状态分组与筛选
- 深色界面，手机、平板、桌面都能用

**定时重扫**

- 在**服务端**跑，关掉浏览器也继续；配置落盘，容器重启后按原节奏续排期
- 默认每 1 小时，最小间隔 60 秒

---

## 镜像信息

| | |
| --- | --- |
| 基础镜像 | `python:3.13-alpine` |
| 架构 | `linux/amd64`、`linux/arm64`（Docker 会自动挑对应架构） |
| 体积 | 约 17.5 MB（压缩后） |
| 暴露端口 | 8765 |
| 健康检查 | 内置 `HEALTHCHECK`，打 `/api/status` |
| 时区 | 默认 `Asia/Shanghai`，可用 `-e TZ=` 覆盖 |

**多架构**意味着 x86 的 NAS / 服务器和树莓派 / Apple Silicon 都能直接 `docker pull`，不用 `--platform`。

---

## 持久化

台账、日志、定时重扫配置都写在 `/app/data`，挂个卷就不会丢：

```bash
-v lan-scan-data:/app/data              # 命名卷
-v /你的路径/lan-scan-data:/app/data    # 或者宿主机目录
```

里面是：

| 文件 | 内容 |
| --- | --- |
| `devices.json` | 设备台账（含人工编辑内容） |
| `auto.json` | 定时重扫配置 |
| `server.log` | 运行日志 |

> ⚠️ `devices.json` 里有你网络的真实 MAC / IP / 主机名，别随手分享或提交到代码仓库。

想用 IEEE 全量厂商表（识别率更高）：

```bash
docker exec lan-scan python3 update_oui.py --out /app/data/oui.csv
docker restart lan-scan
```

---

## 常用操作

```bash
docker logs -f lan-scan          # 看日志
docker restart lan-scan          # 重启
docker rm -f lan-scan            # 停止并删除（卷还在）

# 命令行跑一次扫描
docker exec lan-scan python3 - <<'PY'
import json, urllib.request
req = urllib.request.Request("http://127.0.0.1:8765/api/scan",
                             data=json.dumps({"subnet": "10.0.0.0/24", "profile": "fast"}).encode(),
                             headers={"Content-Type": "application/json"}, method="POST")
print(json.load(urllib.request.urlopen(req)))
PY
```

---

## 已知限制

- **跨网段无效**：ARP 只作用于本广播域，扫别的子网会退化成 ICMP + 端口探测，不承诺准确
- **ICMP 可能被防火墙挡**：所以 ARP 才是主力，禁 ping 的设备一样能发现
- **随机化 MAC 认不出厂商**：手机隐私地址任何 OUI 库都查不到
- **端口探测是 connect 扫描**（不是 SYN 半开），会在目标设备留下完整连接记录，**只适合在自己网络里用**
- 依赖系统有 `ping` 命令；没有的话自动跳过 ICMP 阶段，其余功能不受影响

## 安全提醒

服务默认监听 `0.0.0.0`，**同一局域网内任何人都能打开页面并触发扫描**。
只在可信网络里运行；在公共 Wi-Fi 下请只监听本机。

另外，扫描他人网络可能违反当地法规或网络使用条款，**请只扫自己有权管理的网络**。

---

## 相关链接

- 源码仓库：<https://github.com/hzjackboy/lan-device-scanner>
- 全部标签：<https://hub.docker.com/r/hzjackboy/lan-device-scanner/tags>
