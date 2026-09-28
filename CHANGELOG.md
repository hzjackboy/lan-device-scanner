# 更新日志

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)：`主版本.次版本.修订号`。
版本号在 `server.py` 的 `VERSION` 常量里，页脚与顶栏徽标由 `/api/status` 动态取。

## [1.1.0] — 2026-09-28

从"能扫"做到"能管、能部署"。本次加入设备台账、定时重扫、容器化与回归测试。

### 新增

- **设备管理（设备台账）**：按 MAC 为主键长期记录扫到过的设备，掉线的设备保留记录并标记离线。
  支持人工编辑别名 / 分类 / 位置 / 标签 / 备注 / 类型覆盖，以及"关注""忽略"；
  重扫不覆盖人工内容，可一键恢复自动识别。落盘 `data/devices.json`。
- **首页设备方块墙 + 在线离线环形饼图**：扫描结果以方块图标展示，饼图统计在线 / 离线占比。
- **首页定时重扫**：服务端 `AutoScheduler`（默认 3600 秒，最小 60 秒），关掉页面也继续跑，
  配置落 `data/auto.json`，服务重启后按原节奏续排期。
- **侧边栏导航 + hash 路由**：首页 / 设备扫描 / 历史记录 / 设备管理 / 关于与说明。
- **批量删除**：设备管理支持行内删除、多选批量删除、一键清除离线 / 忽略 / 全部。
- **台账导出**：`/api/devices/export?format=csv|json`。
- **桌面启动器**：`desktop/局域网扫描服务.command` 单文件搞定启动 / 停止 / 重启 / 打开页面 / 看日志。
- **容器化部署**：`Dockerfile` + `docker-compose.yml`（**必须 host 网络**，否则 ARP 扫不到局域网）。
- **测试**：`./tests/run.sh` 共 8 套 113 项检查（5 套离线 UI + 3 套联调），
  另有 `tests/docker_smoke.sh` 容器冒烟测试 27 项。
- **`AGENTS.md`**：压缩后的项目上下文，新会话自动加载。

### 修复

- **设备管理改名后首页不同步**：台账别名此前只在 `GET /api/scan/<id>` 贴上，
  SSE 推的帧没有；编辑保存后也没重取快照。现在三个出口都贴，前端 `applySnapshot` 记录 `scanId`。
- **macOS `arp -an` 省略前导零**（`8:9b:4b:...`）导致 OUI 查不到厂商，
  27/57 台设备的厂商丢失。现在按 octet 补零。
- **NetBIOS 应答不回显 question 段**导致读出 `ROUP` 之类垃圾主机名，改为按 header `qdcount` 跳过。
- **mDNS 的 SRV 记录解析**：读 `rec["host"]` 而不是 `target`，此前 browse 恒返回 0 条。
- **设备类型误判**：`infer_kind` 调整判定顺序（强特征端口 → 主机名关键词 → 端口组合 →
  mDNS 服务 → 厂商 → 弱端口兜底），NAS 不再被 554 端口认成摄像头，MacBook 不再被认成 Apple TV。
- **busybox 版 ping 不认 `-n`**：此前会导致每台设备都判"离线"却不报错（静默全失败）。
  现在遇到用法错误自动去掉 `-n` 重试一次，并在日志里提示。
- **演示设备污染台账**：演示模式的假设备不进真实台账。
- **跨网段误判掉线**：只有落在本次扫描网段内的设备才会被判离线，扫别的网段不误伤。

### 已知限制

macOS 上（Docker Desktop 与 colima 都一样）host 网络仍只是虚拟机内网，
实测容器看到 `192.168.5.0/24` 而非宿主机的 `10.0.0.0/24`，
因此**真实 ARP 扫描请用宿主机直跑**，或把容器部署到 Linux 主机 / 软路由 / NAS / K8s（`hostNetwork: true`）上。
详见 README 的「Docker 部署」。

## [1.0.0] — 2026-09-25

首个版本：零依赖局域网扫描服务。

- Python 标准库 HTTP 服务 + 原生 JS 前端，不需要 root、不装任何第三方包。
- 发现手段：ARP 缓存 → UDP 触发 ARP 解析（非 root 拿 MAC、能发现禁 ping 设备）→
  并发 ICMP → ping 后补读 ARP → mDNS/Bonjour 浏览 → 反向 DNS / NetBIOS → TCP 端口指纹。
- 自实现 mDNS（含压缩指针解析）与 NetBIOS NBSTAT 报文。
- OUI 厂商库：内置常用表 + IEEE 全量 `oui.csv`（4 万条，`python3 update_oui.py` 获取）。
- 实时 Web 界面：SSE 推送扫描进度，设备逐台出现，含网段分布热力图、CSV/JSON 导出。

[1.1.0]: https://github.com/hzjackboy/lan-device-scanner/releases/tag/v1.1.0
[1.0.0]: https://github.com/hzjackboy/lan-device-scanner/releases/tag/v1.0.0
