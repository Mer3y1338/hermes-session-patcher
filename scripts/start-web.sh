#!/bin/bash
# 启动 Web UI
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
$PY -m hermes_session_patcher.web.backend.main "$@"
