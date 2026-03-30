#!/usr/bin/env bash
# ECS / 单机 Linux 一键部署：可重复执行；默认以非 root 用户运行 Web 进程。
# 用法（在项目根目录，或任意目录指定 CASE_ROOT）：
#   sudo bash scripts/deploy_ecs.sh
#   CASE_ROOT=/opt/CASE-Excel_merge sudo -E bash scripts/deploy_ecs.sh
#
# 部署日志：默认写入 ${CASE_ROOT}/logs/deploy_YYYYMMDD_HHMMSS.log（stdout/stderr 全量 tee）。
# 可预先 export DEPLOY_LOG_FILE=路径 或 DEPLOY_LOG_DIR=目录 覆盖。
#
# 注意：默认不删除 hr_excel_web/uploads 与 exports；DEPLOY_CLEAN_DATA=1 时危险。
# DEPLOY_SKIP_SYSTEMD=1 时为调试模式（不建专用用户、venv 由 root 创建，勿用于生产）。
# 首次部署默认在 /etc/default/case-excel-web 中生成 HR_WEB_SECRET_KEY 与 HR_WEB_PASSWORD_*（若尚未配置），
# 凭据副本见 /root/.case-excel-web.initial；pip 支持重试与国内镜像（DEPLOY_PIP_*）。

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
# 首次部署：自动生成 HR_WEB_SECRET_KEY；登录口令默认「账号=密码」由应用内置（不写 HR_WEB_PASSWORD_*）
DEPLOY_SEED_SECRETS="${DEPLOY_SEED_SECRETS:-1}"
# 设为 1 时且 env 中尚无 HR_WEB_PASSWORD_* 时，写入随机统一口令（与「账号=密码」二选一，一般保持 0）
DEPLOY_GENERATE_LOGIN_PASSWORDS="${DEPLOY_GENERATE_LOGIN_PASSWORDS:-0}"
# pip 网络不稳时加大重试与超时；国内 ECS 可设 DEPLOY_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
DEPLOY_PIP_RETRIES="${DEPLOY_PIP_RETRIES:-5}"
DEPLOY_PIP_TIMEOUT="${DEPLOY_PIP_TIMEOUT:-120}"
DEPLOY_PIP_INDEX_URL="${DEPLOY_PIP_INDEX_URL:-}"
# 永久配置 pip 镜像源（对所有用户生效）：写入 /etc/pip.conf
DEPLOY_CONFIGURE_PIP_MIRROR="${DEPLOY_CONFIGURE_PIP_MIRROR:-1}"
DEPLOY_PIP_MIRROR_INDEX_URL="${DEPLOY_PIP_MIRROR_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple}"
DEPLOY_PIP_MIRROR_TRUSTED_HOST="${DEPLOY_PIP_MIRROR_TRUSTED_HOST:-mirrors.aliyun.com}"
# 设为 1 时即使存在 offline_wheels 也走在线 PyPI（排查离线包问题用）
DEPLOY_FORCE_ONLINE_PIP="${DEPLOY_FORCE_ONLINE_PIP:-0}"
# Web 上传/导出：超过 N 天未修改则删除（systemd timer）；0 表示不安装清理定时器
CASE_CLEANUP_RETENTION_DAYS="${CASE_CLEANUP_RETENTION_DAYS:-7}"
CASE_CLEANUP_TIMER_ENABLE="${CASE_CLEANUP_TIMER_ENABLE:-1}"
# 部署日志目录（默认项目下 logs/）；也可预先 export DEPLOY_LOG_FILE=/path/deploy.log 指定完整路径
DEPLOY_LOG_DIR="${DEPLOY_LOG_DIR:-}"

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

# 创建 venv 前探测：避免 ensurepip 缺失时才报错（Ubuntu 最小化安装常见）
verify_python_can_create_venv() {
  local td err
  td="$(mktemp -d)"
  err="$(mktemp)"
  if ! python3 -m venv "$td/t" 2>"$err"; then
    log "python3 -m venv 失败，诊断输出:"
    sed 's/^/  | /' "$err" 2>/dev/null || cat "$err"
    rm -rf "$td" "$err"
    die "python3 无法创建含 pip 的虚拟环境。Ubuntu/Debian 请先: apt update && apt install -y python3-venv（或 python3.12-venv 等与系统 python3 主版本一致的包）"
  fi
  rm -rf "$td" "$err"
}

# 是否存在可用离线 wheel（offline_wheels/*.whl）
_use_offline_wheels() {
  [[ "${DEPLOY_FORCE_ONLINE_PIP}" == "1" ]] && return 1
  [[ -d "${CASE_ROOT}/offline_wheels" ]] || return 1
  compgen -G "${CASE_ROOT}/offline_wheels"/*.whl >/dev/null 2>&1
}

# 对比 requirements.txt 与生成离线包时记录的 sha256（可选）
_check_offline_requirements_sha() {
  if ! _use_offline_wheels; then
    return 0
  fi
  local f="${CASE_ROOT}/offline_wheels/.requirements.sha256"
  if [[ ! -f "$f" ]]; then
    log "提示: offline_wheels 无 .requirements.sha256，无法自动校验 requirements 是否与生离线包时一致"
    return 0
  fi
  if (cd "$CASE_ROOT" && sha256sum -c "$f" --status) 2>/dev/null; then
    log "offline_wheels 与当前 requirements.txt 校验一致"
  else
    log "警告: requirements.txt 与生成离线包时不一致，离线安装可能失败；请重新执行 scripts/download_offline_wheels.sh 或改用 DEPLOY_FORCE_ONLINE_PIP=1"
  fi
}

# cd 失败时尚未 tee，错误仅到终端；请确认 CASE_ROOT 或从项目根执行
cd "$CASE_ROOT" || die "无法进入目录: $CASE_ROOT（部署日志尚未初始化）"

# 将后续标准输出、标准错误同时写入终端与部署专属日志（便于排错与留存原始输出）
if [[ -z "${DEPLOY_LOG_DIR}" ]]; then
  DEPLOY_LOG_DIR="${CASE_ROOT}/logs"
fi
mkdir -p "$DEPLOY_LOG_DIR" || die "无法创建日志目录: $DEPLOY_LOG_DIR"
if [[ -z "${DEPLOY_LOG_FILE:-}" ]]; then
  DEPLOY_LOG_FILE="${DEPLOY_LOG_DIR}/deploy_$(date '+%Y%m%d_%H%M%S').log"
fi
touch "$DEPLOY_LOG_FILE" || die "无法写入部署日志: $DEPLOY_LOG_FILE"
# 注意：此后 log()、pip、systemctl 等子命令输出均会追加到 DEPLOY_LOG_FILE
exec > >(tee -a "$DEPLOY_LOG_FILE") 2>&1
# 非 die() 路径下的命令失败时仍记录一行，便于对照日志末行排错
trap 'ec=$?; log "部署失败: 命令返回非零退出码 ${ec}"; exit "$ec"' ERR

log "======== CASE-Excel_merge ECS 部署 ========"
log "部署日志文件: $DEPLOY_LOG_FILE（标准输出与标准错误均记录）"
log "项目根目录: $CASE_ROOT"
log "服务名: $SERVICE_NAME | systemd: $UNIT_DST"
log "运行用户: $CASE_RUN_USER（生产模式） / DEPLOY_SKIP_SYSTEMD=$DEPLOY_SKIP_SYSTEMD"
log "HR_WEB_HOST=$HR_WEB_HOST HR_WEB_PORT=$HR_WEB_PORT HR_WEB_DEBUG=$HR_WEB_DEBUG"
log "DEPLOY_PURGE_VENV=$DEPLOY_PURGE_VENV DEPLOY_CLEAN_DATA=$DEPLOY_CLEAN_DATA"
log "DEPLOY_SEED_SECRETS=$DEPLOY_SEED_SECRETS DEPLOY_GENERATE_LOGIN_PASSWORDS=$DEPLOY_GENERATE_LOGIN_PASSWORDS"
log "pip: retries=$DEPLOY_PIP_RETRIES timeout=${DEPLOY_PIP_TIMEOUT}s PIP_INDEX_URL=${DEPLOY_PIP_INDEX_URL:-（未设，使用默认 PyPI）} DEPLOY_FORCE_ONLINE_PIP=$DEPLOY_FORCE_ONLINE_PIP"
log "Web 临时文件清理: CASE_CLEANUP_RETENTION_DAYS=$CASE_CLEANUP_RETENTION_DAYS CASE_CLEANUP_TIMER_ENABLE=$CASE_CLEANUP_TIMER_ENABLE"
echo ""

# 首次部署：向 /etc/default/case-excel-web 追加 HR_WEB_SECRET_KEY 与 HR_WEB_PASSWORD_*（若尚未配置）
seed_secrets_to_env_file() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    return 0
  fi
  if [[ "${DEPLOY_SEED_SECRETS}" != "1" ]]; then
    log "[8/12] 跳过初始密钥与登录密码（DEPLOY_SEED_SECRETS=0）"
    return 0
  fi
  need_cmd openssl
  local creds="/root/.case-excel-web.initial"
  local wrote_creds=0
  if grep -qE '^HR_WEB_SECRET_KEY=..+' "$ENV_FILE" 2>/dev/null; then
    log "[8/12] 已存在非空 HR_WEB_SECRET_KEY，跳过生成"
  else
    local sk_val
    sk_val="$(openssl rand -hex 32)"
    echo "HR_WEB_SECRET_KEY=${sk_val}" >>"$ENV_FILE"
    {
      echo "# CASE-Excel_merge 首次部署凭据（请备份后删除本文件）"
      echo "# 生成时间: $(date '+%Y-%m-%d %H:%M:%S %z')"
      echo "HR_WEB_SECRET_KEY=${sk_val}"
      echo ""
    } >"$creds"
    chmod 600 "$creds"
    wrote_creds=1
    log "[8/12] 已生成 HR_WEB_SECRET_KEY"
  fi
  if grep -qE '^[[:space:]]*(export[[:space:]]+)?HR_WEB_PASSWORD_' "$ENV_FILE" 2>/dev/null; then
    log "[8/12] 已存在 HR_WEB_PASSWORD_*，跳过随机登录密码"
  elif [[ "${DEPLOY_GENERATE_LOGIN_PASSWORDS}" != "1" ]]; then
    log "[8/12] 跳过随机登录密码（DEPLOY_GENERATE_LOGIN_PASSWORDS=0）；应用使用内置规则：初始密码与账号名相同，首次登录须网页改密"
  else
    # 可选：四个 HR_WEB_PASSWORD_* 使用同一随机串（与内置「账号=密码」互斥）
    local p0
    p0="$(openssl rand -hex 12)"
    {
      echo "HR_WEB_PASSWORD_HR_ADMIN=${p0}"
      echo "HR_WEB_PASSWORD_HR_USER=${p0}"
      echo "HR_WEB_PASSWORD_IT_ADMIN=${p0}"
      echo "HR_WEB_PASSWORD_VIEWER=${p0}"
    } >>"$ENV_FILE"
    if [[ "$wrote_creds" -eq 0 ]]; then
      {
        echo "# CASE-Excel_merge 首次部署凭据（请备份后删除本文件）"
        echo "# 生成时间: $(date '+%Y-%m-%d %H:%M:%S %z')"
      } >"$creds"
      chmod 600 "$creds"
      wrote_creds=1
    fi
    {
      echo "# 统一初始登录口令（hr_admin / hr_user / it_admin / viewer 均相同；登录后请在网页修改个人口令）"
      echo "统一初始口令=${p0}"
    } >>"$creds"
    log "[8/12] 已生成统一随机登录口令（四角色 HR_WEB_PASSWORD_* 相同）"
  fi
  if [[ "$wrote_creds" -eq 1 ]]; then
    log "[8/12] 凭据已写入 $creds（权限 600），请备份后删除该文件"
  fi
}

# --- 1. 环境检测（磁盘、Python、生产路径下 curl/systemd）---
step_env_check() {
  log "[1/12] 环境检测: 开始"
  log "[1/12] 内核: $(uname -srmo)"
  log "[1/12] 主机名: $(uname -n)"
  if command -v lsb_release >/dev/null 2>&1; then
    log "[1/12] 发行版: $(lsb_release -ds 2>/dev/null || true)"
  fi
  log "[1/12] 项目目录磁盘空间:"
  df -h "$CASE_ROOT" 2>/dev/null || df -h .
  log "[1/12] Python: $(python3 --version 2>&1)"

  # 永久配置 pip 镜像源（/etc/pip.conf，所有用户生效）
  if [[ "${DEPLOY_CONFIGURE_PIP_MIRROR}" == "1" ]]; then
    local pip_conf="/etc/pip.conf"
    local desired_index_url="${DEPLOY_PIP_INDEX_URL:-$DEPLOY_PIP_MIRROR_INDEX_URL}"
    local desired_trusted_host="${DEPLOY_PIP_MIRROR_TRUSTED_HOST}"

    if [[ -f "$pip_conf" ]] && grep -qE "^[[:space:]]*index-url[[:space:]]*=[[:space:]]*${desired_index_url}[[:space:]]*$" "$pip_conf" \
      && grep -qE "^[[:space:]]*trusted-host[[:space:]]*=[[:space:]]*${desired_trusted_host}[[:space:]]*$" "$pip_conf"; then
      log "[1/12] pip 镜像已配置（$pip_conf）"
    else
      log "[1/12] 写入 pip 全局镜像配置（$pip_conf）：$desired_index_url"
      cat >"$pip_conf" <<EOF
[global]
index-url = ${desired_index_url}
trusted-host = ${desired_trusted_host}
EOF
    fi
  else
    log "[1/12] 跳过配置 /etc/pip.conf（DEPLOY_CONFIGURE_PIP_MIRROR!=1）"
  fi

  need_cmd python3
  if [[ "$DEPLOY_SKIP_SYSTEMD" != "1" ]]; then
    need_cmd curl
    command -v systemctl >/dev/null 2>&1 || die "未找到 systemctl，无法安装 systemd 单元"
    log "[1/12] curl、systemd 可用"
  else
    log "[1/12] 调试模式（DEPLOY_SKIP_SYSTEMD=1）：不强制 curl / systemd"
  fi
  log "[1/12] 环境检测: 完成"
  echo ""
}

# --- 2. 停止服务 ---
step_stop() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    log "[2/12] 跳过停止服务（DEPLOY_SKIP_SYSTEMD=1）"
    return 0
  fi
  if ! command -v systemctl >/dev/null 2>&1; then
    log "[2/12] 未检测到 systemctl，跳过"
    return 0
  fi
  if [[ -f "$UNIT_DST" ]]; then
    log "[2/12] 停止服务: ${SERVICE_NAME}"
    systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
    sleep 1
  else
    log "[2/12] 未发现已安装单元，跳过 stop"
  fi
}

# --- 3. 创建运行用户（仅生产路径）---
step_create_user() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    log "[3/12] 跳过创建专用用户（调试模式）"
    return 0
  fi
  if id -u "$CASE_RUN_USER" &>/dev/null; then
    log "[3/12] 运行用户已存在: $CASE_RUN_USER"
  else
    log "[3/12] 创建系统用户与组: $CASE_RUN_USER"
    useradd --system --user-group --no-create-home --shell /usr/sbin/nologin \
      --comment "CASE-Excel_merge web" "$CASE_RUN_USER" || die "useradd 失败"
  fi
}

# --- 4. 可选清理数据 ---
step_clean_data() {
  if [[ "$DEPLOY_CLEAN_DATA" != "1" ]]; then
    log "[4/12] 保留上传与导出目录"
    return 0
  fi
  log "[4/12] 警告: 清理 uploads / exports / audit_log.csv"
  rm -rf "$CASE_ROOT/hr_excel_web/uploads" "$CASE_ROOT/hr_excel_web/exports" 2>/dev/null || true
  mkdir -p "$CASE_ROOT/hr_excel_web/uploads" "$CASE_ROOT/hr_excel_web/exports"
  rm -f "$CASE_ROOT/hr_excel_web/audit_log.csv" 2>/dev/null || true
}

# --- 5. 目录权限：归运行用户所有 ---
step_chown_project() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    log "[5/12] 跳过 chown（调试模式）"
    return 0
  fi
  log "[5/12] 设置项目目录属主: $CASE_RUN_USER:$CASE_RUN_GROUP"
  mkdir -p "$CASE_ROOT/hr_excel_web/uploads" "$CASE_ROOT/hr_excel_web/exports"
  chown -R "$CASE_RUN_USER:$CASE_RUN_GROUP" "$CASE_ROOT"
  chmod u+rwX,go-rwx "$CASE_ROOT/hr_excel_web/uploads" "$CASE_ROOT/hr_excel_web/exports" 2>/dev/null || true
}

# --- 6～7. venv 与 pip ---
step_venv() {
  need_cmd python3
  if [[ "$DEPLOY_SKIP_SYSTEMD" != "1" ]]; then
    need_cmd sudo
  fi
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    if [[ "$DEPLOY_PURGE_VENV" == "1" ]]; then
      log "[6/12] 删除 venv（调试）"
      rm -rf "$CASE_ROOT/venv"
    fi
    if [[ ! -d "$CASE_ROOT/venv" ]]; then
      verify_python_can_create_venv
      log "[6/12] 创建 venv（root）"
      python3 -m venv "$CASE_ROOT/venv" || die "创建 venv 失败。Ubuntu/Debian 请先: apt update && apt install -y python3-venv（或 python3.12-venv 等与当前 python3 版本一致的包）"
    fi
    # shellcheck source=/dev/null
    source "$CASE_ROOT/venv/bin/activate"
    _check_offline_requirements_sha
    export PIP_DEFAULT_TIMEOUT="${DEPLOY_PIP_TIMEOUT}"
    if [[ -n "${DEPLOY_PIP_INDEX_URL}" ]]; then export PIP_INDEX_URL="${DEPLOY_PIP_INDEX_URL}"; else unset PIP_INDEX_URL; fi
    if _use_offline_wheels; then
      log "[7/12] pip 离线安装（offline_wheels/，--no-index）"
      python -m pip install --no-index --find-links="$CASE_ROOT/offline_wheels" -U pip setuptools wheel
      pip install --no-index --find-links="$CASE_ROOT/offline_wheels" --retries "${DEPLOY_PIP_RETRIES}" --timeout "${DEPLOY_PIP_TIMEOUT}" -r "$CASE_ROOT/requirements.txt" \
        || die "离线 pip 失败：wheel 缺失或平台/Python 与生成环境不一致。请重新执行 scripts/download_offline_wheels.sh（须在 Ubuntu 等 Linux 上）或设 DEPLOY_FORCE_ONLINE_PIP=1"
    else
      log "[7/12] pip 在线安装依赖（root 调试环境）"
      python -m pip install -U pip
      pip install --retries "${DEPLOY_PIP_RETRIES}" --timeout "${DEPLOY_PIP_TIMEOUT}" -r "$CASE_ROOT/requirements.txt" \
        || die "pip install 失败。可 export DEPLOY_PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple 后重试"
    fi
    return 0
  fi

  if [[ "$DEPLOY_PURGE_VENV" == "1" ]]; then
    log "[6/12] 删除旧 venv（DEPLOY_PURGE_VENV=1）"
    rm -rf "$CASE_ROOT/venv"
  fi
  if [[ ! -d "$CASE_ROOT/venv" ]]; then
    verify_python_can_create_venv
    log "[6/12] 以 $CASE_RUN_USER 创建 venv"
    sudo -u "$CASE_RUN_USER" env HOME="$CASE_ROOT" bash -lc "cd '$CASE_ROOT' && python3 -m venv venv" \
      || die "创建 venv 失败。Ubuntu/Debian 请先: apt update && apt install -y python3-venv（或 python3.12-venv 等）；再执行 rm -rf ${CASE_ROOT}/venv 后重跑本脚本"
  else
    log "[6/12] 已存在 venv，更新依赖"
  fi
  local offline_mode=0
  _check_offline_requirements_sha
  if _use_offline_wheels; then
    offline_mode=1
    log "[7/12] 以 $CASE_RUN_USER 执行 pip 离线安装（offline_wheels/）"
  else
    log "[7/12] 以 $CASE_RUN_USER 执行 pip 在线安装（retries=${DEPLOY_PIP_RETRIES} timeout=${DEPLOY_PIP_TIMEOUT}s）"
  fi
  sudo -u "$CASE_RUN_USER" env HOME="$CASE_ROOT" OFFLINE_MODE="${offline_mode}" PIP_DEFAULT_TIMEOUT="${DEPLOY_PIP_TIMEOUT}" PIP_INDEX_URL="${DEPLOY_PIP_INDEX_URL}" \
    bash -lc "
    set -e
    cd '$CASE_ROOT'
    source venv/bin/activate
    export PIP_DEFAULT_TIMEOUT=\"\${PIP_DEFAULT_TIMEOUT}\"
    if [[ -n \"\${PIP_INDEX_URL}\" ]]; then export PIP_INDEX_URL=\"\${PIP_INDEX_URL}\"; else unset PIP_INDEX_URL; fi
    if [[ \"\${OFFLINE_MODE}\" == \"1\" ]]; then
      python -m pip install --no-index --find-links='$CASE_ROOT/offline_wheels' -U pip setuptools wheel
      pip install --no-index --find-links='$CASE_ROOT/offline_wheels' --retries ${DEPLOY_PIP_RETRIES} --timeout ${DEPLOY_PIP_TIMEOUT} -r requirements.txt
    else
      python -m pip install -U pip
      pip install --retries ${DEPLOY_PIP_RETRIES} --timeout ${DEPLOY_PIP_TIMEOUT} -r requirements.txt
    fi
  " || die "pip install 失败。离线失败时请检查 offline_wheels 与 Python 平台；在线失败可设 DEPLOY_PIP_INDEX_URL 或 DEPLOY_FORCE_ONLINE_PIP=1"
}

# --- 8. 环境文件（systemd 以 root 读取后注入进程，文件可 600）---
step_env_file() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    log "[8/12] 跳过 $ENV_FILE"
    return 0
  fi
  # 说明：
  # - systemd 运行时会把 ENV_FILE 中的变量注入进 Flask 进程。
  # - 为了让“默认规则：密码=账号名”生效，当 DEPLOY_GENERATE_LOGIN_PASSWORDS=0 时，
  #   需要移除旧的 HR_WEB_PASSWORD_* 行，避免继续覆盖内置默认口令逻辑。
  log "[8/12] 写入 $ENV_FILE（合并 HR_WEB_HOST/PORT/DEBUG；保留 HR_WEB_SECRET_KEY；按 DEPLOY_GENERATE_LOGIN_PASSWORDS=${DEPLOY_GENERATE_LOGIN_PASSWORDS} 决定是否移除 HR_WEB_PASSWORD_*）"
  umask 077
  tmpf="$(mktemp)"
  if [[ -f "$ENV_FILE" ]]; then
    if [[ "${DEPLOY_GENERATE_LOGIN_PASSWORDS}" != "1" ]]; then
      # 关闭自动口令生成：删除旧 HR_WEB_PASSWORD_*，确保回到内置“密码=账号名”规则
      # 兼容：
      # - export HR_WEB_PASSWORD_XXX=...
      # - 行首有空格的写法
      # - Windows CRLF：去掉行尾 \r，避免正则匹配边界问题
      sed -e 's/\r$//' "$ENV_FILE" \
        | sed -E '/^[[:space:]]*(export[[:space:]]+)?HR_WEB_(HOST|PORT|DEBUG)[[:space:]]*=/d;
                 /^[[:space:]]*(export[[:space:]]+)?HR_WEB_PASSWORD_[_A-Za-z0-9]+[[:space:]]*=/d;
                 /^[[:space:]]*CASE_EXCEL_PROJECT_ROOT[[:space:]]*=/d;
                 /^[[:space:]]*CASE_CLEANUP_RETENTION_DAYS[[:space:]]*=/d' \
        | grep -v '^# 由 scripts/deploy_ecs.sh' >"$tmpf" || true
    else
      # 开启自动口令生成：保留现有 HR_WEB_PASSWORD_*，交由 seed_secrets_to_env_file 进行首次写入（存在则跳过）
      # 仍需要移除旧的 HOST/PORT/DEBUG 与 CASE_* 行，避免残留配置干扰
      sed -e 's/\r$//' "$ENV_FILE" \
        | sed -E '/^[[:space:]]*(export[[:space:]]+)?HR_WEB_(HOST|PORT|DEBUG)[[:space:]]*=/d;
                 /^[[:space:]]*CASE_EXCEL_PROJECT_ROOT[[:space:]]*=/d;
                 /^[[:space:]]*CASE_CLEANUP_RETENTION_DAYS[[:space:]]*=/d' \
        | grep -v '^# 由 scripts/deploy_ecs.sh' >"$tmpf" || true
    fi
  else
    : >"$tmpf"
  fi
  {
    echo "# 由 scripts/deploy_ecs.sh 维护以下三行；密钥建议用 HR_WEB_SECRET_KEY="
    echo "HR_WEB_HOST=${HR_WEB_HOST}"
    echo "HR_WEB_PORT=${HR_WEB_PORT}"
    echo "HR_WEB_DEBUG=${HR_WEB_DEBUG}"
    echo "# 由 scripts/deploy_ecs.sh 维护以下二行（Web 上传/导出按天回收，见 systemd timer case-excel-web-cleanup）"
    echo "CASE_EXCEL_PROJECT_ROOT=${CASE_ROOT}"
    echo "CASE_CLEANUP_RETENTION_DAYS=${CASE_CLEANUP_RETENTION_DAYS}"
  } >>"$tmpf"
  install -m 600 -o root -g root "$tmpf" "$ENV_FILE"
  rm -f "$tmpf"
  if [[ "${DEPLOY_GENERATE_LOGIN_PASSWORDS}" != "1" ]]; then
    if grep -qE '^[[:space:]]*(export[[:space:]]+)?HR_WEB_PASSWORD_' "$ENV_FILE" 2>/dev/null; then
      log "[8/12] 警告: 清理 HR_WEB_PASSWORD_* 后仍检测到口令变量仍存在，当前文件: $ENV_FILE"
    else
      log "[8/12] 已清理 HR_WEB_PASSWORD_*（账号=密码规则应可生效）"
    fi
  fi
  seed_secrets_to_env_file
}

# --- 9. systemd 单元（User= 非 root）---
step_systemd_unit() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    log "[9/12] 跳过 systemd"
    return 0
  fi
  log "[9/12] 安装 systemd 单元（User=$CASE_RUN_USER）"
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

# --- 10. Web 上传/导出按天回收（systemd timer；不用 logrotate：后者面向日志轮转）---
CLEANUP_SERVICE_NAME="case-excel-web-cleanup"
step_cleanup_timer() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    log "[10/12] 跳过清理定时器（DEPLOY_SKIP_SYSTEMD=1）"
    return 0
  fi
  if [[ "${CASE_CLEANUP_TIMER_ENABLE}" != "1" ]]; then
    log "[10/12] 跳过清理定时器（CASE_CLEANUP_TIMER_ENABLE=0）"
    return 0
  fi
  if [[ ! -f "${CASE_ROOT}/scripts/cleanup_web_temp.sh" ]]; then
    log "[10/12] 警告: 未找到 ${CASE_ROOT}/scripts/cleanup_web_temp.sh，跳过定时清理"
    return 0
  fi
  chmod 755 "${CASE_ROOT}/scripts/cleanup_web_temp.sh"
  log "[10/12] 安装 ${CLEANUP_SERVICE_NAME}.timer（保留 ${CASE_CLEANUP_RETENTION_DAYS} 天内有改动的文件）"
  cat <<EOF >"/tmp/${CLEANUP_SERVICE_NAME}.service"
[Unit]
Description=CASE-Excel_merge Web uploads/exports retention cleanup
After=network.target

[Service]
Type=oneshot
User=${CASE_RUN_USER}
Group=${CASE_RUN_GROUP}
EnvironmentFile=-${ENV_FILE}
ExecStart=${CASE_ROOT}/scripts/cleanup_web_temp.sh
EOF
  cat <<EOF >"/tmp/${CLEANUP_SERVICE_NAME}.timer"
[Unit]
Description=Daily timer for CASE-Excel_merge upload/export cleanup

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=60m
Persistent=true

[Install]
WantedBy=timers.target
EOF
  install -m 644 "/tmp/${CLEANUP_SERVICE_NAME}.service" "/etc/systemd/system/${CLEANUP_SERVICE_NAME}.service"
  install -m 644 "/tmp/${CLEANUP_SERVICE_NAME}.timer" "/etc/systemd/system/${CLEANUP_SERVICE_NAME}.timer"
  rm -f "/tmp/${CLEANUP_SERVICE_NAME}.service" "/tmp/${CLEANUP_SERVICE_NAME}.timer"
  systemctl daemon-reload
  systemctl enable "${CLEANUP_SERVICE_NAME}.timer"
  systemctl start "${CLEANUP_SERVICE_NAME}.timer" 2>/dev/null || true
  log "[10/12] 已启用 timer；查看: systemctl list-timers ${CLEANUP_SERVICE_NAME}.timer；日志: journalctl -u ${CLEANUP_SERVICE_NAME}.service"
}

# --- 11. 启动并确认 systemd 为 active ---
step_start() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    log "[11/12] 跳过 systemctl start"
    return 0
  fi
  log "[11/12] 启动服务: ${SERVICE_NAME}"
  systemctl start "${SERVICE_NAME}"
  local i=0
  while [[ $i -lt 45 ]]; do
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
      log "[11/12] 服务已处于 active（等待 ${i}s）"
      break
    fi
    sleep 1
    i=$((i + 1))
  done
  systemctl is-active --quiet "${SERVICE_NAME}" || die "服务 ${SERVICE_NAME} 未进入 active，请查看: journalctl -u ${SERVICE_NAME} -n 80 --no-pager"
  systemctl --no-pager -l status "${SERVICE_NAME}" || true
}

# --- 12. 健康检查（失败则 exit 非零，部署不算成功）---
# systemd 标 active 后 Flask 可能仍在加载依赖（如 pandas），端口尚未监听；需轮询而非单次 curl。
step_health() {
  if [[ "$DEPLOY_SKIP_SYSTEMD" == "1" ]]; then
    log "[12/12] 跳过 HTTP 健康检查（DEPLOY_SKIP_SYSTEMD=1）"
    return 0
  fi
  local url="http://127.0.0.1:${HR_WEB_PORT}/"
  log "[12/12] 健康检查: $url（冷启动可能需数十秒，将重试直至就绪）"
  need_cmd curl
  local code="000" attempt=0 max_attempts=45
  while [[ $attempt -lt $max_attempts ]]; do
    code="$(curl -sS --connect-timeout 3 -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
    if [[ "$code" == "200" ]] || [[ "$code" == "302" ]] || [[ "$code" == "301" ]]; then
      log "健康检查通过 (HTTP $code，第 $((attempt + 1)) 次尝试)"
      return 0
    fi
    if [[ $attempt -eq 0 ]]; then
      log "[12/12] 应用尚未响应 HTTP ${code:-?}，等待进程完成启动（最多约 $((max_attempts * 2))s）…"
    fi
    sleep 2
    attempt=$((attempt + 1))
  done
  die "健康检查失败: 最后 HTTP ${code:-000}（期望 200/301/302）；排查: journalctl -u ${SERVICE_NAME} -n 80 --no-pager"
}

if [[ "$DEPLOY_SKIP_SYSTEMD" != "1" ]] && [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  die "生产部署需 root：sudo bash $0 ；仅调试可加 DEPLOY_SKIP_SYSTEMD=1"
fi

step_env_check
step_stop
step_create_user
step_clean_data
step_chown_project
step_venv
step_env_file
step_systemd_unit
step_cleanup_timer
step_start
step_health

trap - ERR
echo ""
log "======== 部署成功 ========"
log "完整日志已保存: $DEPLOY_LOG_FILE"
if [[ "$DEPLOY_SKIP_SYSTEMD" != "1" ]]; then
  log "进程以系统用户 $CASE_RUN_USER 运行（非 root）"
  log "查看服务: systemctl status ${SERVICE_NAME} | journalctl -u ${SERVICE_NAME} -f"
  log "登录 Web：默认初始密码与账号名相同（如 hr_admin / hr_admin），首次登录后须网页改密；若已配置 HR_WEB_PASSWORD_* 则以 env 为准"
  log "  随机口令（仅 DEPLOY_GENERATE_LOGIN_PASSWORDS=1）见: grep '^HR_WEB_PASSWORD_' $ENV_FILE 或 /root/.case-excel-web.initial"
fi
echo ""
