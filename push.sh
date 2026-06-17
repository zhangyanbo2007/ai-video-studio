#!/bin/bash
# 推送到 GitHub
# 用法: ./push.sh [commit_msg]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

MSG="${1:-update: $(date '+%Y-%m-%d %H:%M')}"

# unset 失效的 GITHUB_TOKEN，让 gh credential helper 生效
unset GITHUB_TOKEN
export https_proxy=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897

echo "  推送到 GitHub..."
git add -A
git commit -m "$MSG" || echo "没有新改动"
git push -u origin main 2>&1

echo "✅ 推送完成"
