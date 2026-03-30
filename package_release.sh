#!/usr/bin/env bash
# 在项目根目录执行：生成可上传到内网 Linux 的发布包（不含 venv、上传缓存等）
# 解压后得到单一顶层目录，便于部署。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PARENT="$(dirname "$ROOT")"
BASE="$(basename "$ROOT")"
STAMP=$(date +%Y%m%d_%H%M%S)
# 输出到项目上级目录，避免 tar 把正在生成的压缩包再次打入包内
ARCHIVE="${PARENT}/CASE-Excel_merge_release_${STAMP}.tar.gz"

echo "项目目录: $ROOT"
echo "输出文件: $ARCHIVE"

cd "$PARENT"
tar -czf "$ARCHIVE" \
  --exclude="${BASE}/venv" \
  --exclude="${BASE}/.git" \
  --exclude="${BASE}/.cursor" \
  --exclude="${BASE}/__pycache__" \
  --exclude="${BASE}/*/__pycache__" \
  --exclude="${BASE}/*.pyc" \
  --exclude="${BASE}/hr_excel_web/uploads" \
  --exclude="${BASE}/hr_excel_web/exports" \
  --exclude="${BASE}/hr_excel_web/audit_log.csv" \
  --exclude="${BASE}/intranet_employee_chat_project/exports" \
  --exclude="${BASE}/~\$*.xlsx" \
  --exclude="${BASE}/*/~\$*.xlsx" \
  --exclude="${BASE}/CASE-Excel_merge_release_*.tar.gz" \
  "$BASE"

echo ""
echo "打包完成: $ARCHIVE"
ls -lh "$ARCHIVE" 2>/dev/null || dir "$ARCHIVE"
echo ""
echo "上传到服务器后示例:"
echo "  tar -xzf $(basename "$ARCHIVE")"
echo "  cd $BASE"
echo "  chmod +x deploy.sh run_hr_web.sh package_release.sh scripts/deploy_ecs.sh scripts/cleanup_web_temp.sh"
echo "  （开发）./deploy.sh && source venv/bin/activate && python main.py"
echo "  （ECS 生产）sudo bash scripts/deploy_ecs.sh"
echo "  （若创建 venv 失败）apt update && apt install -y python3-venv"
