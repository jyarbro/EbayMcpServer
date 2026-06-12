#!/bin/bash
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

pip install -q "mcp[cli]>=1.3.0" pydantic "requests>=2.28.0" "starlette>=0.27.0" "uvicorn>=0.24.0" httpx
