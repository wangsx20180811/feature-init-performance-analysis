# CASE-Excel_merge

员工绩效与基本信息表的 **Excel 合并、预览、TopN 与扩展分析** 工具集，并提供基于浏览器的 **HR 网页端**（登录后上传表格，通过表单或提示词驱动分析，可下载合并/分析结果）。

## 目录

- [项目简介](#项目简介)
- [目录结构（概要）](#目录结构概要)
- [环境要求](#环境要求)
- [一键部署与启动（对照脚本）](#一键部署与启动对照脚本)
- [发布包与内网 Linux 上线](#发布包与内网-linux-上线)
- [员工 Web 界面使用说明](#员工-web-界面使用说明)
- [命令行 main.py 与参数（IT / 脚本）](#命令行-mainpy-与参数it--脚本)
- [停止 Web 服务](#停止-web-服务)
- [许可证与声明](#许可证与声明)

> 说明：锚点以 GitHub / Gitea 等常见渲染为准；若本地预览无法跳转，可直接按标题向下浏览。

---

## 项目简介

- **Web 应用**（`hr_excel_web/`）：Flask 服务，支持表一（员工基本信息）、多文件绩效数据、可选 `hr_config.json` 列映射；表单操作与简单提示词两种交互方式。
- **核心实现**（`tools/`）：表读取与筛选、绩效多文件/多 Sheet 合并、左右表合并、全年四季 TopN、扩展统计与报表导出等，可被 Web 或命令行脚本调用。

## 目录结构（概要）

| 路径 | 说明 |
|------|------|
| `main.py` | 统一入口：无参或 `web` 启动 Web；`merge` / `topn` / `ext` / `read` 调用 `tools/` 模块 |
| `requirements.txt` | Python 依赖（pandas、openpyxl、flask 等，版本已锁定） |
| `deploy.bat` / `deploy.sh` | 一键创建虚拟环境并安装依赖（Windows / Linux·macOS） |
| `run_hr_web.bat` / `run_hr_web.sh` | 一键启动服务并尝试打开浏览器 |
| `tools/` | 功能实现脚本（合并、读取、绩效加载、TopN、扩展分析、列映射等） |
| `hr_excel_web/` | Web 应用（`app.py`、模板、`uploads/`、`exports/`） |
| `hr_config.example.json` | HR 列映射与等级占比等配置示例（可选上传） |
| `package_release.sh` | 生成发布用 `tar.gz`（排除 venv、上传目录等） |
| `scripts/deploy_ecs.sh` | **ECS / 单机 Linux 生产向**：停服务、venv、依赖、写环境文件、systemd、健康检查（可重复执行） |
| `Dockerfile` / `.dockerignore` | 可选：容器化部署 |
| `scripts/hr-excel-web.service.example` | 可选：systemd 手写示例（推荐优先用 `deploy_ecs.sh` 生成单元） |

## 环境要求

| 项 | 说明 |
|----|------|
| Python | **3.10～3.12** 均可（`requirements.txt` 中 wheel 与官方镜像以 **3.12** 为参考；低于 3.10 未做兼容性保证） |
| 架构 | **64 位** 推荐（pandas 等二进制轮与内存占用） |
| 系统 | **Windows 10/11**；**Linux**（glibc 系发行版，见下）；macOS 可与 `deploy.sh` 共用流程 |

以下说明与仓库内 **`deploy.bat`**、**`deploy.sh`**、**`hr_excel_web/app.py`**（环境变量）一致；若行为与文档不符，以代码为准。

## 一键部署与启动（对照脚本）

### 环境变量一览（Web 服务）

由 **`hr_excel_web/app.py`** 在直接运行 `main.py` / `app.py` 时读取（**`main.py merge` 等子命令不会设置下列变量**，仅影响 Web）：

| 变量 | 默认值 | 含义 |
|------|--------|------|
| `HR_WEB_HOST` | `127.0.0.1` | 监听地址。本机浏览器访问保持默认即可；**内网其它机器访问**请设为 **`0.0.0.0`**（或具体网卡 IP）。 |
| `HR_WEB_PORT` | `5001` | 监听端口。 |
| `HR_WEB_DEBUG` | `1` | 为 `1` / `true` / `yes` / `on` 时开启 **Flask debug**；**生产环境请设为 `0` 或 `false`**。 |
| `HR_WEB_SECRET_KEY` | （未设置则用内置演示密钥） | **生产务必设置**长随机字符串，用于会话签名；可写在 **`/etc/default/case-excel-web`**（`deploy_ecs.sh` 会保留该行）。 |

说明：`main.py web --port 5002` 会向子进程写入 **`HR_WEB_PORT`**（见 `main.py` 中 `_run_web`）；**`HR_WEB_HOST`** 无 CLI 参数，仅能通过环境变量设置。

### Windows 一键部署

**前置：** 从 [python.org](https://www.python.org/downloads/) 安装 **64 位 Python 3.10+**，安装时勾选 **「Add Python to PATH」**。不建议使用 Microsoft Store 版 `python`（路径与权限易与脚本不一致）；若已安装多版本，可在命令行用 `where python` 确认 `deploy.bat` 调用的解释器。

**步骤：**

1. 将项目解压到**非系统保护目录**（路径避免过长；**中文路径多数情况可用**，若遇个别工具报错可换英文路径）。
2. 双击或在 **cmd** 中执行项目根目录 **`deploy.bat`**（脚本内已 **`chcp 65001`**，便于控制台显示中文）。
3. 脚本行为（与代码一致）：若不存在 **`venv`** 则执行 **`python -m venv venv`**；再 **`activate`** 后 **`pip install -U pip`** 与 **`pip install -r requirements.txt`**（版本见 `requirements.txt`）。
4. 若提示找不到 `python`，请检查 PATH，或使用 **`py -3 -m venv venv`** 手动建环境后再执行 `pip install -r requirements.txt`。

**启动 Web（推荐）：** 双击 **`run_hr_web.bat`**（或 **`一键打开HR网页.bat`**）。脚本会**优先使用** **`venv\Scripts\python.exe main.py`**（若已部署）；否则回退到 **`python main.py`**。启动前可设置 **`set HR_WEB_PORT=5002`** 再运行 bat 以换端口。

**命令行启动：** 在项目根目录执行 `venv\Scripts\activate` 后 `python main.py`，或 `venv\Scripts\python.exe main.py`（无需 activate）。

### Linux / 服务器一键部署（多发行版）

**共同前提：** 系统需有 **`python3`**（≥3.10），且能创建 venv。脚本 **`deploy.sh`** 使用：`python3 -m venv venv` → `source venv/bin/activate` → `pip install -r requirements.txt`。

**典型发行版补充（仅当 `python3 -m venv` 报错时再装）：**

| 发行系 | 示例命令（需 root） |
|--------|---------------------|
| Debian / Ubuntu | `sudo apt update && sudo apt install -y python3 python3-venv python3-pip` |
| RHEL / Rocky / AlmaLinux 8+ | `sudo dnf install -y python3 python3-pip`；若缺 venv 模块：`sudo dnf install -y python3-devel` 或 `python3.11` 等具体版本包（以仓库为准） |
| openSUSE Leap / SUSE | `sudo zypper install python3 python3-pip` |
| Amazon Linux 2023 | `sudo dnf install -y python3 python3-pip` |

**glibc / musl：** 预编译 wheel（pandas 等）面向 **manylinux（glibc）**。**Alpine（musl）** 上可能需额外依赖或源码构建；**推荐**使用本仓库 **`Dockerfile`**（基于 `python:3.12-slim-bookworm`，Debian/glibc）以降低差异。

**步骤：**

```bash
cd /path/to/CASE-Excel_merge
chmod +x deploy.sh run_hr_web.sh package_release.sh scripts/deploy_ecs.sh scripts/cleanup_web_temp.sh   # 首次从压缩包解压时建议执行
./deploy.sh
source venv/bin/activate
```

**内网多机访问：** 默认仅监听 **127.0.0.1**，需在其他机器浏览器访问时：

```bash
export HR_WEB_HOST=0.0.0.0
export HR_WEB_PORT=5001
export HR_WEB_DEBUG=0
python main.py
```

**防火墙（示例，按实际发行版选择）：**

- **firewalld**：`sudo firewall-cmd --permanent --add-port=5001/tcp && sudo firewall-cmd --reload`
- **ufw（Ubuntu 常见）**：`sudo ufw allow 5001/tcp && sudo ufw reload`

**SELinux（RHEL 系）：** 若绑定非标准策略端口仍无法访问，需按单位规范设置端口标签或反向代理，此处不展开；优先用 **Nginx 反向代理** 暴露 80/443。

### 启动 Web 的几种方式（小结）

| 方式 | 说明 |
|------|------|
| **Windows** `run_hr_web.bat` | 优先 **`venv\Scripts\python.exe`**；环境变量 **`HR_WEB_PORT`** 可换端口。 |
| **Linux / macOS** `run_hr_web.sh` | 若存在 `venv` 则自动 `activate`；**`HR_WEB_PORT`** 可换端口；会尝试 `xdg-open` / `open` 打开浏览器。 |
| **`python main.py`** | 无参即启动 Web（等价旧版直接跑 `app.py`）。 |
| **`python main.py web --port 5002`** | 设置端口并启动 Web（写入 **`HR_WEB_PORT`**）。 |

访问：**http://127.0.0.1:5001/**（或所设端口）。若 **`HR_WEB_HOST=0.0.0.0`**，请用 **`http://<服务器内网IP>:端口/`** 访问。

---

## 发布包与内网 Linux 上线

### 1. 打包（开发机或 CI）

在**项目根目录**执行（需 **bash**：Linux / macOS / **Git Bash**）：

```bash
chmod +x package_release.sh
./package_release.sh
```

会在**项目上一级目录**生成 **`CASE-Excel_merge_release_时间戳.tar.gz`**，已排除 `venv`、`.git`、上传与导出目录、审计日志等（见 **`package_release.sh`**）。**勿**将压缩包输出路径放在被打包的目录内，以免 tar 自包含。

**单机部署（主线，非 Docker 镜像）：** 将 **`tar.gz`** 解压到目标机（如 **阿里云 ECS**，**Ubuntu + systemd**），执行 **`sudo bash scripts/deploy_ecs.sh`** 即可完成：**运行用户**、**venv**、**`pip install -r requirements.txt`**（在线 PyPI，带重试/可选镜像）、**`/etc/default/case-excel-web`** 合并、**首次会话密钥与随机登录密码（可选自动生成）**、**systemd** 单元、**Web 临时文件按天回收（systemd timer）**、**启动与健康检查**。同一套流程可换到其它 **Linux 单机**环境，**不依赖**本项目的 Docker 镜像。

**Web 临时文件回收：** 部署脚本会安装 **`case-excel-web-cleanup.timer`**（每日约 03:30，随机延迟最多 1 小时），执行 **`scripts/cleanup_web_temp.sh`**，按 **`CASE_CLEANUP_RETENTION_DAYS`**（默认 **7**）删除 **`hr_excel_web/uploads/`**、**`exports/`** 下「最后修改时间」早于保留天数的文件。**不**使用 logrotate（该工具用于日志轮转，不适合按目录与天龄删用户上传文件）。**不**自动删 **`audit_log.csv`**。

**可选增强：** 若需在无公网 PyPI 的环境加速/离线安装 Python 包，可使用项目内 **`offline_wheels/`** 与 **`scripts/download_offline_wheels*.sh`**（详见 **`offline_wheels/README.txt`**）；**无离线目录时按在线安装即可**，不必作为部署前提。

**打包与上线前自检（建议）：**

1. 本地执行 `python -m py_compile main.py`、`python -m py_compile hr_excel_web/app.py`（或通过 IDE）确认无语法错误；可选运行 `python main.py` 做冒烟。
2. **生产**在目标机或 **`/etc/default/case-excel-web`** 中设置 **`HR_WEB_SECRET_KEY`**（长随机字符串），勿使用默认演示密钥。
3. 解压上传后执行 **`chmod +x package_release.sh deploy.sh run_hr_web.sh scripts/deploy_ecs.sh scripts/cleanup_web_temp.sh`**（若从压缩包解压）。
4. ECS 使用 **`sudo bash scripts/deploy_ecs.sh`**，确认 **`systemctl status case-excel-web`** 为 **active**，必要时 **`journalctl -u case-excel-web -n 30`**。

### 2. 服务器解压与部署

解压后顶层目录名应与打包时的项目文件夹名一致（默认 **`CASE-Excel_merge`**）。

```bash
tar -xzf CASE-Excel_merge_release_xxxx.tar.gz
cd CASE-Excel_merge
chmod +x package_release.sh deploy.sh run_hr_web.sh scripts/deploy_ecs.sh scripts/cleanup_web_temp.sh
```

- **临时运行（开发调试用）：** `./deploy.sh`，再 `export HR_WEB_HOST=0.0.0.0 HR_WEB_DEBUG=0` 后 `python main.py`。  
- **ECS / 生产（推荐）：** 使用 **`scripts/deploy_ecs.sh`**（见下一节），可重复执行并注册 **systemd**。

### 3. ECS 一键部署（`scripts/deploy_ecs.sh`）

适用于 **Ubuntu 等带 systemd 的服务器**。部署脚本需 **以 root 执行**（`sudo bash scripts/deploy_ecs.sh`），用于：安装 systemd、写 `/etc/default/`、**创建系统用户**、**chown 项目目录**。

**Web 进程不以 root 运行**：默认创建系统用户 **`caseexcel`**（与 `CASE_RUN_USER` 一致），**venv 与 pip 以该用户执行**，**systemd 中 `User=` / `Group=`** 为该用户；`WorkingDirectory` 为项目根目录。

脚本步骤概要：**停止旧服务** → **创建用户（若不存在）** → 可选清理数据 → **`chown -R` 项目** → **venv + pip（sudo -u caseexcel）** → 合并写入 **`/etc/default/case-excel-web`**（`600`）→ 安装 **systemd**（含 `PrivateTmp` / `NoNewPrivileges`）→ **start** → **curl**。

**首次部署前（Ubuntu / Debian 最小化镜像）：** 建议执行 `apt update && apt install -y python3-venv`（或 `python3.12-venv` 等与当前 `python3` 主版本一致），`sudo` 与 `curl`（健康检查可选）亦需已安装；否则创建 venv 或检查 HTTP 会失败。

```bash
cd /path/to/CASE-Excel_merge   # 解压后的项目根
sudo bash scripts/deploy_ecs.sh
```

常用环境变量（可在命令前 `export`，与 `hr_excel_web/app.py` 一致）：

| 变量 | 默认（脚本内） | 说明 |
|------|----------------|------|
| `HR_WEB_HOST` | `0.0.0.0` | 内网访问需监听全网卡 |
| `HR_WEB_PORT` | `5001` | 端口 |
| `HR_WEB_DEBUG` | `0` | 生产建议保持 `0` |
| `CASE_ROOT` | 脚本推断的项目根 | 解压目录不在当前路径时设为绝对路径 |
| `CASE_RUN_USER` | `caseexcel` | 运行 Web 的系统用户；不存在则 **useradd** 创建 |
| `CASE_RUN_GROUP` | 与 `CASE_RUN_USER` 同名 | 一般勿改；与 `useradd --user-group` 一致 |
| `DEPLOY_PURGE_VENV` | `0` | `1` 时删除 **`venv` 后重建** |
| `DEPLOY_CLEAN_DATA` | `0` | `1` 时清空 **uploads / exports / audit_log**（**危险**） |
| `DEPLOY_SKIP_SYSTEMD` | `0` | `1` 为**调试**：不建用户、venv 用 root、不写 systemd（**勿用于生产**） |
| `DEPLOY_SEED_SECRETS` | `1` | `0` 时不在 `/etc/default/case-excel-web` 中自动生成 **`HR_WEB_SECRET_KEY`** / 随机登录密码 |
| `DEPLOY_GENERATE_LOGIN_PASSWORDS` | `1` | 在 `DEPLOY_SEED_SECRETS=1` 且 env 中尚无 **`HR_WEB_PASSWORD_*`** 时生成随机密码并写入 env；凭据副本 **`/root/.case-excel-web.initial`**（600） |
| `DEPLOY_PIP_RETRIES` | `5` | `pip install` 重试次数（缓解网络抖动） |
| `DEPLOY_PIP_TIMEOUT` | `120` | `pip` 单次超时（秒） |
| `DEPLOY_PIP_INDEX_URL` | （空） | 国内 ECS 可设为 `https://pypi.tuna.tsinghua.edu.cn/simple` 等镜像，再执行部署脚本 |
| `DEPLOY_FORCE_ONLINE_PIP` | `0` | 仅当使用可选 **`offline_wheels/`** 时：设为 `1` 强制在线 `pip` |
| `CASE_CLEANUP_RETENTION_DAYS` | `7` | **`uploads/`、`exports/`** 内文件「未修改」超过该天数则由定时任务删除（写入 `/etc/default/case-excel-web`） |
| `CASE_CLEANUP_TIMER_ENABLE` | `1` | `0` 时不安装 **`case-excel-web-cleanup.timer`** |

应用侧（**`/etc/default/case-excel-web`** 或环境变量）：**`HR_WEB_SECRET_KEY`** 会话密钥；**`HR_WEB_PASSWORD_HR_ADMIN`**、**`HR_WEB_PASSWORD_HR_USER`**、**`HR_WEB_PASSWORD_IT_ADMIN`**、**`HR_WEB_PASSWORD_VIEWER`** 覆盖内置默认密码（见 `hr_excel_web/app.py`）。

升级新版本：**覆盖或解压到新目录后**，再次执行同一脚本即可（会先 **stop**，再 **chown**、装依赖、**start**）。默认 **保留** 用户上传与导出目录。

查看服务：`systemctl status case-excel-web`；日志：`journalctl -u case-excel-web -f`。若启用了 **SELinux**，需按单位策略为项目目录或端口设置上下文（此处不展开）。

**说明**：`deploy_ecs.sh` 仍需要 **root** 来执行系统级操作；**仅 Flask 进程**在运行时为 **非 root**。

### 4. Docker（可选）

镜像内已设 **`HR_WEB_HOST=0.0.0.0`**、**`HR_WEB_DEBUG=0`**（见 **`Dockerfile`**）。构建与运行示例：

```bash
docker build -t case-excel-merge:latest .
docker run -d -p 5001:5001 \
  -v "$(pwd)/hr_excel_web/uploads:/app/hr_excel_web/uploads" \
  -v "$(pwd)/hr_excel_web/exports:/app/hr_excel_web/exports" \
  case-excel-merge:latest
```

持久化上传与导出时务必挂载卷；生产环境请配合 **HTTPS 与身份认证**。

### 5. systemd（手写示例，可选）

若未使用 **`deploy_ecs.sh`**，可参考 **`scripts/hr-excel-web.service.example`** 自行修改 **`WorkingDirectory`**、**`ExecStart`** 等；推荐单元以 **`deploy_ecs.sh`** 生成为准（含 **`EnvironmentFile`**）。

生产环境请务必：**通过环境变量 `HR_WEB_SECRET_KEY` 设置会话密钥**（或等价配置）、**替换内置账号**、**关闭 debug**、**置于反向代理之后**。

---

## 员工 Web 界面使用说明

### 1. 登录与账号

内置账号与密码定义在 `hr_excel_web/app.py` 的 `USER_STORE`（**生产环境务必改为企业统一认证或数据库**）：

| 用户名 | 说明（注释） | 密码（演示） |
|--------|--------------|--------------|
| `hr_admin` | HR 管理员 | `HrPerf@2026` |
| `hr_user` | HR 业务用户 | `HrUser@2026` |
| `it_admin` | IT 管理员 | `ItOps@2026` |
| `viewer` | 只读浏览（当前与其它账号功能相同，便于后续扩展权限） | `ViewOnly@2026` |

登录成功后会进入工作台；**退出登录**会清空当前会话中的文件路径记录。

### 2. 上传与数据留存（注意事项）

- **表一（主表）**：`file_a`，支持 `.xlsx` / `.xls` / `.csv` / `.tsv`。
- **绩效表**：`perf_files`，可多选；兼容旧字段名 **`file_b`**（单文件绩效）。
- **HR 配置（可选）**：`hr_config`，JSON，列映射与等级占比等参见根目录 **`hr_config.example.json`**。
- **每次提交**：若本次选择了新文件，会先保存到 `hr_excel_web/uploads/<用户名>/`，文件名格式为 `时间戳_原始文件名`；同一「主文件名」（时间戳后的原名）**只保留最新一份**，旧文件会自动删除，避免占满磁盘。
- **会话**：表一、绩效列表、配置路径保存在服务端会话中；**不重新上传**时沿用上次已保存的路径。

### 3. 表单「选择功能」预设（推荐，与后端一一对应）

在「表单操作」中选功能并填参，点击 **「执行所选功能」**。下列为代码中的 `operation` 值及数据要求（与页面悬停说明一致）。

#### 3.1 基础功能

| 预设功能 | 需要的数据 | 主要参数 |
|----------|------------|----------|
| 预览表一前若干行 | 仅表一 | 预览行数 1～500 |
| 预览表二前若干行 | 至少一份绩效 | 预览行数 1～500（联合预览） |
| 合并表一与表二（导出 Excel） | 表一 + 绩效 | 连接列名（默认 `员工ID`）、合并方式（left/inner/outer/right）、是否右表按连接键去重 |
| 按员工 ID 同时查两张表 | 表一 + 绩效 | 员工 ID 列表（逗号分隔）、ID 列名（默认 `员工ID`） |
| 按入职日期筛选表一 | 仅表一 | 日期列名（默认 `入职日期`）、早于/晚于（至少填一项，格式建议 `YYYY-MM-DD`） |
| 2024 四季均值 TopN（表一+表二） | 表一 + 绩效 | Top N（1～500）；**年度在表单中固定为 2024**（与 `topn_annual_2024` 实现一致） |

#### 3.2 扩展分析（需表一 + 绩效；可选 HR 配置）

展开「扩展分析」类选项后，通常可填：**分析主年度**、**对比年度（可选）**、**Top N / 对比条数**（依功能使用）。`operation` 取值如下（与命令行 `main.py ext --op` 一致）：

| operation | 说明（页面文案摘要） |
|-----------|----------------------|
| `ext_desc_dept` | 按部门描述统计（均值/标准差等） |
| `ext_missing` | 指定年度缺评名单 |
| `ext_outliers` | 绩效离群检测（IQR） |
| `ext_grade` | 等级分布与占比预警 |
| `ext_consistency` | 数据一致性检查 |
| `ext_yoy` | 两年绩效对比（升降榜） |
| `ext_dept_top` | 各部门内 TopN |
| `ext_rater` | 按评分人汇总（宽松度粗看） |
| `ext_goal` | 目标达成率（需目标/完成列） |
| `ext_calib` | 校准前后对比（需对应列） |
| `ext_full_report` | 汇总报表（多 Sheet Excel） |
| `ext_platform_notes` | 平台类能力说明（定时/SSO/大模型等，以说明为主） |

扩展分析会按是否生成多 Sheet 结果，在页面提供 **Excel 下载**；部分操作依赖表结构或 `hr_config.json` 中的列映射。

### 4. 提示词方式（「仅按提示词处理」）

在「提示词」文本框输入内容后提交。**必须先上传表一**；部分能力还需绩效数据。未命中任何规则时，页面会提示改用表单。

下列逻辑来自 `hr_excel_web/app.py` 中的 `_try_prompt_route`，**按代码判断顺序与条件**整理。

#### 4.1 预览表一前若干行

- **条件**：提示词中包含 **「预览」**，或 **同时包含「前」与「行」**。
- **行数**：可写 **「前 N 行」**（正则匹配），未写则默认 **5**，且不超过 **500**。
- **数据**：仅需 **表一**（不读取绩效文件做预览）。
- **示例**：`预览前10行`、`前20行`

#### 4.2 合并表一与绩效（导出 Excel）

- **条件**：已上传绩效；且提示词中含 **「合并」** 或英文 **merge**（不区分大小写）。
- **连接列**：默认 **`员工ID`**；若提示词中含 **`列：工号`**、`列:xxx` 等形式（`列` 后跟可选冒号与列名），则使用该列名作为连接列。
- **固定行为**：**左连接（left）**、**右表按连接键去重**，与表单中可调的合并方式不同。
- **示例**：`合并`、`merge`、`合并 列：工号`

#### 4.3 按员工 ID 同时查两张表

- **条件**：已上传绩效；提示词中含 **「员工」**；且文中出现 **至少一段连续 3 位及以上数字**（作为员工 ID 片段抽取，多段会以逗号拼接）。
- **固定行为**：ID 列名固定为 **`员工ID`**（不可在提示词中修改）。
- **示例**：`查员工 10001 和 10002`、`员工 1001`

#### 4.4 指定年度 · 四季均值 TopN（表一 + 绩效）

- **条件**：已上传绩效；且满足下列 **任一** 关键词组合：
  - 含 **「四季」**，或
  - 含 **「四个季度」**，或
  - 同时含 **「季度」与「均值」**，或
  - 同时含 **「全年」与「绩效」**。
- **TopN**：从 **`top5`**、`top 10` 等英文，或 **「前 10 名」** 等形式解析；未写则默认 **5**，范围 **1～500**。
- **年度**：从文中 **四位年份 `20xx`** 提取，未写则默认 **2024**。
- **示例**：`2024四季绩效top5`、`四个季度均值前10名`、`2023全年绩效排名`

### 5. Web 使用注意事项（汇总）

| 类别 | 说明 |
|------|------|
| 提示词 vs 表单 | 提示词为**固定规则**分流：合并方式、员工 ID 列名等与表单不完全一致；需要精细参数时请用 **表单操作**。 |
| 预览范围 | 提示词中的「预览」仅针对 **表一**；**预览绩效（表二）** 只能通过表单 **「预览表二前若干行」**。 |
| 表单 TopN 年度 | 表单中 **「2024 四季均值 TopN」** 对应后端年度 **固定为 2024**；若需其它年度，请用 **提示词**（含年份与四季相关关键词）或命令行 `main.py topn -y`。 |
| 上传与空间 | 同一名义文件多次上传，**仅保留最新时间戳文件**；导出结果在 **`hr_excel_web/exports/`**。 |
| 安全 | 默认 `secret_key` 与内置账号仅作演示；生产环境请更换密钥、关闭调试、接入正式认证。 |

---

## 命令行 main.py 与参数（IT / 脚本）

### 1. 适用场景与通用注意

- **统一入口**：在项目**根目录**执行（`main.py` 会切换工作目录并加载 `tools/`）。
- **建议**先 **`deploy.bat` / `deploy.sh`** 创建 **`venv`**，使用 **`venv\Scripts\python.exe main.py ...`**（Windows）或激活虚拟环境后再执行，避免污染系统 Python。
- **路径含空格或中文**：请用引号包裹，例如 `-l "D:\data\员工表.xlsx"`。
- **帮助**：`python main.py -h`；各子命令 `python main.py merge -h`、`python main.py read preview-head -h` 等。

### 2. 子命令一览（与 `tools/` 模块对应）

| 子命令 | 对应模块 | 作用 |
|--------|----------|------|
| （无参数）或 `web` | `hr_excel_web/app.py` | 启动 HR Web；可用 `web --port N` 或环境变量 `HR_WEB_PORT` |
| `merge` | `merge_excel_data.py` | 两表合并导出 xlsx |
| `topn` | `topN_annual_performance.py` | 指定年度四季均值 TopN |
| `ext` | `hr_analytics_extended.py` | 扩展分析，`--op` 与网页 `ext_*` 相同 |
| `read` | `read_excel_data.py` | 子命令：`preview-head`、`by-employee-id`、`by-hire-date` |

### 3. 使用示例

```bash
# 启动 Web
python main.py
python main.py web --port 5002

# 合并（短参数 -l -r -o；--on 连接列；--dedupe-right 右表去重）
python main.py merge -l 左表.xlsx -r 右表.xlsx -o 合并结果.xlsx --on 员工ID --dedupe-right

# TopN（-b 基本信息；-p 可多个绩效文件；-y 年度；-n TopN；-o 导出）
python main.py topn -b 员工基本信息表.xlsx -p 绩效A.xlsx 绩效B.xlsx -y 2024 -n 10 -o topn.xlsx

# 扩展分析（--op 同网页；-c 可选 hr_config.json；-O 导出 Excel，勿与 --op 混淆）
python main.py ext -b 员工基本信息表.xlsx -p 绩效.xlsx --op ext_grade -y 2024 -n 5 -c hr_config.json -O 扩展分析.xlsx

# 读取 / 筛选
python main.py read preview-head -f 员工基本信息表.xlsx -N 10
python main.py read by-employee-id -f 表一.xlsx 绩效.xlsx -e 1001,1002 --id-column 员工ID
python main.py read by-hire-date -f 员工基本信息表.xlsx --date-column 入职日期 --before 2022-01-01
```

### 4. 命令行注意事项（汇总）

| 类别 | 说明 |
|------|------|
| 与 Web 等价性 | `main.py` 通过设置 `sys.argv` 调用各模块的 `main()`，与 **`python tools/xxx.py` 全参数** 行为一致；此处提供的是**短参数别名**（如 `merge` 的 `-l/-r/-o`）。 |
| `ext` 导出 | 导出文件请使用 **`-O` / `--out`**，不要与 **`--op`**（分析类型）混淆。 |
| `read` | 必须带二级子命令，例如 **`read preview-head`**，详见 `python main.py read -h`。 |
| 直接调用 tools | 仍可执行 `python tools\read_excel_data.py ...`（参数为各脚本原生长选项）；需在项目根目录或正确配置 `PYTHONPATH`。 |
| 生产调度 | 计划任务、CI 中请使用**绝对路径**与**固定 venv 解释器**，并将日志重定向到文件以便排错。 |

---

## 停止 Web 服务

在运行 `main.py`（或 `app.py`）的控制台窗口按 **Ctrl+C** 结束进程；若使用 **`deploy_ecs.sh`** 安装的 **systemd**，服务名一般为 **`case-excel-web`**：`systemctl stop case-excel-web`（以实际单元文件名为准）。

## 许可证与声明

本项目结构以实用与内网演示为主；生产部署请修改默认密钥、账号与调试选项，并做好访问控制与审计。
