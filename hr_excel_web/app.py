"""
员工绩效分析 — HR 网页端：登录后上传 Excel，表单或提示词驱动分析，展示结果或下载合并文件。
绩效数据通过 perf_data_loader 统一合并（多文件、多 Sheet、缺省年度从文件名/Sheet 名推断），
再调用 read_excel_data、merge_excel_data、topN_annual_performance、hr_analytics_extended（扩展分析）。
"""

from __future__ import annotations

import csv
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_DIR = _PROJECT_ROOT / "tools"
# 实现脚本位于 tools/，需优先加入路径以便 import merge_excel_data 等
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from merge_excel_data import merge_dataframes
from perf_data_loader import (
    filter_by_employee_union_text,
    preview_performance_union_text,
    read_performance_files,
)
from read_excel_data import (
    filter_by_hire_date_text,
    preview_head_text,
    read_table,
)
from hr_analytics_extended import run_extended_operation, write_sheets_to_excel
from hr_column_mapper import load_hr_config
from topN_annual_performance import analyze_topn_annual_quarters, format_topn_report

APP_ROOT = Path(__file__).resolve().parent
UPLOAD_ROOT = APP_ROOT / "uploads"
EXPORT_ROOT = APP_ROOT / "exports"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
EXPORT_ROOT.mkdir(parents=True, exist_ok=True)

# 磁盘上保存名：YYYYMMDD_HHMMSS_微秒_原始文件名（主名含扩展名，用于同主名去重）
_UPLOAD_STORED_NAME_RE = re.compile(
    r"^(\d{8})_(\d{6})_(\d{6})_(.+)$"
)


def _upload_sort_key_from_stored_filename(filename: str) -> str | None:
    """从带时间戳前缀的保存文件名解析排序键；不匹配则返回 None。"""
    m = _UPLOAD_STORED_NAME_RE.match(filename)
    if not m:
        return None
    d, t, micro, _main = m.groups()
    return f"{d}_{t}_{micro}"


def _upload_main_name_from_stored_filename(filename: str) -> str | None:
    """从保存文件名提取主名（时间戳后的整段原名，含扩展名）。"""
    m = _UPLOAD_STORED_NAME_RE.match(filename)
    if not m:
        return None
    return m.group(4)


def _cleanup_user_upload_dir_keep_newest_per_main_name(user_dir: Path) -> None:
    """
    对 user_dir 内符合「时间戳_主名」规则的文件：按主名分组，每组仅保留时间戳最新的一份，删除其余。
    用于节省空间并避免同一逻辑文件多次上传堆积。
    """
    if not user_dir.is_dir():
        return
    groups: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    for p in user_dir.iterdir():
        if not p.is_file():
            continue
        main = _upload_main_name_from_stored_filename(p.name)
        if main is None:
            continue
        sk = _upload_sort_key_from_stored_filename(p.name)
        if sk is None:
            continue
        groups[main].append((sk, p))
    for _main, items in groups.items():
        if len(items) <= 1:
            continue
        items.sort(key=lambda x: x[0], reverse=True)
        for _sk, path in items[1:]:
            try:
                path.unlink()
            except OSError:
                pass


app = Flask(__name__)
# 生产环境请设置环境变量 HR_WEB_SECRET_KEY（可与 systemd EnvironmentFile 配合）
app.secret_key = os.environ.get("HR_WEB_SECRET_KEY", "hr-excel-web-session-key")

# 内置账号（演示/内网试用；生产环境请改为统一认证或数据库）
USER_STORE = {
    "hr_admin": "HrPerf@2026",   # HR 管理员
    "hr_user": "HrUser@2026",    # HR 业务用户
    "it_admin": "ItOps@2026",    # IT 管理员
    "viewer": "ViewOnly@2026",   # 只读浏览（当前功能与上列相同，便于后续扩展权限）
}


def _save_upload(username: str, field: str) -> str | None:
    f = request.files.get(field)
    if not f or not f.filename:
        return None
    user_dir = UPLOAD_ROOT / username
    user_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    name = Path(f.filename).name
    path = user_dir / f"{ts}_{name}"
    f.save(path)
    _cleanup_user_upload_dir_keep_newest_per_main_name(user_dir)
    return str(path)


def _save_perf_uploads(username: str) -> list[str]:
    """保存本次请求中上传的一个或多个绩效文件；兼容单文件字段 file_b。"""
    user_dir = UPLOAD_ROOT / username
    user_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for f in request.files.getlist("perf_files"):
        if f and f.filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            name = Path(f.filename).name
            path = user_dir / f"{ts}_{name}"
            f.save(path)
            paths.append(str(path))
    if not paths:
        f = request.files.get("file_b")
        if f and f.filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            name = Path(f.filename).name
            path = user_dir / f"{ts}_{name}"
            f.save(path)
            paths.append(str(path))
    if paths:
        _cleanup_user_upload_dir_keep_newest_per_main_name(user_dir)
    return paths


def _save_hr_config_upload(username: str) -> str | None:
    """保存可选的 hr_config.json（列映射与等级占比等）。"""
    f = request.files.get("hr_config")
    if not f or not f.filename:
        return None
    user_dir = UPLOAD_ROOT / username
    user_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = user_dir / f"{ts}_hr_config.json"
    f.save(path)
    _cleanup_user_upload_dir_keep_newest_per_main_name(user_dir)
    return str(path)


def _append_audit(username: str, operation: str, note: str = "") -> None:
    """操作审计日志（CSV，便于后续对接 SIEM）。"""
    path = APP_ROOT / "audit_log.csv"
    new_file = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        if new_file:
            w.writerow(["time", "user", "operation", "note"])
        w.writerow(
            [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                username,
                operation,
                (note or "")[:800],
            ]
        )


def _session_perf_paths(session) -> list[str]:
    """当前会话中的绩效文件路径列表（兼容旧版仅 file_b_path）。"""
    p = session.get("perf_paths")
    if p:
        return list(p)
    fb = session.get("file_b_path")
    if fb:
        return [fb]
    return []


def _try_prompt_route(
    prompt: str,
    path_a: str | None,
    perf_paths: list[str],
) -> tuple[str | None, str | None]:
    """
    简单提示词分流（可选）：返回 (结果文本, 下载文件名) 或 (None, None) 表示未识别。
    """
    if not prompt or not prompt.strip():
        return None, None
    t = prompt.strip()
    t_low = t.lower()

    if not path_a:
        return None, None

    # 预览前若干行
    m_prev = re.search(r"前\s*(\d+)\s*行", t)
    if "预览" in t or ("前" in t and "行" in t):
        rows = int(m_prev.group(1)) if m_prev else 5
        text = preview_head_text(path_a, sheet=None, rows=min(rows, 500))
        return text, None

    if perf_paths and ("合并" in t or "merge" in t_low):
        on = "员工ID"
        m_on = re.search(r"列\s*[:：]?\s*(\S+)", t)
        if m_on:
            on = m_on.group(1).strip()
        base_df = read_table(path_a)
        perf_df, load_note = read_performance_files(perf_paths)
        merged = merge_dataframes(
            base_df,
            perf_df,
            on=on,
            left_on=None,
            right_on=None,
            how="left",
            dedupe_right=True,
        )
        fn = f"合并结果_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        out = EXPORT_ROOT / fn
        merged.to_excel(out, index=False)
        summary = (
            load_note
            + "\n"
            + f"已按提示完成合并（连接列: {on}，左连接，右表去重）。\n"
            f"结果行数: {len(merged)}，列数: {len(merged.columns)}。\n请下载 Excel。"
        )
        return summary, fn

    if perf_paths and "员工" in t and re.search(r"\d{3,}", t):
        ids = ",".join(re.findall(r"\d{3,}", t))
        if ids:
            text = filter_by_employee_union_text(
                path_a, perf_paths, ids, "员工ID"
            )
            return text, None

    # 2024（或指定年）四季均有数据，按均值 TopN；例：「2024四季绩效top5」「四个季度均值前10名」
    if perf_paths and (
        "四季" in t
        or "四个季度" in t
        or ("季度" in t and "均值" in t)
        or ("全年" in t and "绩效" in t)
    ):
        top_m = re.search(r"top\s*(\d+)", t_low) or re.search(
            r"前\s*(\d+)\s*名", t
        )
        top_n = int(top_m.group(1)) if top_m else 5
        top_n = max(1, min(top_n, 500))
        year_m = re.search(r"(20\d{2})", t)
        year = int(year_m.group(1)) if year_m else 2024
        base_df = read_table(path_a)
        perf_df, load_note = read_performance_files(perf_paths)
        result_df = analyze_topn_annual_quarters(
            base_df, perf_df, year=year, top_n=top_n
        )
        title = (
            f"=== {year} 年四个季度均有绩效记录 — 按均值 Top {top_n} ===\n\n"
        )
        text = load_note + "\n\n" + title + format_topn_report(result_df)
        fn = None
        if not result_df.empty:
            fn = f"{year}四季绩效Top{top_n}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            result_df.to_excel(EXPORT_ROOT / fn, index=False)
        return text, fn

    return None, None


@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
        if USER_STORE.get(u) == p:
            session["username"] = u
            session["file_a_path"] = None
            session["perf_paths"] = None
            session.pop("file_b_path", None)
            session.pop("hr_config_path", None)
            return redirect(url_for("workspace"))
        flash("账号或密码错误")
    return render_template("login.html")


@app.route("/workspace", methods=["GET", "POST"])
def workspace():
    username = session.get("username")
    if not username:
        return redirect(url_for("login"))

    result_text = None
    download_name = None

    if request.method == "POST":
        pa = _save_upload(username, "file_a") or session.get("file_a_path")
        new_perf = _save_perf_uploads(username)
        if new_perf:
            session["perf_paths"] = new_perf
        new_cfg = _save_hr_config_upload(username)
        if new_cfg:
            session["hr_config_path"] = new_cfg
        perf_paths = _session_perf_paths(session)
        session["file_a_path"] = pa

        action = request.form.get("action", "form")

        if action == "prompt":
            prompt = request.form.get("prompt", "").strip()
            if not prompt:
                flash("请填写提示词，或改用下方表单操作。")
            elif not pa:
                flash("请先上传表一")
            else:
                rt, dn = _try_prompt_route(prompt, pa, perf_paths)
                if rt is not None:
                    result_text = rt
                    download_name = dn
                else:
                    flash("未能理解该提示词，请使用下方表单选择功能并填写参数。")

        elif action == "form":
            op = request.form.get("operation", "")
            try:
                if op == "preview_a":
                    if not pa:
                        flash("请先上传主表（表一）")
                    else:
                        rows = int(request.form.get("preview_rows", "5"))
                        rows = max(1, min(rows, 500))
                        result_text = preview_head_text(pa, sheet=None, rows=rows)

                elif op == "preview_b":
                    if not perf_paths:
                        flash("请先上传绩效表（可多个文件）")
                    else:
                        rows = int(request.form.get("preview_rows", "5"))
                        rows = max(1, min(rows, 500))
                        result_text = preview_performance_union_text(
                            perf_paths, rows=rows
                        )

                elif op == "merge":
                    if not pa or not perf_paths:
                        flash("合并需要表一（左）与至少一份绩效数据（右，可多文件）")
                    else:
                        on = request.form.get("on_column", "").strip() or "员工ID"
                        how = request.form.get("how", "left") or "left"
                        dedupe = request.form.get("dedupe_right") == "1"
                        base_df = read_table(pa)
                        perf_df, load_note = read_performance_files(perf_paths)
                        merged = merge_dataframes(
                            base_df,
                            perf_df,
                            on=on,
                            left_on=None,
                            right_on=None,
                            how=how,
                            dedupe_right=dedupe,
                        )
                        fn = f"合并结果_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                        out = EXPORT_ROOT / fn
                        merged.to_excel(out, index=False)
                        download_name = fn
                        result_text = (
                            load_note
                            + "\n\n"
                            + f"合并完成。\n"
                            f"连接列: {on}，方式: {how}，"
                            f"右表去重: {'是' if dedupe else '否'}\n"
                            f"结果行数: {len(merged)}，列数: {len(merged.columns)}。\n"
                            f"请下载 Excel 文件。"
                        )

                elif op == "by_employee":
                    if not pa or not perf_paths:
                        flash("需要上传表一与至少一份绩效表，以便分别筛选")
                    else:
                        ids = request.form.get("employee_ids", "").strip()
                        id_col = request.form.get("id_column", "").strip() or "员工ID"
                        if not ids:
                            flash("请填写员工 ID")
                        else:
                            result_text = filter_by_employee_union_text(
                                pa, perf_paths, ids, id_col
                            )

                elif op == "by_date":
                    if not pa:
                        flash("请先上传主表（表一）")
                    else:
                        dc = request.form.get("date_column", "").strip() or "入职日期"
                        before = request.form.get("before_date", "").strip() or None
                        after = request.form.get("after_date", "").strip() or None
                        if not before and not after:
                            flash("请至少填写「早于」或「晚于」其中一个日期")
                        else:
                            result_text = filter_by_hire_date_text(
                                [pa], dc, before, after, sheet=None
                            )

                elif op == "topn_annual_2024":
                    # 表一=员工基本信息；绩效=一个或多个文件合并
                    if not pa or not perf_paths:
                        flash("请先上传表一（员工基本信息）与至少一份绩效数据")
                    else:
                        try:
                            top_n = int(
                                request.form.get("annual_top_n", "5").strip() or "5"
                            )
                        except ValueError:
                            top_n = 5
                        top_n = max(1, min(top_n, 500))
                        base_df = read_table(pa)
                        perf_df, load_note = read_performance_files(perf_paths)
                        result_df = analyze_topn_annual_quarters(
                            base_df, perf_df, year=2024, top_n=top_n
                        )
                        result_text = (
                            load_note
                            + "\n\n"
                            + f"=== 2024 年四个季度均有绩效记录 — 按均值 Top {top_n} ===\n\n"
                            + format_topn_report(result_df)
                        )
                        if not result_df.empty:
                            fn = f"2024四季绩效Top{top_n}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                            out = EXPORT_ROOT / fn
                            result_df.to_excel(out, index=False)
                            download_name = fn
                        _append_audit(username, op, f"top_n={top_n}")

                elif op.startswith("ext_"):
                    if not pa or not perf_paths:
                        flash("扩展分析需要表一与至少一份绩效数据")
                    else:
                        cfg = load_hr_config(session.get("hr_config_path"))
                        base_df = read_table(pa)
                        perf_df, load_note = read_performance_files(perf_paths)
                        try:
                            ey = int(request.form.get("ext_year", "2024") or "2024")
                        except ValueError:
                            ey = 2024
                        y2_raw = (request.form.get("ext_year2") or "").strip()
                        try:
                            ey2 = int(y2_raw) if y2_raw else None
                        except ValueError:
                            ey2 = None
                        try:
                            ext_top = int(request.form.get("ext_top_n", "5") or "5")
                        except ValueError:
                            ext_top = 5
                        ext_top = max(1, min(ext_top, 500))
                        text, sheets = run_extended_operation(
                            op,
                            base_df,
                            perf_df,
                            cfg,
                            year=ey,
                            year2=ey2,
                            top_n=ext_top,
                        )
                        result_text = load_note + "\n\n" + text
                        if sheets:
                            fn = (
                                f"HR扩展分析_{op}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                            )
                            out = EXPORT_ROOT / fn
                            write_sheets_to_excel(sheets, str(out))
                            download_name = fn
                        _append_audit(username, op, f"year={ey},year2={ey2},top={ext_top}")

                else:
                    flash("请选择有效的操作类型")
            except Exception as e:
                flash(f"处理失败: {e}")

    perf_paths_view = _session_perf_paths(session)
    return render_template(
        "index.html",
        username=username,
        result_text=result_text,
        download_name=download_name,
        file_a=bool(session.get("file_a_path")),
        has_perf=bool(perf_paths_view),
        perf_count=len(perf_paths_view),
        has_config=bool(session.get("hr_config_path")),
    )


@app.route("/download/<filename>")
def download(filename: str):
    if not session.get("username"):
        return redirect(url_for("login"))
    safe = Path(filename).name
    path = EXPORT_ROOT / safe
    if not path.exists():
        flash("文件不存在或已过期")
        return redirect(url_for("workspace"))
    return send_file(path, as_attachment=True, download_name=safe)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _port_available(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            return False
    return True


if __name__ == "__main__":
    # 可通过环境变量 HR_WEB_PORT 换端口；HR_WEB_HOST 默认 127.0.0.1，内网/容器可设为 0.0.0.0
    port = int(os.environ.get("HR_WEB_PORT", "5001"))
    host = os.environ.get("HR_WEB_HOST", "127.0.0.1").strip() or "127.0.0.1"
    # HR_WEB_DEBUG：设为 1/true 开启 Flask debug；生产环境建议 0 或不设置（见下方默认）
    _dbg = os.environ.get("HR_WEB_DEBUG", "1").strip().lower()
    debug_mode = _dbg in ("1", "true", "yes", "on")
    if not _port_available(host, port):
        print(
            f"[错误] 端口 {port} 已被占用，本服务无法启动。\n"
            f"请关闭占用该端口的程序，或在命令行执行: set HR_WEB_PORT=5002\n"
            f"然后重新运行本脚本。"
        )
        raise SystemExit(1)
    print()
    print("-" * 52)
    print("  员工绩效分析 Web 服务已启动（请勿关闭本窗口）")
    print(f"  监听地址: {host}:{port}")
    print(f"  本机访问: http://127.0.0.1:{port}/  或 http://localhost:{port}/")
    if host == "0.0.0.0":
        print("  （已绑定 0.0.0.0，请用服务器内网 IP 或域名从其它机器访问）")
    print("  停止服务: 在本窗口按 Ctrl+C")
    print("-" * 52)
    print()
    try:
        app.run(host=host, port=port, debug=debug_mode)
    except OSError as e:
        print(f"[错误] 服务启动失败: {e}")
        raise SystemExit(1) from e
