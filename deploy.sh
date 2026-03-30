#!/usr/bin/env bash
# CASE-Excel_merge 一键部署（Linux / macOS）
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo ""
echo "=== CASE-Excel_merge 一键部署 ==="
echo "项目目录: $ROOT"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
  echo "[错误] 未找到 python3，请先安装 Python 3.10+。"
  exit 1
fi

if [ ! -d "venv" ]; then
  echo "[1/2] 创建虚拟环境 venv ..."
  if ! python3 -m venv venv; then
    echo "[错误] 创建 venv 失败。Ubuntu/Debian 请先: sudo apt update && sudo apt install -y python3-venv（或 python3.12-venv 等与 python3 主版本一致的包）"
    exit 1
  fi
else
  echo "[1/2] 已存在 venv，跳过创建。"
fi

echo "[2/2] 安装/更新依赖 requirements.txt ..."
# shellcheck source=/dev/null
source "$ROOT/venv/bin/activate"
python -m pip install -U pip
pip install -r "$ROOT/requirements.txt"

echo ""
echo "部署完成。"
echo "下一步: ./run_hr_web.sh  或  source venv/bin/activate && python main.py"
echo "ECS / Linux 生产环境（systemd）请使用: sudo bash scripts/deploy_ecs.sh（见 README）"
echo ""
