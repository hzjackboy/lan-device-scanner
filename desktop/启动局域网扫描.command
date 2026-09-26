#!/bin/bash
# 双击启动局域网设备扫描服务，并自动打开页面
# 实际逻辑都在「局域网扫描服务.command」里，这里只是快捷方式
exec "$(cd "$(dirname "$0")" && pwd)/局域网扫描服务.command" start
