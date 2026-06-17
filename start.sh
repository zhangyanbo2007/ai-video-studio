#!/bin/bash
# AI 图片视频生成器 - 启动脚本
# 用法: ./start.sh [local|frp|all]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MODE="${1:-all}"

start_server() {
    echo "✨ 启动 AI 图片视频生成器..."
    source .venv/bin/activate
    python server.py
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
    *)
        echo "用法: $0 [local|frp|all]"
        echo "  local - 仅启动本地服务"
        echo "  frp   - 仅启动 FRP 隧道"
        echo "  all   - 同时启动（默认）"
        exit 1
        ;;
esac
