"""
员工绩效分析场景 — 读取表格数据（单一脚本内按子命令拆分，每项能力职责单一）。

子命令：
  preview-head      读取指定表格前 N 行（默认 5）
  by-employee-id    按员工 ID 在多个表格中筛选相关行
  by-hire-date      按入职日期列，筛选早于/晚于指定日期的员工行（可多表）
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

import pandas as pd


def read_table(path: str, sheet: Optional[str] = None) -> pd.DataFrame:
    """读取单张表（xlsx/xls/csv/tsv）。"""
    ext = os.path.splitext(path)[1].lower()
    if ext in {".xlsx", ".xls"}:
        if sheet is None:
            return pd.read_excel(path)
        return pd.read_excel(path, sheet_name=sheet)
    if ext in {".csv"}:
        return pd.read_csv(path)
    if ext in {".tsv"}:
        return pd.read_csv(path, sep="\t")
    raise ValueError(f"不支持的文件类型: {ext}（仅支持 xlsx/xls/csv/tsv）")


def format_df_table(df: pd.DataFrame, rows: Optional[int] = None) -> str:
    """将 DataFrame 格式化为控制台对齐文本（便于阅读）。"""
    preview = df if rows is None else df.head(rows).copy()
    cols = list(preview.columns)
    cell_strs: list[list[str]] = []
    for row in preview.itertuples(index=False, name=None):
        row_str = []
        for v in row:
            if pd.isna(v):
                row_str.append("")
            else:
                row_str.append(str(v))
        cell_strs.append(row_str)

    display_cols = ["行号"] + [str(c) for c in cols]
    display_rows = []
    for i, row_str in enumerate(cell_strs, start=1):
        display_rows.append([str(i)] + row_str)

    widths = [len(c) for c in display_cols]
    for r in display_rows:
        for j, v in enumerate(r):
            widths[j] = max(widths[j], len(v))

    def render_row(values: list[str]) -> str:
        parts = [values[j].ljust(widths[j]) for j in range(len(values))]
        return " | ".join(parts)

    sep = "-+-".join("-" * w for w in widths)
    out_lines = [render_row(display_cols), sep]
    out_lines.extend(render_row(r) for r in display_rows)
    return "\n".join(out_lines)


def preview_head_text(path: str, sheet: Optional[str] = None, rows: int = 5) -> str:
    """读取指定文件前 N 行，返回格式化文本（供 CLI 与 Web 共用）。"""
    df = read_table(path, sheet=sheet)
    lines = [
        f"=== 文件: {os.path.abspath(path)} ===",
    ]
    if sheet:
        lines.append(f"Sheet: {sheet}")
    lines.append(f"总行数: {len(df)}，展示前 {rows} 行")
    lines.append(format_df_table(df, rows=rows))
    return "\n".join(lines)


def cmd_preview_head(args: argparse.Namespace) -> int:
    """读取指定文件前 N 行并打印。"""
    print(preview_head_text(args.file, sheet=args.sheet, rows=args.rows))
    return 0


def _parse_employee_ids(raw: str) -> list:
    parts = [p.strip() for p in raw.replace("，", ",").split(",") if p.strip()]
    if not parts:
        raise ValueError("员工 ID 列表为空")
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except ValueError:
            out.append(p)
    return out


def filter_by_employee_text(
    files: list[str],
    employee_ids: str,
    id_column: str,
    sheet: Optional[str] = None,
) -> str:
    """多表按员工 ID 筛选，返回格式化文本。"""
    ids = _parse_employee_ids(employee_ids)
    blocks: list[str] = []
    for fp in files:
        df = read_table(fp, sheet=sheet)
        if id_column not in df.columns:
            raise ValueError(f"文件缺少列「{id_column}」: {fp}")
        sub = df[df[id_column].isin(ids)]
        part = [
            f"=== 文件: {os.path.abspath(fp)} ===",
            f"匹配行数: {len(sub)} / 总行数 {len(df)}",
        ]
        if sub.empty:
            part.append("(无匹配行)")
        else:
            part.append(format_df_table(sub, rows=None))
        blocks.append("\n".join(part))
    return "\n\n".join(blocks)


def cmd_by_employee_id(args: argparse.Namespace) -> int:
    """在多个文件中按员工 ID 列筛选行。"""
    print(
        filter_by_employee_text(
            list(args.files),
            args.employee_ids,
            args.id_column,
            sheet=args.sheet,
        )
    )
    return 0


def _normalize_date_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def filter_by_hire_date_text(
    files: list[str],
    date_column: str,
    before: Optional[str],
    after: Optional[str],
    sheet: Optional[str] = None,
) -> str:
    """按日期列筛选早于/晚于指定日，返回格式化文本。"""
    if not before and not after:
        raise ValueError("请至少指定 before 或 after 之一")

    before_ts = pd.Timestamp(before) if before else None
    after_ts = pd.Timestamp(after) if after else None
    blocks: list[str] = []

    for fp in files:
        df = read_table(fp, sheet=sheet)
        if date_column not in df.columns:
            raise ValueError(f"文件缺少日期列「{date_column}」: {fp}")
        dates = _normalize_date_series(df[date_column])
        mask = pd.Series(True, index=df.index)
        if before_ts is not None:
            mask = mask & dates.notna() & (dates < before_ts)
        if after_ts is not None:
            mask = mask & dates.notna() & (dates > after_ts)
        sub = df.loc[mask]

        cond = f"列「{date_column}」"
        if before_ts is not None:
            cond += f" 早于 {before_ts.date()}"
        if after_ts is not None:
            cond += f" 晚于 {after_ts.date()}"

        part = [
            f"=== 文件: {os.path.abspath(fp)} ===",
            f"条件: {cond}",
            f"匹配行数: {len(sub)} / 总行数 {len(df)}",
        ]
        if sub.empty:
            part.append("(无匹配行)")
        else:
            part.append(format_df_table(sub, rows=None))
        blocks.append("\n".join(part))
    return "\n\n".join(blocks)


def cmd_by_hire_date(args: argparse.Namespace) -> int:
    """按入职日期列筛选 before / after。"""
    print(
        filter_by_hire_date_text(
            list(args.files),
            args.date_column,
            args.before,
            args.after,
            sheet=args.sheet,
        )
    )
    return 0


def _configure_stdio_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> int:
    _configure_stdio_utf8()

    parser = argparse.ArgumentParser(
        description="员工绩效分析 — 读取 Excel/CSV 数据（按子命令单一职责）。"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_prev = sub.add_parser("preview-head", help="读取指定表格前 N 行")
    p_prev.add_argument("--file", required=True, help="表格文件路径")
    p_prev.add_argument("--sheet", default=None, help="Excel sheet 名（可选）")
    p_prev.add_argument("--rows", type=int, default=5, help="行数，默认 5")
    p_prev.set_defaults(func=cmd_preview_head)

    p_emp = sub.add_parser("by-employee-id", help="按员工 ID 筛选多个表格中的行")
    p_emp.add_argument(
        "--files",
        nargs="+",
        required=True,
        help="一个或多个表格路径",
    )
    p_emp.add_argument(
        "--employee-ids",
        required=True,
        help="员工 ID，逗号分隔，如 1001,1002",
    )
    p_emp.add_argument(
        "--id-column",
        default="员工ID",
        help="作为员工标识的列名，默认 员工ID",
    )
    p_emp.add_argument("--sheet", default=None, help="各文件共用 sheet 名（可选）")
    p_emp.set_defaults(func=cmd_by_employee_id)

    p_date = sub.add_parser(
        "by-hire-date",
        help="按入职日期列筛选早于/晚于指定日期的行（可多表）",
    )
    p_date.add_argument("--files", nargs="+", required=True, help="表格路径列表")
    p_date.add_argument(
        "--date-column",
        default="入职日期",
        help="日期列名，默认 入职日期",
    )
    p_date.add_argument(
        "--before",
        default=None,
        help="早于该日期（含当日之前），格式 YYYY-MM-DD",
    )
    p_date.add_argument(
        "--after",
        default=None,
        help="晚于该日期，格式 YYYY-MM-DD",
    )
    p_date.add_argument("--sheet", default=None, help="共用 sheet 名（可选）")
    p_date.set_defaults(func=cmd_by_hire_date)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
