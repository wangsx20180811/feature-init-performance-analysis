# 变更记录

本文档便于迭代间对照；发布前可据此撰写提交说明。

## [未发布] 待下次 `git commit` / `git push`

### 2026-03-30 — README 热升级说明、中英双语与 GitHub 展示说明

- **`README.md`**：增加 **热升级与数据保留（推荐）** 章节；文首 **语言切换**；说明 GitHub 文件列表显示的是 **最近提交 message** 而非独立描述。
- **`README.en.md`**：英文摘要（目录、热升级、ECS、登录规则等），完整细节仍链回中文 README。

### 2026-03-30 — 代码审查、CHANGELOG 校正与发布打包

- **审查**：`hr_excel_web/app.py` 中 `must_change_initial_password` 与登录、工作台、`/download` 拦截一致；内置口令为「账号=密码」；无残留旧版统一演示口令逻辑。`scripts/deploy_ecs.sh` 默认 **`DEPLOY_GENERATE_LOGIN_PASSWORDS=0`**，与文档一致。
- **CHANGELOG**：校正下方「登录用户自助修改密码」条目中过时的「灰色演示区」表述（当前改密页不展示口令明文）。
- **发布包**：已删除 **`d:\AI_mode_dev\`** 下历史 **`CASE-Excel_merge_release_*.tar.gz`**，并重新执行 **`package_release.sh`**；本次生成 **`CASE-Excel_merge_release_20260330_123027.tar.gz`**（约 73KB，路径为项目上一级目录）。

### 2026-03-30 — 初始密码=账号名 + 首次登录强制改密

- **默认**：未配置 `HR_WEB_PASSWORD_*` 时，**密码与账号相同**；**未**写入 `password_overrides.json` 前仅可进入改密页，工作台/下载会重定向。
- **部署**：`DEPLOY_GENERATE_LOGIN_PASSWORDS` 默认 **`0`**（不默认生成随机 env 口令）；`1` 仍为可选随机串。
- **登录页**：说明「账号=密码」规则；若已配置 env 则提示向管理员索取。

### 2026-03-30 — 发布包排除项（`package_release.sh`）

- **排除**：`logs/`（部署日志）、`hr_excel_web/password_overrides.json`（运行期改密）、`.vscode/`（本机 IDE），避免把本机状态打进 `tar.gz`。

### 2026-03-30 — 登录用户自助修改密码（`password_overrides.json`）

- **能力**：登录后在 **「修改密码」**（`/settings/password`）输入当前口令与新口令（≥8 字符）；新口令以 **Werkzeug 哈希**写入 **`hr_excel_web/password_overrides.json`**（权限尽量 600），**优先于** `HR_WEB_PASSWORD_*` / 内置「账号=密码」规则。
- **页面**：说明首次改密要求与管理员协助方式；**不**在页面展示口令明文。
- **其它**：`.gitignore` 忽略 **`password_overrides.json`**；工作台 header 含「修改密码」入口。

### 2026-03-30 — 生产登录与演示密码说明（`HR_WEB_PASSWORD_*`）

- **根因**：`deploy_ecs.sh` 将随机 **`HR_WEB_PASSWORD_*`** 写入 **`/etc/default/case-excel-web`**，凭据副本 **`/root/.case-excel-web.initial`**；而登录页曾固定展示 **`HrPerf@2026`** 等演示口令，易与生产环境不一致。
- **改动**：`hr_excel_web/app.py` 检测任一 **`HR_WEB_PASSWORD_*`** 非空时，登录页展示**环境变量模式**说明；演示账号区标注「仅未配置 HR_WEB_PASSWORD_* 时可用」。**`scripts/deploy_ecs.sh`** 部署成功日志中增加 **`grep` / initial 文件** 提示。**`README.md`** ECS 节补充「生产登录与演示密码」。
- **验证**：配置 env 密码后打开 `/`，应出现蓝色提示条；本地未配置 env 时行为与原先一致。

### 2026-03-30 — `scripts/deploy_ecs.sh` 部署健康检查

- **现象**：`systemd` 已将服务标为 `active` 后，Flask 仍在加载依赖（如 pandas），尚未监听端口；单次 `curl` 与健康检查同一秒内执行，易出现 `Connection refused` / HTTP 非 200，误判部署失败。
- **改动**：`step_health` 对 `http://127.0.0.1:${HR_WEB_PORT}/` 做**轮询**（间隔 2s，最多约 90s），直至 HTTP 为 200/301/302 方视为通过。
- **验证建议**：服务器上更新脚本后再次执行 `sudo bash scripts/deploy_ecs.sh`；或确认冷启动后 `curl` 返回 200。

---

（后续迭代请在本节上方追加条目，或发布后改为带版本号的小节。）
