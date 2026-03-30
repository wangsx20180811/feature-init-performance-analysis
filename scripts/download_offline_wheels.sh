#!/usr/bin/env bash
# 在与生产一致的环境（推荐 Ubuntu 24.04 x86_64 + Python 3.12）下载 requirements 及 pip 工具链 wheel，
# 供离线部署。勿在 Windows 上作为 Linux ECS 的离线包来源。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ROOT}/offline_wheels"
REQ="${ROOT}/requirements.txt"

cd "$ROOT"
need_cmd() { command -v "$1" >/dev/null 2>&1 || { echo "错误: 未找到 $1"; exit 1; }; }

need_cmd python3
if ! python3 -m pip --version >/dev/null 2>&1; then
  echo "错误: python3 无 pip，请先: apt install -y python3-pip python3-venv"
  exit 1
fi

mkdir -p "$OUT"
echo "输出目录: $OUT"
echo "Python: $(python3 --version)"
echo "requirements: $REQ"
echo ""

# 直接依赖 + 升级 pip/setuptools/wheel 所需（便于 deploy 里先离线升级 pip）
python3 -m pip download -r "$REQ" -d "$OUT"
python3 -m pip download pip setuptools wheel -d "$OUT"

if command -v sha256sum >/dev/null 2>&1; then
  (cd "$ROOT" && sha256sum requirements.txt >"$OUT/.requirements.sha256")
  echo "已写入 $OUT/.requirements.sha256"
fi

n=$(find "$OUT" -maxdepth 1 -name '*.whl' 2>/dev/null | wc -l)
echo ""
echo "完成: 已下载 wheel 约 $n 个（含 pip/setuptools/wheel）。"
echo "下一步: bash package_release.sh 打发布包（含本目录）。"
echo ""
