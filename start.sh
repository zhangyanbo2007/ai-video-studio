#!/bin/bash
# AI 图片视频生成器 - 启动脚本
# 用法: ./start.sh [local|frp|all|push]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MODE="${1:-all}"

start_server() {
    echo "✨ 启动 AI 图片视频生成器..."
    source .venv/bin/activate
    python server.py
}

push_github() {
    echo "  推送到 GitHub..."

    # unset 失效的 GITHUB_TOKEN，让 gh credential helper 生效
    unset GITHUB_TOKEN
    export https_proxy=http://127.0.0.1:7897
    export HTTPS_PROXY=http://127.0.0.1:7897

    git add -A
    git commit -m "update: $(date '+%Y-%m-%d %H:%M')" || echo "没有新改动"
    git push -u origin main 2>&1

    echo "✅ 推送完成"
}

start_frp() {
    echo "  启动 FRP 隧道 (8870 -> 8879)..."

    # 从 frp-config.json 读取配置
    VPS_HOST=$(python3 -c "import json; c=json.load(open('frp-config.json')); print(c['vps']['host'])")
    VPS_USER=$(python3 -c "import json; c=json.load(open('frp-config.json')); print(c['vps']['ssh_user'])")
    VPS_PASS=$(python3 -c "import json; c=json.load(open('frp-config.json')); print(c['vps']['ssh_password'])")
    FRP_PORT=$(python3 -c "import json; c=json.load(open('frp-config.json')); print(c['vps']['frp_control_port'])")

    # 创建临时 frpc 配置
    cat > /tmp/frpc_video.ini << EOF
[common]
server_addr = $VPS_HOST
server_port = $FRP_PORT

[node37-video-studio]
type = tcp
local_ip = 127.0.0.1
local_port = 8879
remote_port = 8870
EOF

    echo "  FRP 配置已生成: /tmp/frpc_video.ini"
    echo "  VPS: $VPS_HOST:$FRP_PORT"
    echo "  映射: 127.0.0.1:8879 -> $VPS_HOST:8870"
    echo ""

    # 启动 frpc
    frpc -c /tmp/frpc_video.ini
}

case "$MODE" in
    local)
        start_server
        ;;
    frp)
        start_frp
        ;;
    all)
        # 后台启动服务，前台启动 frp
        start_server &
        SERVER_PID=$!
        sleep 2
        start_frp
        kill $SERVER_PID 2>/dev/null
        ;;
    push)
        push_github
        ;;
    *)
        echo "用法: $0 [local|frp|all|push]"
        echo "  local - 仅启动本地服务"
        echo "  frp   - 仅启动 FRP 隧道"
        echo "  all   - 同时启动（默认）"
        echo "  push  - 推送到 GitHub"
        exit 1
        ;;
esac
