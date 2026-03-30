#!/usr/bin/env bash
# 在宿主机已安装 Docker 的前提下，用官方 ubuntu:24.04 容器生成与阿里云 ECS（Ubuntu 24.04 x86_64）一致的 offline_wheels。
# 生成的文件写入项目目录 offline_wheels/，再执行 package_release.sh 即可把 wheel 打进 tar.gz，无需在 ECS 上生成再拷回开发机。
# 用法（在项目根目录，Git Bash / Linux / macOS）：
#   chmod +x scripts/download_offline_wheels_docker.sh
#   bash scripts/download_offline_wheels_docker.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "错误: 未找到 docker，请先安装 Docker Desktop（Windows）或 docker.io（Linux）。"
  exit 1
fi

echo "项目根目录: $ROOT"
echo "将拉取 ubuntu:24.04 并在容器内执行 scripts/download_offline_wheels.sh（需联网下载 apt 与 PyPI）。"
echo ""

docker run --rm \
  -v "${ROOT}:/work" \
  -w /work \
  ubuntu:24.04 \
  bash -c '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv ca-certificates curl
echo "容器内: $(python3 --version)"
chmod +x scripts/download_offline_wheels.sh 2>/dev/null || true
bash scripts/download_offline_wheels.sh
'

echo ""
echo "完成。offline_wheels/ 已写入当前项目目录，下一步可执行: bash package_release.sh"
