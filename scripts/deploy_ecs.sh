#!/usr/bin/env bash
# ECS / 单机 Linux 一键部署：可重复执行；默认以非 root 用户运行 Web 进程。
# 用法（在项目根目录，或任意目录指定 CASE_ROOT）：
#   sudo bash scripts/deploy_ecs.sh
#   CASE_ROOT=/opt/CASE-Excel_merge sudo -E bash scripts/deploy_ecs.sh
#
# 注意：默认不删除 hr_excel_web/uploads 与 exports；DEPLOY_CLEAN_DATA=1 时危险。
# DEPLOY_SKIP_SYSTEMD=1 时为调试模式（不建专用用户、venv 由 root 创建，勿用于生产）。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CASE_ROOT="${CASE_ROOT:-$DEFAULT_ROOT}"
SERVICE_NAME="${CASE_SERVICE_NAME:-case-excel-web}"
ENV_FILE="${CASE_ENV_FILE:-/etc/default/case-excel-web}"
UNIT_DST="/etc/systemd/system/${SERVICE_NAME}.service"

# 运行 Web 的系统用户（与同名组）；不存在则自动创建
CASE_RUN_USER="${CASE_RUN_USER:-caseexcel}"
CASE_RUN_GROUP="${CASE_RUN_GROUP:-$CASE_RUN_USER}"

export HR_WEB_HOST="${HR_WEB_HOST:-0.0.0.0}"
export HR_WEB_PORT="${HR_WEB_PORT:-5001}"
export HR_WEB_DEBUG="${HR_WEB_DEBUG:-0}"

DEPLOY_PURGE_VENV="${DEPLOY_PURGE_VENV:-0}"
DEPLOY_CLEAN_DATA="${DEPLOY_CLEAN_DATA:-0}"
DEPLOY_SKIP_SYSTEMD="${DEPLOY_SKIP_SYSTEMD:-0}"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

die() {
  log "错误: $*"
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "未找到命令: $1"
}

cd "$CASE_ROOT" || die "无法进入目录: $CASE_ROOT"

log "======== CASE-Excel_merge ECS 部署 ========"
log "项目根目录: $CASE_ROOT"
log "服务名: $SERVICE_NAME | systemd: $UNIT_DST"
log "运行用户: $CASE_RUN_USER（生产模式） / DEPLOY_SKIP_SYSTEMD=$DEPLOY_SKIP_SYSTEMD"
log "HR_WEB_HOST=$HR_WEB_HOST HR_WEB_PORT=$HR_WEB_PORT HR_WEB_DEBUG=$HR_WEB_DEBUG"
log "DEPLOY_PURGE_VENV=$DEPLOY_PURGE_VENV DEPLOY_CLEAN_DATA=$DEPLOY_CLEAN_DATA"
echo ""

# --- 1. 停止服务 ---
step_stop() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    log "[1/10] 跳过停止服务（DEPLOY_SKIP_SYSTEMD=1）"
    return 0
  fi
  if ! command -v systemctl >/dev/null 2>&1; then
    log "[1/10] 未检测到 systemctl，跳过"
    return 0
  fi
  if [[ -f "$UNIT_DST" ]]; then
    log "[1/10] 停止服务: ${SERVICE_NAME}"
    systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
    sleep 1
  else
    log "[1/10] 未发现已安装单元，跳过 stop"
  fi
}

# --- 2. 创建运行用户（仅生产路径）---
step_create_user() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    log "[2/10] 跳过创建专用用户（调试模式）"
    return 0
  fi
  if id -u "$CASE_RUN_USER" &>/dev/null; then
    log "[2/10] 运行用户已存在: $CASE_RUN_USER"
  else
    log "[2/10] 创建系统用户与组: $CASE_RUN_USER"
    useradd --system --user-group --no-create-home --shell /usr/sbin/nologin \
      --comment "CASE-Excel_merge web" "$CASE_RUN_USER" || die "useradd 失败"
  fi
}

# --- 3. 可选清理数据 ---
step_clean_data() {
  if [[ "$DEPLOY_CLEAN_DATA" != "1" ]]; then
    log "[3/10] 保留上传与导出目录"
    return 0
  fi
  log "[3/10] 警告: 清理 uploads / exports / audit_log.csv"
  rm -rf "$CASE_ROOT/hr_excel_web/uploads" "$CASE_ROOT/hr_excel_web/exports" 2>/dev/null || true
  mkdir -p "$CASE_ROOT/hr_excel_web/uploads" "$CASE_ROOT/hr_excel_web/exports"
  rm -f "$CASE_ROOT/hr_excel_web/audit_log.csv" 2>/dev/null || true
}

# --- 4. 目录权限：归运行用户所有 ---
step_chown_project() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    log "[4/10] 跳过 chown（调试模式）"
    return 0
  fi
  log "[4/10] 设置项目目录属主: $CASE_RUN_USER:$CASE_RUN_GROUP"
  mkdir -p "$CASE_ROOT/hr_excel_web/uploads" "$CASE_ROOT/hr_excel_web/exports"
  chown -R "$CASE_RUN_USER:$CASE_RUN_GROUP" "$CASE_ROOT"
  chmod u+rwX,go-rwx "$CASE_ROOT/hr_excel_web/uploads" "$CASE_ROOT/hr_excel_web/exports" 2>/dev/null || true
}

# --- 5～6. venv 与 pip ---
step_venv() {
  need_cmd python3
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    if [[ "$DEPLOY_PURGE_VENV" == "1" ]]; then
      log "[5/10] 删除 venv（调试）"
      rm -rf "$CASE_ROOT/venv"
    fi
    if [[ ! -d "$CASE_ROOT/venv" ]]; then
      log "[5/10] 创建 venv（root）"
      python3 -m venv "$CASE_ROOT/venv" || die "创建 venv 失败"
    fi
    # shellcheck source=/dev/null
    source "$CASE_ROOT/venv/bin/activate"
    log "[6/10] pip 安装依赖（root 调试环境）"
    python -m pip install -U pip
    pip install -r "$CASE_ROOT/requirements.txt"
    return 0
  fi

  if [[ "$DEPLOY_PURGE_VENV" == "1" ]]; then
    log "[5/10] 删除旧 venv（DEPLOY_PURGE_VENV=1）"
    rm -rf "$CASE_ROOT/venv"
  fi
  if [[ ! -d "$CASE_ROOT/venv" ]]; then
    log "[5/10] 以 $CASE_RUN_USER 创建 venv"
    sudo -u "$CASE_RUN_USER" env HOME="$CASE_ROOT" bash -lc "cd '$CASE_ROOT' && python3 -m venv venv" \
      || die "创建 venv 失败，请确认已 chown 且已安装 python3-venv"
  else
    log "[5/10] 已存在 venv，更新依赖"
  fi
  log "[6/10] 以 $CASE_RUN_USER 执行 pip install"
  sudo -u "$CASE_RUN_USER" env HOME="$CASE_ROOT" bash -lc "
    set -e
    cd '$CASE_ROOT'
    source venv/bin/activate
    python -m pip install -U pip
    pip install -r requirements.txt
  " || die "pip install 失败"
}

# --- 7. 环境文件（systemd 以 root 读取后注入进程，文件可 600）---
step_env_file() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    log "[7/10] 跳过 $ENV_FILE"
    return 0
  fi
  log "[7/10] 写入 $ENV_FILE（合并 HR_WEB_*，保留其它行如 HR_WEB_SECRET_KEY）"
  umask 077
  tmpf="$(mktemp)"
  if [[ -f "$ENV_FILE" ]]; then
    grep -vE '^HR_WEB_(HOST|PORT|DEBUG)=' "$ENV_FILE" | grep -v '^# 由 scripts/deploy_ecs.sh' >"$tmpf" || true
  else
    : >"$tmpf"
  fi
  {
    echo "# 由 scripts/deploy_ecs.sh 维护以下三行；密钥建议用 HR_WEB_SECRET_KEY="
    echo "HR_WEB_HOST=${HR_WEB_HOST}"
    echo "HR_WEB_PORT=${HR_WEB_PORT}"
    echo "HR_WEB_DEBUG=${HR_WEB_DEBUG}"
  } >>"$tmpf"
  install -m 600 -o root -g root "$tmpf" "$ENV_FILE"
  rm -f "$tmpf"
}

# --- 8. systemd 单元（User= 非 root）---
step_systemd_unit() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    log "[8/10] 跳过 systemd"
    return 0
  fi
  log "[8/10] 安装 systemd 单元（User=$CASE_RUN_USER）"
  cat <<EOF >"/tmp/${SERVICE_NAME}.service"
[Unit]
Description=CASE-Excel_merge HR Web (Flask)
After=network.target

[Service]
Type=simple
User=${CASE_RUN_USER}
Group=${CASE_RUN_GROUP}
WorkingDirectory=${CASE_ROOT}
EnvironmentFile=-${ENV_FILE}
ExecStart=${CASE_ROOT}/venv/bin/python ${CASE_ROOT}/main.py
Restart=on-failure
RestartSec=5
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
  install -m 644 "/tmp/${SERVICE_NAME}.service" "$UNIT_DST"
  rm -f "/tmp/${SERVICE_NAME}.service"
  systemctl daemon-reload
  systemctl enable "${SERVICE_NAME}"
}

# --- 9. 启动 ---
step_start() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    log "[9/10] 跳过 systemctl start"
    return 0
  fi
  log "[9/10] 启动服务: ${SERVICE_NAME}"
  systemctl start "${SERVICE_NAME}"
  sleep 2
  systemctl --no-pager -l status "${SERVICE_NAME}" || true
}

# --- 10. 健康检查 ---
step_health() {
  local url="http://127.0.0.1:${HR_WEB_PORT}/"
  log "[10/10] 健康检查: $url"
  if command -v curl >/dev/null 2>&1; then
    code="$(curl -sS -o /dev/null -w '%{http_code}' "$url" || echo "000")"
    if [[ "$code" == "200" ]] || [[ "$code" == "302" ]] || [[ "$code" == "301" ]]; then
      log "健康检查通过 (HTTP $code)"
    else
      log "HTTP $code；日志: journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
    fi
  else
    log "未安装 curl，跳过 HTTP 检查"
  fi
}

if [[ "$DEPLOY_SKIP_SYSTEMD" != "1" ]] && [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  die "生产部署需 root：sudo bash $0 ；仅调试可加 DEPLOY_SKIP_SYSTEMD=1"
fi

step_stop
step_create_user
step_clean_data
step_chown_project
step_venv
step_env_file
step_systemd_unit
step_start
step_health

echo ""
log "======== 部署结束 ========"
log "进程以系统用户 $CASE_RUN_USER 运行（非 root）"
log "systemctl status ${SERVICE_NAME} | journalctl -u ${SERVICE_NAME} -f"
echo ""
