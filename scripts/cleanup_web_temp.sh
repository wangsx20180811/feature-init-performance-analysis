#!/usr/bin/env bash
# Web 上传/导出目录：删除「最后修改时间」早于保留天数的文件（默认 7 天）。
# 由 systemd timer 每日触发；需 EnvironmentFile 提供 CASE_EXCEL_PROJECT_ROOT、CASE_CLEANUP_RETENTION_DAYS。
# 不处理 audit_log.csv（审计需单独策略）。
set -euo pipefail

ROOT="${CASE_EXCEL_PROJECT_ROOT:?未设置 CASE_EXCEL_PROJECT_ROOT，请检查 /etc/default/case-excel-web}"
DAYS="${CASE_CLEANUP_RETENTION_DAYS:-7}"

if ! [[ "$DAYS" =~ ^[0-9]+$ ]] || [[ "$DAYS" -lt 1 ]]; then
  echo "错误: CASE_CLEANUP_RETENTION_DAYS 须为 >=1 的整数，当前: ${DAYS}" >&2
  exit 1
fi

UP="${ROOT}/hr_excel_web/uploads"
EX="${ROOT}/hr_excel_web/exports"

if [[ -d "$UP" ]]; then
  find "$UP" -type f -mtime "+${DAYS}" -delete 2>/dev/null || true
  find "$UP" -type d -empty -delete 2>/dev/null || true
fi
if [[ -d "$EX" ]]; then
  find "$EX" -type f -mtime "+${DAYS}" -delete 2>/dev/null || true
  find "$EX" -type d -empty -delete 2>/dev/null || true
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') case-excel-web-cleanup: 完成 mtime+${DAYS} 天清理，项目根=${ROOT}"
exit 0
