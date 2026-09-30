# 局域网设备扫描服务 —— 项目速览

零依赖局域网扫描器：Python 标准库后端 + 原生 JS 前端（无框架、无 pip 依赖、不需要 root）。
这份文件是压缩后的项目上下文，DSH 会在每个新会话自动加载。

## 当前状态

- **版本**：`v1.3.0`。发版要同步改四处：`server.py` 的 `VERSION`、`static/index.html` 两处默认值、
  `tests/ui_sidebar.test.js` 的桩数据、`Dockerfile` 的 `image.version`；再补 `CHANGELOG.md` 并打 tag
- **服务**：由桌面脚本 `~/Desktop/局域网扫描服务.command` 管理，端口 8765
  （日志 `data/server.log`，进程号 `data/server.pid`）
- **镜像**：Docker Hub 公开镜像 `hzjackboy/lan-device-scanner`（amd64 + arm64 多架构），
  发版用 `./docker-push.sh hzjackboy 1.3.0 latest` 一条命令推
- **仓库**：私有 `hzjackboy/lan-device-scanner`，本机 `gh` 已登录该账号
- **数据**：`data/devices.json`（设备台账，含真实 MAC/IP/主机名）、`data/auto.json`（定时重扫配置）
  —— 都在 `.gitignore` 里，**绝不要提交**
- **测试**：`./tests/run.sh`（5 套离线 UI + 3 套联调 + 1 套启动脚本；服务在跑时自动附带联调）
- **文档地图**：`PRD.md`（产品需求：目标 / 用户画像 / 19 条需求优先级 / 逐条验收标准 / 路线图）、
  `README.md`（安装使用与排错）、`CHANGELOG.md`（版本变更）、本文件（架构与踩坑）

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
| `desktop/` | 桌面启动器（单文件）。顶部状态面板常驻 + 空闲每 3 秒原地重画；每个动作跑完都回菜单 |
| `tests/` | node + DOM 桩测试（离线 UI）与联调脚本 |
| `Dockerfile` / `docker-compose.yml` | 容器化部署（**必须 host 网络**，否则 ARP 扫不到局域网） |

前端 5 个视图：**首页**（在线/离线环形饼图 + 设备方块墙）、**设备扫描**、**历史记录**、
**设备管理**（台账）、**关于与说明**。加视图只需：`VIEWS` 加一项 + 一个 `<section class="view">` + 一个 `.nav-item`。

**首页展示密度**：`list` / `l` / `m` / `s` 四档，存在 `state.homeMode` 与 `localStorage['home-mode']`。
切换只改 `#home-grid` 的 `data-mode` 属性，**布局全在 CSS 里**（`[data-mode="..."]` 选择器），
所以切换不重新渲染、瞬时生效、不丢滚动位置。加一档只需在 `HOME_MODES`、`index.html` 的
`#home-view-switch` 里各加一项，再补一条 CSS。

**响应式断点**（都在 `style.css` 末尾的「响应式适配」一节）：
`2800 / 2200 / 1800`（放宽 `main` 的 max-width，大屏别只占中间一条）、
`900`（平板，工具条铺满）、`720`（手机：方块墙关掉内层滚动、台账表精简到 6 列）、
`560`（收起顶栏本机信息、统计卡片按内容自适应）、`480`（台账表收到 4 列）。

## 关键设计（改代码前必读）

1. **发现顺序**：读 ARP 缓存 → UDP 触发 ARP 解析（非 root 拿 MAC、能发现禁 ping 设备）→
   并发 ICMP（拿延迟）→ ping 后补读一次 ARP（补 MAC）→ mDNS 浏览 → 反向 DNS/NetBIOS → TCP 端口指纹。
2. **设备类型推断顺序**（`oui.infer_kind`）：强特征端口 → 主机名关键词 → 端口组合 →
   mDNS 服务 → 厂商 → 弱端口兜底。所以 NAS 不会被 554 认成摄像头，MacBook 不会被认成 Apple TV。
3. **设备台账按 MAC 为主键**（IP 兜底），每次扫描结束由 `ScanManager.on_finish` 归档一次：
   见过的标记在线并累加 `seen_count`，没出现的标记掉线但**保留记录**。
4. **只有落在本次扫描网段内的设备才会被判掉线**（扫别的网段不误伤）；演示模式的假设备不进台账。
5. **人工编辑**（别名/分类/位置/标签/备注/类型覆盖/关注/忽略/**图标**）存在记录的 `custom` 里，
   重扫不覆盖；通过 `apply_to_snapshot()` 贴回扫描结果，首页方块墙与结果表优先显示别名。
   加人工字段只需改一处：`scanner.EDITABLE_FIELDS`（存储、reset、`_flatten`、`apply_to_snapshot`
   都按它遍历），再在前端弹窗里加控件即可 —— 但 `_flatten` / `apply_to_snapshot` 里要记得
   显式带出新字段，不然前端拿不到。
   `icon` 是设备图标：`deviceIcon(dev)` 优先用人工值，为空才按类型/主机名/厂商猜；
   候选项在 `static/app.js` 的 `ICON_CHOICES`（由 `DEVICE_ICONS` 自动去重生成，保证风格一致）。
6. **定时重扫在服务端**（不是浏览器定时器），配置落 `data/auto.json`，重启后按原节奏续排期。

## 已知坑（都踩过）

1. **macOS 自带 bash 3.2**：`$VAR` 后面紧跟中文全角字符时，会把该字符首字节吃进变量名，
   输出乱码。**shell 脚本里变量一律写 `${VAR}`**（`desktop/` 下的脚本已全部如此）。
   还有两个相关的坑（`desktop/局域网扫描服务.command` 踩过）：
   `read -t` **只认整数秒**（`-t 0.5` 报 invalid timeout specification）；
   `read -t` **超时返回 1，不是常见的 128+SIGALRM=142** —— 它和 EOF 的退出码一模一样，
   所以菜单循环只能靠「耗时是否等满超时秒数」区分超时与输入结束，用退出码判断会把
   每次超时都当成 EOF 直接退出菜单（现象：状态面板不再自动刷新）。
   回归测试见 `tests/launcher.test.sh`，用变体测试验过它确实能抓到这个 bug。
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
8. **推 Docker Hub 的代理问题**（三个结论，别再试错）：
   ① BuildKit 的 registry 解析器**不认** `HTTP(S)_PROXY`，`--driver-opt env.HTTPS_PROXY=...`
   大小写都加也没用，照样 `dial tcp ...:443: i/o timeout`；走代理的是 **docker CLI** 那次
   `auth.docker.io` token 请求，所以必须在带 `HTTPS_PROXY` 的本机 shell 里跑。
   ② 因此**不能用 `docker-container` 驱动推镜像**（推的是 VM 里的 buildkitd，不走代理），
   要用 **`docker` 驱动**（`--builder $(docker context show)`）。
   ③ Docker 29 的 `docker` 驱动**已经支持** `--platform a,b --push` 一次生成并推送
   manifest list，不用 build 两次再 `docker manifest create` 拼。
   ④ 装了 buildx 插件后 `docker build` 会走 BuildKit 并写 `~/.docker/buildx`，
   受限环境会报 `mkdir ...: operation not permitted` —— `tests/docker_smoke.sh` 和
   `docker-push.sh` 都已 `export BUILDX_CONFIG=${PWD}/.buildx`（该目录已 gitignore）。
   ⑤ **登录凭据**：本机已配 `"credsStore": "osxkeychain"`（`brew install docker-credential-helper`），
   令牌在 macOS 钥匙串里，`~/.docker/config.json` 里没有明文。**关键坑**：`docker info` 的
   `Username:` 行只在明文 `auths` 存在时才出现，用了钥匙串就不显示 —— 别用它判断登录状态
   （`docker-push.sh` 已改成先问 `docker-credential-<store>`，再退回看 `auths`）。
   另外 `docker login` 一行命令要写成 `HTTPS_PROXY=... docker login -u X`，
   **分行粘贴会丢换行**，zsh 报 `export: not valid in this context: -u`。

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
./tests/run.sh                            # 跑全部测试（含启动脚本那套）
./tests/launcher.test.sh                  # 只跑桌面启动脚本测试（12 项）
./tests/docker_smoke.sh                   # 容器冒烟测试（27 项）
```
