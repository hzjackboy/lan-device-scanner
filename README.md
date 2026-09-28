# 局域网设备扫描服务

一个能直接跑的局域网（LAN）设备扫描器：后端是 Python 标准库写的 HTTP 服务，
前端是一个实时刷新的 Web 页面。不需要 root，不需要装任何第三方包。

打开页面 → 选网段 → 点"开始扫描"，设备会一台台实时冒出来：IP、MAC、厂商、
主机名、设备类型、开放端口、延迟、发现方式，还有一张网段分布热力图。

```bash
git clone https://github.com/hzjackboy/lan-device-scanner.git
cd lan-device-scanner
python3 update_oui.py        # 可选：下载 IEEE 全量厂商表（约 4 万条）
python3 server.py            # 或者 ./run.sh
```

然后浏览器打开 <http://127.0.0.1:8765>（同一局域网的手机、平板也能访问，
启动时会打印局域网地址）。

---

## 功能

**扫描能力**

| 手段 | 说明 |
| --- | --- |
| ARP 缓存 + UDP 触发 ARP | 非 root 拿到真实 MAC，能发现禁 ping 的设备（局域网里最有效的一招） |
| ICMP ping 并发扫描 | 拿延迟，同时补上 ARP 表里没有的在线设备 |
| mDNS / Bonjour 浏览 | 解析 `_airplay`/`_googlecast`/`_ipp`/`_hap`/`_esphomelib` 等服务，拿到设备名和服务列表 |
| 反向 DNS | 解析 PTR 记录 |
| NetBIOS 名称查询 | 拿 Windows / Samba 机器名（自己实现的 NBNS 报文） |
| TCP 端口探测 | 快速档 10 个、完整档 67 个常见端口，用于设备指纹 |
| OUI 厂商识别 | 内置常见厂商表，另可加载 IEEE 全量 `oui.csv`（4 万条，仓库里已带一份） |

**设备类型推断**按可信度排序：强特征端口 → 主机名关键词 → 端口组合 →
mDNS 服务 → 厂商 → 弱端口兜底。所以 NAS 不会被 554 端口认成摄像头，
开着 AirPlay 的 MacBook 也不会被认成 Apple TV。

**Web 界面**

左侧是可伸缩的导航栏，收起后只留图标（点按钮或 `Ctrl/⌘ + B` 切换，状态记在
`localStorage`；窄屏自动变成抽屉，用顶部汉堡按钮唤出）。四个页面：

- **首页**（第一项，默认页）：左边是**在线 / 离线环形饼图**，右边是**设备方块墙**。
  - 饼图数据取自设备台账（只有台账才有"掉线"概念），圆心是设备总数，图例给出在线 /
    已掉线的台数和百分比，脚注带已关注、已忽略、最近归档时间；点图例或"去设备管理"
    直接跳到设备管理页并带上对应筛选
  - 方块墙里每台设备是一个约 65px 见方的小方块，上面是类型图标（💡 灯 / 📷 摄像头 /
    📱 手机 / 💻 电脑 / 📡 路由器 / 🖨 打印机 / 🔊 音箱 …）和在线状态点，下面是名称
    （优先用你在设备管理里起的别名）和 IP；设备类型、厂商、MAC、开放端口都在鼠标悬停
    提示和点击后的详情弹窗里。支持搜索、"仅在线"过滤、按设备类型 / 厂商分组；扫描时
    新设备会逐个亮起来，被标记"忽略"的设备不显示。首次打开展示服务端保留的上一次结果。
- **设备扫描**：扫描控制 + 实时进度 + 结果表格 + 网段热力图 + 扫描日志
- **历史记录**：最近 60 次扫描，可一键载入结果或直接导出 CSV / JSON；定时扫描的记录带「定时」标签
- **设备管理**：设备台账，见下节
- **关于与说明**：运行环境、可扫描网段、扫描原理、HTTP 接口列表

**设备管理（台账）**

每次扫描结束都会自动归档一次，形成一份长期的设备台账，落盘在 `data/devices.json`：

- **掉线的设备也留着**：这次没扫到的设备标记为「已掉线」并记下掉线时间，记录不删除；
  只有落在本次扫描网段里的设备才会被判掉线，扫别的网段不会误伤
- **分门别类**：默认按分类分组，也可以按设备类型、按在线状态分组；配分类 / 在线状态 / 关注 /
  已编辑 / 已忽略等筛选和 5 种排序
- **人工编辑并保存**：别名、分类、位置、标签、备注、设备类型覆盖、关注、忽略，随时可改；
  「恢复自动识别」一键清空人工内容
- **删除设备**：每行操作列都有「删除」按钮，编辑弹窗里也有；还可以勾选多台后「删除选中」，
  或用「清除离线」一键清掉所有已掉线的记录。删除只是清理台账，设备若还在线，下次扫描
  会作为新设备重新出现（人工填的别名/分类会丢失，这一点在确认框里有提示）
- **别名会贯通到其它页面**：首页方块墙和扫描结果表优先显示你起的名字（主机名作为副标题），
  被标记「忽略」的设备不再出现在首页方块墙
- 关闭关注 / 编辑过的设备可以在筛选里单独看；支持导出整个台账为 CSV / JSON
- 台账里每台设备记录了：首次发现、最近在线、出现次数、历史 IP（换过 IP 也认得出是同一台）、
  厂商、自动识别类型、端口、位置、标签、备注

**定时自动重扫**（首页顶部那一条）

打开开关后，**由服务端按间隔自动重跑**，默认一小时一次，可选 15 分钟到 24 小时。
调度在服务端进程里，所以关掉浏览器页面、甚至换台设备看，扫描都照常进行，历史记录
也会一条条攒下来。

- 配置存在 `data/auto.json`，服务重启后继续按原来的节奏走（错过的时间点会尽快补一次）
- 首页显示倒计时、上次时间、已自动扫描次数；页面开着时检测到后台扫描会自动接上实时进度，扫完自动换上新结果
- 「立即扫描一次」按钮可以马上按当前设置跑一次，不影响后续排期
- 关掉开关时如果正有定时扫描在跑，会把它取消
- 间隔下限 60 秒（防止误填 0 把网络刷爆），网段和端口档位沿用首页当前的设置

扫描页的能力：

- SSE 实时推送，扫描过程中设备逐台出现（断线自动降级为轮询）
- 进度条 + 阶段提示 + 在线数/已知主机名/已探测地址/耗时
- 表格列排序、关键词搜索、"仅在线"过滤
- 网段分布图：绿=在线、黄=仅 ARP、灰=无响应
- 点任意一行看设备详情（端口服务名、mDNS 服务、备注、发现方式）
- 导出 CSV / JSON
- 演示模式：没有真实局域网时用内置假数据看效果

想加新页面：在 `app.js` 的 `VIEWS` 里加一项、在 `index.html` 里加一个
`<section class="view" id="view-xxx" hidden>`、再加一个 `.nav-item[data-view=xxx]`
即可，hash 路由和折叠逻辑都是现成的。

## 开发 / 接手这个项目

- **`AGENTS.md`** —— 压缩后的项目上下文（架构、关键设计、已知坑、API 一览）。
  用 DSH 打开这个目录时会被自动加载，新会话不用重新摸索。
- **`./tests/run.sh`** —— 跑全部测试：5 套前端离线测试（node + DOM 桩，直接跑
  `static/app.js` 的真实渲染逻辑）+ 3 套联调脚本（服务在跑时自动附带）。当前 107 项用例。

```bash
./tests/run.sh          # 全量
node tests/ui_devices.test.js   # 单跑某一套
```

## 目录结构

```
server.py          HTTP 服务 + JSON API + SSE（唯一入口）
scanner.py         扫描引擎：网段识别、ARP、ping、端口、任务管理
mdns.py            极简 mDNS/Bonjour 实现（查询 + 解析 + 浏览服务）
netbios.py         NetBIOS 名称服务（NBSTAT）实现
oui.py             MAC 厂商库 + 设备类型推断
update_oui.py      下载 IEEE 全量 OUI 表到 oui.csv（可选，跑一次即可）
oui.csv            厂商表（4 万条，update_oui.py 下载的）
data/auto.json     定时重扫的配置（开关 / 间隔 / 网段 / 上次时间），自动生成
data/devices.json  设备台账（含人工编辑内容），自动生成
static/            前端页面（原生 JS，无框架无依赖）
tests/             测试脚本 + run.sh
AGENTS.md          压缩后的项目上下文（DSH 自动加载）
Dockerfile         容器镜像（alpine + iproute2 + iputils）
docker-compose.yml compose 编排（host 网络 + data 卷）
run.sh             启动脚本
```

## 桌面一键脚本（macOS）

只有一个脚本：`desktop/局域网扫描服务.command`。复制到桌面后**双击即可**，
所有功能（启动 / 停止 / 重启 / 打开页面 / 看状态 / 看日志）都在菜单里：

```
==============================================
  局域网设备扫描服务
==============================================
  状态：● 运行中（PID 97892）
  本机：http://127.0.0.1:8765
  局域网：http://10.0.0.50:8765
----------------------------------------------
  1) 启动服务并打开页面
  2) 停止服务
  3) 重启服务
  4) 只打开页面
  5) 查看运行状态
  6) 查看最近日志
  0) 退出
----------------------------------------------
  请输入序号（直接回车 = 打开页面）:
```

菜单顶部实时显示服务状态；**直接按回车**执行默认动作——服务没跑就"启动并打开页面"，
已经在跑就"打开页面"，所以双击后敲一下回车就能用。

终端里也可以带动作直接调用：

```bash
~/Desktop/局域网扫描服务.command start     # 启动并打开页面
~/Desktop/局域网扫描服务.command stop      # 停止
~/Desktop/局域网扫描服务.command restart   # 重启
~/Desktop/局域网扫描服务.command open      # 只打开页面（没跑就先启动）
~/Desktop/局域网扫描服务.command toggle    # 没跑就启动，在跑就停止
~/Desktop/局域网扫描服务.command status    # 状态（版本、网段、定时重扫、台账统计）
~/Desktop/局域网扫描服务.command log       # 最近 40 行日志
~/Desktop/局域网扫描服务.command help      # 帮助
```

服务用 `nohup` 挂在后台（日志 `data/server.log`，进程号 `data/server.pid`），
关掉终端窗口也继续跑；停止时先按 pid 文件找进程，找不到就按端口找，所以别的
方式启动的实例也能停掉。项目目录默认写在脚本顶部的 `PROJECT_DIR`，换路径改它或设
环境变量 `LAN_SCAN_PROJECT`；从仓库的 `desktop/` 目录直接跑会自动回退到上一级。

> 脚本里变量一律写成 `${VAR}` 而不是 `$VAR`：macOS 自带的 bash 3.2 在变量后面
> 紧跟中文全角字符时，会把该字符的首字节吃进变量名，导致输出乱码。

## Docker 部署

可以打包成镜像，仓库里已经带了 `Dockerfile` / `docker-compose.yml` / `.dockerignore`。

```bash
docker build -t lan-device-scanner .
docker run -d --name lan-scan --network host \
  -v "$PWD/data:/app/data" \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  lan-device-scanner
```

或者直接用 compose：

```bash
docker compose up -d      # 起来
docker compose logs -f    # 看日志
docker compose down       # 停掉
```

### ⚠️ 必须用 host 网络

这个工具的发现能力靠 **ARP（二层广播域）**：读宿主 ARP 表 + 发 UDP 触发 ARP 解析。
Docker 默认的 bridge 网络里容器被 NAT，`/proc/net/arp` 只有 docker 网段那几个地址，
**扫不到你的局域网**。所以 `--network host`（compose 里 `network_mode: host`）是硬要求；
用了 host 网络后不能再写 `ports:` 映射，容器直接占用宿主机 8765 端口。

| 部署位置 | ARP 发现 | 说明 |
| --- | --- | --- |
| Linux 主机 / 软路由 / 树莓派 | ✅ | `--network host` 后与直接在宿主机跑等价 |
| 群晖、威联通等 NAS 的容器套件 | ✅ | 网络选「使用与 Docker Host 相同的网络」/ host |
| Kubernetes | ⚠️ | 需要 `hostNetwork: true`，且 Pod 所在节点必须在目标局域网内 |
| 云服务器 VPS | ⚠️ | 只能扫 VPS 自己那一段（宿主 ARP 表），**扫不到你家局域网**；跨网段退化成 ICMP + 端口探测 |
| Docker Desktop（macOS / Windows） | ❌ | 容器跑在虚拟机里，即使 host 网络也在 VM 的 NAT 后面，ARP 看到的不是你的局域网 |

### 持久化与环境变量

| 路径 / 变量 | 作用 |
| --- | --- |
| `/app/data`（挂卷） | 设备台账 `devices.json`、日志 `server.log`、定时重扫配置 `auto.json` |
| `TZ` | 日志与时间显示时区，默认 `Asia/Shanghai` |
| `LAN_SCAN_OUI` | 厂商表路径，默认按 `oui.csv` → `data/oui.csv` 顺序找 |

厂商表想持久化（默认不在镜像里，1.5MB）：`docker exec lan-scan python3 update_oui.py --out /app/data/oui.csv`

镜像基于 `python:3.13-alpine` + `iproute2` + `iputils`，约 60MB；内置 `HEALTHCHECK`
打 `/api/status`，`docker ps` 能看到 healthy 状态。容器里以 root 运行（ICMP 需要
`NET_RAW`，Docker 默认能力集已包含）——**只在内网暴露**，公网请加反向代理和认证。

> 容器里没有桌面启动脚本（那是给 macOS 用的），但定时重扫等功能照常：调度在服务端进程里。

## 使用方法

```bash
# 默认监听 0.0.0.0:8765，局域网内其他设备也能打开
python3 server.py

# 换端口 / 启动后自动打开浏览器 / 只监听本机
python3 server.py --port 9000 --open
python3 server.py --host 127.0.0.1

# 刷新厂商库（需要联网，之后的扫描可离线）
python3 update_oui.py
```

页面上可以选自动检测到的网段，也可以手填，例如 `192.168.1.0/24`。
网段上限 /20（4096 个地址），再大会直接报错而不是把机器拖死。

## HTTP API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/status` | 服务信息、本机网段、ping 是否可用、定时重扫状态、台账统计 |
| GET | `/api/interfaces` | 可扫描网段列表 |
| POST | `/api/scan` | 启动扫描，body：`{"subnet":"10.0.0.0/24","profile":"fast","demo":false,"ping":true,"mdns":true,"netbios":true,"resolve_names":true}` |
| GET | `/api/scan/<id>` | 当前快照（进度 + 设备列表 + 日志） |
| GET | `/api/scan/<id>/events` | SSE 实时推送，每个变更推一次 `event: scan` |
| DELETE | `/api/scan/<id>` | 取消扫描 |
| GET | `/api/scan/<id>/export?format=csv\|json` | 导出结果 |
| GET | `/api/auto` | 定时重扫状态：开关、间隔、下次时间、已跑次数 |
| POST | `/api/auto` | 设置定时重扫：`{"enabled":true,"interval":3600,"subnet":"10.0.0.0/24","options":{"profile":"fast"}}` |
| POST | `/api/auto/run` | 立刻按当前设置跑一次（不影响排期） |
| GET | `/api/devices` | 设备台账：设备列表 + 统计 + 分类 |
| POST | `/api/devices/<key>` | 编辑台账设备：`{"name":"主路由","category":"路由器 / 网络","location":"弱电箱","tags":"常驻","note":"...","kind":"","starred":true,"ignored":false}`，发 `{"reset":true}` 恢复自动识别 |
| DELETE | `/api/devices/<key>` | 从台账删除该设备 |
| POST | `/api/devices/bulk-delete` | 批量删除：`{"keys":["MAC1","MAC2"]}` 或 `{"scope":"offline\|ignored\|all"}`，返回删除条数与最新统计 |
| GET | `/api/devices/export?format=csv\|json` | 导出台账 |
| GET | `/api/history` | 最近 60 次扫描记录 |
| GET | `/api/oui?mac=...` | 单查厂商 |

命令行扫一遍（不打开页面）：

```bash
ID=$(curl -s -X POST localhost:8765/api/scan \
      -H 'Content-Type: application/json' \
      -d '{"subnet":"10.0.0.0/24","profile":"fast"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["scan_id"])')
curl -sN localhost:8765/api/scan/$ID/events | head -20   # 实时看进度
curl -s "localhost:8765/api/scan/$ID/export?format=csv"  # 导出
```

## 结果字段

| 字段 | 说明 |
| --- | --- |
| `online` | 是否确认在线（ping 通 / 有 ARP 应答 / 端口开放） |
| `only_arp` | 只在 ARP 缓存里出现过、没被其他手段确认，可能是过期记录 |
| `sources` | 发现来源：`arp-cache` `arp` `icmp` `tcp` `mdns` `dns` `netbios` |
| `confirmed` | 是否被明确探测手段确认过 |
| `note` | 附加说明，如 mDNS TXT 里的设备型号 |

## 已知限制

- **跨网段无效**：ARP 只能作用于本广播域，扫别的子网会退化成 ICMP + 端口探测。
- **ICMP 可能被防火墙挡**：所以 ARP 才是主力，禁 ping 的设备一样能发现。
- **厂商识别依赖 OUI 表**：随机化 MAC（手机隐私地址）只能显示"私有/随机 MAC"。
- **端口扫描是 connect 扫描**：不是 SYN 半开扫描，会留下完整 TCP 连接记录，
  只适合在自己网络里用。
- ping 需要系统有 `ping` 命令；没有的话自动跳过 ICMP 阶段，其余功能不受影响。
- macOS 首次运行可能弹出"本地网络访问"授权提示，允许后 ARP/mDNS 才能拿到完整结果。

## 安全提醒

服务默认监听 `0.0.0.0`，同一局域网内任何人都能打开页面并触发扫描。
只在可信网络里运行；在公共网络（咖啡馆、酒店 Wi-Fi）请加 `--host 127.0.0.1`。
另外，扫描他人网络可能违反当地法规或网络使用条款，请只扫自己有权管理的网络。
