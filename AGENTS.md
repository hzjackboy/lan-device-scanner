# 局域网设备扫描服务 —— 项目速览

零依赖局域网扫描器：Python 标准库后端 + 原生 JS 前端（无框架、无 pip 依赖、不需要 root）。
这份文件是压缩后的项目上下文，DSH 会在每个新会话自动加载。

## 当前状态

- **服务**：由桌面脚本 `~/Desktop/局域网扫描服务.command` 管理，端口 8765
  （日志 `data/server.log`，进程号 `data/server.pid`）
- **仓库**：私有 `hzjackboy/lan-device-scanner`，本机 `gh` 已登录该账号
- **数据**：`data/devices.json`（设备台账，含真实 MAC/IP/主机名）、`data/auto.json`（定时重扫配置）
  —— 都在 `.gitignore` 里，**绝不要提交**
- **测试**：`./tests/run.sh`（5 套离线 UI 测试 + 3 套联调；服务在跑时自动附带联调）

## 架构

| 文件 | 职责 |
| --- | --- |
| `server.py` | 唯一入口：HTTP + JSON API + SSE；持有 `ScanManager` / `DeviceRegistry` / `AutoScheduler` |
| `scanner.py` | 扫描引擎：网段识别、ARP、ping、端口、`ScanJob`、`ScanManager`、`AutoScheduler`、`DeviceRegistry` |
| `mdns.py` | 自实现的 mDNS/Bonjour：组包、压缩指针解析、服务浏览、反查 |
| `netbios.py` | 自实现的 NBNS 节点状态查询（拿 Windows 机器名） |
| `oui.py` | MAC 厂商库（内置表 + `oui.csv` 全量表）+ `infer_kind()` 设备类型推断 |
| `update_oui.py` | 下载 IEEE 全量 OUI 到 `oui.csv`（已 gitignore，需要时跑一次） |
| `static/` | 前端三件套（`index.html` / `style.css` / `app.js`），hash 路由 + SSE |
| `desktop/` | 桌面启动器（单文件，菜单 + 命令行动作） |
| `tests/` | node + DOM 桩测试（离线 UI）与联调脚本 |
| `Dockerfile` / `docker-compose.yml` | 容器化部署（**必须 host 网络**，否则 ARP 扫不到局域网） |

前端 5 个视图：**首页**（在线/离线环形饼图 + 设备方块墙）、**设备扫描**、**历史记录**、
**设备管理**（台账）、**关于与说明**。加视图只需：`VIEWS` 加一项 + 一个 `<section class="view">` + 一个 `.nav-item`。

## 关键设计（改代码前必读）

1. **发现顺序**：读 ARP 缓存 → UDP 触发 ARP 解析（非 root 拿 MAC、能发现禁 ping 设备）→
   并发 ICMP（拿延迟）→ ping 后补读一次 ARP（补 MAC）→ mDNS 浏览 → 反向 DNS/NetBIOS → TCP 端口指纹。
2. **设备类型推断顺序**（`oui.infer_kind`）：强特征端口 → 主机名关键词 → 端口组合 →
   mDNS 服务 → 厂商 → 弱端口兜底。所以 NAS 不会被 554 认成摄像头，MacBook 不会被认成 Apple TV。
3. **设备台账按 MAC 为主键**（IP 兜底），每次扫描结束由 `ScanManager.on_finish` 归档一次：
   见过的标记在线并累加 `seen_count`，没出现的标记掉线但**保留记录**。
4. **只有落在本次扫描网段内的设备才会被判掉线**（扫别的网段不误伤）；演示模式的假设备不进台账。
5. **人工编辑**（别名/分类/位置/标签/备注/类型覆盖/关注/忽略）存在记录的 `custom` 里，
   重扫不覆盖；通过 `apply_to_snapshot()` 贴回扫描结果，首页方块墙与结果表优先显示别名。
6. **定时重扫在服务端**（不是浏览器定时器），配置落 `data/auto.json`，重启后按原节奏续排期。

## 已知坑（都踩过）

1. **macOS 自带 bash 3.2**：`$VAR` 后面紧跟中文全角字符时，会把该字符首字节吃进变量名，
   输出乱码。**shell 脚本里变量一律写 `${VAR}`**（`desktop/` 下的脚本已全部如此）。
2. macOS `arp -an` 会省略前导零（`8:9b:4b:...`），必须按 octet 补零，否则 OUI 查不到厂商
   （`scanner.normalize_mac` / `oui.normalize`）。
3. NetBIOS 应答**不回显 question 段**，要按 header 的 `qdcount` 跳过，否则读出 `ROUP` 之类垃圾名。
4. mDNS 的 SRV 记录解析结果在 `rec["host"]`（不是 `target`），写错会导致 browse 返回 0 条。
5. 设备类型覆盖与 mDNS 别名要过滤 `(none)`、`WORKGROUP` 这类无效名（`scanner.clean_hostname`）。
6. **容器部署必须 `--network host`**：bridge 网络下 NAT 会挡掉 ARP，`/proc/net/arp`
   只剩 docker 网段。镜像里装了 iproute2/iputils；代码对 busybox 版 ping 会自动去掉 `-n`。
   macOS 上（含 colima）host 网络也只是虚拟机内网，扫不到真实局域网；容器冒烟测试见
   `tests/docker_smoke.sh`（27 项）。colima 四个坑：VM 镜像从 GitHub 下（慢，用 `--disk-image`）、
   VM 里 DNS 软链坏掉（写死 nameserver）、Docker Hub 要配 daemon 代理（宿主机 192.168.5.2:7897）、
   挂载只覆盖 `$HOME`。另外别用 `colima ssh -- curl 127.0.0.1:8765` 探测容器——会打到宿主服务。
7. **台账信息要在所有出口都贴一遍**：`GET /api/scan/<id>`、**SSE `/events`**、
   前端 `applySnapshot` 记录 `scanId`。漏掉任一处，页面上的人工别名就会不同步
   （SSE 漏贴过、编辑后不重取快照也漏过，都已修）。

## API

`GET /api/status`（含 `auto` 与 `devices` 统计）、`/api/interfaces`、`/api/history`、`/api/oui`、
`/api/auto`、`/api/devices`、`/api/devices/export`、`/api/scan/<id>`、`/api/scan/<id>/events`（SSE）、
`/api/scan/<id>/export`；
`POST /api/scan`（起扫描）、`/api/auto`（配置定时重扫）、`/api/auto/run`（立即跑一次）、
`/api/devices/<key>`（编辑，`{"reset":true}` 恢复自动识别）、`/api/devices/bulk-delete`
（`{"keys":[...]}` 或 `{"scope":"offline|ignored|all"}`）；
`DELETE /api/scan/<id>`、`DELETE /api/devices/<key>`。

## 常用命令

```bash
./run.sh                                  # 启动服务（或桌面脚本）
~/Desktop/局域网扫描服务.command status    # 状态；start/stop/restart/open/toggle/log/help
./tests/run.sh                            # 跑测试（先在项目根目录）
python3 update_oui.py                     # 刷新厂商库（需联网）
```
