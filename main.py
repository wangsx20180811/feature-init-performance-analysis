# -*- coding: utf-8 -*-
"""
CASE-Excel_merge 统一入口：
  - 无参数或 web：启动 HR Web（Flask）
  - 子命令：调用 tools/ 下对应脚本（参数已做精简缩写，与直接运行 tools/*.py 功能一致）
"""
from __future__ import annotations

import argparse
import importlib
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / "tools"


def _setup_paths() -> None:
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)


def _delegate_tool(module_name: str, forwarded_argv: list[str]) -> int:
    """将构造好的参数交给 tools 内模块的 main()（与直接 python tools/xxx.py 等价）。"""
    _setup_paths()
    sys.argv = [f"{module_name}.py"] + forwarded_argv
    mod = importlib.import_module(module_name)
    return int(mod.main())


def _run_web(port: int | None) -> None:
    if port is not None:
        os.environ["HR_WEB_PORT"] = str(port)
    app_path = ROOT / "hr_excel_web" / "app.py"
    runpy.run_path(str(app_path), run_name="__main__")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CASE-Excel_merge 统一入口：默认启动 Web；merge/topn/ext/read 调用 tools 模块。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py
  python main.py web --port 5002
  python main.py merge -l 左表.xlsx -r 右表.xlsx -o 合并.xlsx --on 员工ID --dedupe-right
  python main.py topn -b 基本信息.xlsx -p 绩效.xlsx -y 2024 -n 10 -o top.xlsx
  python main.py ext -b 基本信息.xlsx -p 绩效.xlsx --op ext_grade -y 2024 -O 分析.xlsx
  python main.py read preview-head -f 表.xlsx -N 10
  python main.py read by-employee-id -f a.xlsx b.xlsx -e 1001,1002
  python main.py read by-hire-date -f 表.xlsx --before 2022-01-01
        """.strip(),
    )
    sub = parser.add_subparsers(dest="cmd", metavar="子命令", help="省略时等价于 web")

    p_web = sub.add_parser("web", help="启动 HR Web 服务")
    p_web.add_argument(
        "-p",
        "--port",
        type=int,
        default=None,
        metavar="N",
        help="监听端口（默认 5001，亦可设环境变量 HR_WEB_PORT）",
    )

    p_merge = sub.add_parser(
        "merge",
        help="合并两表（tools.merge_excel_data），短参数：-l -r -o",
    )
    p_merge.add_argument("-l", "--left", required=True, help="左表（主表）路径")
    p_merge.add_argument("-r", "--right", required=True, help="右表路径")
    p_merge.add_argument("-o", "--output", required=True, help="输出 xlsx 路径")
    p_merge.add_argument("--left-sheet", default=None, help="左表 sheet 名")
    p_merge.add_argument("--right-sheet", default=None, help="右表 sheet 名")
    p_merge.add_argument("--on", default=None, help="左右同名列，如 员工ID")
    p_merge.add_argument("--left-on", default=None, help="左表连接列")
    p_merge.add_argument("--right-on", default=None, help="右表连接列")
    p_merge.add_argument(
        "--how",
        default="left",
        choices=["left", "right", "inner", "outer"],
        help="合并方式，默认 left",
    )
    p_merge.add_argument(
        "--dedupe-right",
        action="store_true",
        help="右表按连接键去重",
    )

    p_topn = sub.add_parser(
        "topn",
        help="四季均值 TopN（tools.topN_annual_performance）",
    )
    p_topn.add_argument("-b", "--base", required=True, help="员工基本信息表")
    p_topn.add_argument(
        "-p",
        "--perf",
        nargs="+",
        required=True,
        help="一个或多个绩效表路径",
    )
    p_topn.add_argument("-y", "--year", type=int, default=2024, help="年度，默认 2024")
    p_topn.add_argument("-n", "--top", type=int, default=5, help="TopN，默认 5")
    p_topn.add_argument("-o", "--output", default=None, help="可选：导出 xlsx")

    p_ext = sub.add_parser(
        "ext",
        help="扩展分析（tools.hr_analytics_extended），--op 同网页 ext_*",
    )
    p_ext.add_argument("-b", "--base", required=True, help="员工基本信息表")
    p_ext.add_argument(
        "-p",
        "--perf",
        nargs="+",
        required=True,
        help="一个或多个绩效表路径",
    )
    p_ext.add_argument(
        "--op",
        required=True,
        help="操作码，如 ext_desc_dept、ext_grade、ext_full_report",
    )
    p_ext.add_argument("-c", "--config", default=None, help="hr_config.json 路径")
    p_ext.add_argument("-y", "--year", type=int, default=2024, help="分析主年度")
    p_ext.add_argument("--year2", type=int, default=None, help="对比年度（可选）")
    p_ext.add_argument("-n", "--top", type=int, default=5, help="TopN 等条数")
    p_ext.add_argument(
        "-O",
        "--out",
        dest="output",
        default=None,
        metavar="FILE",
        help="导出 Excel 路径（对应底层 --output）",
    )

    p_read = sub.add_parser(
        "read",
        help="表读取与筛选（tools.read_excel_data 子命令）",
    )
    rsub = p_read.add_subparsers(dest="read_cmd", required=True, metavar="read子命令")

    pr_prev = rsub.add_parser("preview-head", help="预览表前 N 行")
    pr_prev.add_argument("-f", "--file", required=True, help="表格路径")
    pr_prev.add_argument("-s", "--sheet", default=None, help="sheet 名")
    pr_prev.add_argument(
        "-N",
        "--rows",
        type=int,
        default=5,
        metavar="N",
        help="行数，默认 5",
    )

    pr_emp = rsub.add_parser("by-employee-id", help="按员工 ID 查多表")
    pr_emp.add_argument(
        "-f",
        "--files",
        nargs="+",
        required=True,
        help="一个或多个表格路径",
    )
    pr_emp.add_argument(
        "-e",
        "--employee-ids",
        required=True,
        help="员工 ID，逗号分隔",
    )
    pr_emp.add_argument(
        "--id-column",
        default="员工ID",
        help="ID 列名，默认 员工ID",
    )
    pr_emp.add_argument("-s", "--sheet", default=None, help="共用 sheet 名")

    pr_date = rsub.add_parser("by-hire-date", help="按入职日期筛选")
    pr_date.add_argument(
        "-f",
        "--files",
        nargs="+",
        required=True,
        help="表格路径列表",
    )
    pr_date.add_argument(
        "--date-column",
        default="入职日期",
        help="日期列名",
    )
    pr_date.add_argument("--before", default=None, help="早于 YYYY-MM-DD")
    pr_date.add_argument("--after", default=None, help="晚于 YYYY-MM-DD")
    pr_date.add_argument("-s", "--sheet", default=None, help="共用 sheet 名")

    return parser


def _argv_merge(ns: argparse.Namespace) -> list[str]:
    out = [
        "--left",
        ns.left,
        "--right",
        ns.right,
        "--output",
        ns.output,
        "--how",
        ns.how,
    ]
    if ns.left_sheet:
        out += ["--left-sheet", ns.left_sheet]
    if ns.right_sheet:
        out += ["--right-sheet", ns.right_sheet]
    if ns.on:
        out += ["--on", ns.on]
    if ns.left_on:
        out += ["--left-on", ns.left_on]
    if ns.right_on:
        out += ["--right-on", ns.right_on]
    if ns.dedupe_right:
        out.append("--dedupe-right")
    return out


def _argv_topn(ns: argparse.Namespace) -> list[str]:
    out = ["--base", ns.base, "--perf"] + list(ns.perf)
    out += ["--year", str(ns.year), "--top", str(ns.top)]
    if ns.output:
        out += ["--output", ns.output]
    return out


def _argv_ext(ns: argparse.Namespace) -> list[str]:
    out = ["--base", ns.base, "--perf"] + list(ns.perf)
    out += ["--op", ns.op, "--year", str(ns.year), "--top", str(ns.top)]
    if ns.config:
        out += ["--config", ns.config]
    if ns.year2 is not None:
        out += ["--year2", str(ns.year2)]
    if ns.output:
        out += ["--output", ns.output]
    return out


def _argv_read(ns: argparse.Namespace) -> list[str]:
    cmd = ns.read_cmd
    if cmd == "preview-head":
        out = [
            "preview-head",
            "--file",
            ns.file,
            "--rows",
            str(ns.rows),
        ]
        if ns.sheet:
            out += ["--sheet", ns.sheet]
        return out
    if cmd == "by-employee-id":
        out = [
            "by-employee-id",
            "--files",
        ] + list(ns.files)
        out += [
            "--employee-ids",
            ns.employee_ids,
            "--id-column",
            ns.id_column,
        ]
        if ns.sheet:
            out += ["--sheet", ns.sheet]
        return out
    if cmd == "by-hire-date":
        out = ["by-hire-date", "--files"] + list(ns.files)
        out += ["--date-column", ns.date_column]
        if ns.before:
            out += ["--before", ns.before]
        if ns.after:
            out += ["--after", ns.after]
        if ns.sheet:
            out += ["--sheet", ns.sheet]
        return out
    raise SystemExit(2)


def main() -> int:
    _setup_paths()
    parser = _build_parser()
    # 无额外参数：直接 Web，与旧版行为一致
    if len(sys.argv) <= 1:
        _run_web(None)
        return 0

    args = parser.parse_args()

    if args.cmd is None or args.cmd == "web":
        port = getattr(args, "port", None)
        _run_web(port)
        return 0

    if args.cmd == "merge":
        return _delegate_tool("merge_excel_data", _argv_merge(args))
    if args.cmd == "topn":
        return _delegate_tool("topN_annual_performance", _argv_topn(args))
    if args.cmd == "ext":
        return _delegate_tool("hr_analytics_extended", _argv_ext(args))
    if args.cmd == "read":
        return _delegate_tool("read_excel_data", _argv_read(args))

    parser.error("未知子命令")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
