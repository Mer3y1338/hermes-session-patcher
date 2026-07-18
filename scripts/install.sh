#!/bin/bash
# 安装脚本
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
$PY -m pip install -e . 2>&1
echo "✓ 已安装。运行 hermes-patcher --help 查看"

# 创建存档目录
mkdir -p ~/.hermes-session-patcher/backups
