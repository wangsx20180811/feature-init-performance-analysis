"""
员工绩效分析场景 — 按指定列名将两张表合并并导出 Excel（职责单一：表对表合并）。

支持左右表连接键相同（--on）或列名不同（--left-on / --right-on）。
可选对右表按连接键去重，避免一对多膨胀。
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

import pandas as pd


def read_table(path: str, sheet: Optional[str] = None) -> pd.DataFrame:
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


def _configure_stdio_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def merge_dataframes(
    left_df: pd.DataFrame,
    right_df: pd.DataFrame,
    *,
    on: Optional[str],
    left_on: Optional[str],
    right_on: Optional[str],
    how: str,
    dedupe_right: bool,
) -> pd.DataFrame:
    """在内存中合并左右 DataFrame，逻辑与 merge_tables 一致。"""
    if on:
        if on not in left_df.columns:
            raise ValueError(f"左表缺少列: {on}")
        if on not in right_df.columns:
            raise ValueError(f"右表缺少列: {on}")
        left_keys = right_keys = [on]
    else:
        if not left_on or not right_on:
            raise ValueError("未指定 on 时，必须同时指定 left_on 与 right_on")
        if left_on not in left_df.columns:
            raise ValueError(f"左表缺少列: {left_on}")
        if right_on not in right_df.columns:
            raise ValueError(f"右表缺少列: {right_on}")
        left_keys = [left_on]
        right_keys = [right_on]

    right_part = right_df.copy()
    if dedupe_right:
        rk = right_keys[0] if len(right_keys) == 1 else None
        if rk:
            right_part = right_part.drop_duplicates(subset=[rk], keep="first")

    if on:
        return left_df.merge(right_part, on=on, how=how)
    return left_df.merge(
        right_part,
        how=how,
        left_on=left_keys,
        right_on=right_keys,
    )


def merge_tables(
    left_path: str,
    right_path: str,
    *,
    left_sheet: Optional[str],
    right_sheet: Optional[str],
    on: Optional[str],
    left_on: Optional[str],
    right_on: Optional[str],
    how: str,
    dedupe_right: bool,
) -> pd.DataFrame:
    left_df = read_table(left_path, sheet=left_sheet)
    right_df = read_table(right_path, sheet=right_sheet)
    return merge_dataframes(
        left_df,
        right_df,
        on=on,
        left_on=left_on,
        right_on=right_on,
        how=how,
        dedupe_right=dedupe_right,
    )


def main() -> int:
    _configure_stdio_utf8()

    parser = argparse.ArgumentParser(
        description="按指定列合并两个表格并导出 xlsx（员工绩效分析 — 合并数据）。"
    )
    parser.add_argument("--left", required=True, help="左表（主表）文件路径")
    parser.add_argument("--right", required=True, help="右表文件路径")
    parser.add_argument("--left-sheet", default=None, help="左表 sheet（可选）")
    parser.add_argument("--right-sheet", default=None, help="右表 sheet（可选）")
    parser.add_argument(
        "--on",
        default=None,
        help="左右表用于匹配的同名列，例如 员工ID",
    )
    parser.add_argument(
        "--left-on",
        default=None,
        help="左表连接列（与 --right-on 成对使用）",
    )
    parser.add_argument(
        "--right-on",
        default=None,
        help="右表连接列",
    )
    parser.add_argument(
        "--how",
        default="left",
        choices=["left", "right", "inner", "outer"],
        help="pandas merge 方式，默认 left",
    )
    parser.add_argument(
        "--dedupe-right",
        action="store_true",
        help="合并前按右表连接键去重（保留首行），避免一对多行膨胀",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="合并结果 xlsx 输出路径",
    )

    args = parser.parse_args()

    merged = merge_tables(
        args.left,
        args.right,
        left_sheet=args.left_sheet,
        right_sheet=args.right_sheet,
        on=args.on,
        left_on=args.left_on,
        right_on=args.right_on,
        how=args.how,
        dedupe_right=args.dedupe_right,
    )
    merged.to_excel(args.output, index=False)
    print("=== 合并完成 ===")
    print(f"输出: {os.path.abspath(args.output)}")
    print(f"结果行数: {len(merged)}")
    print(f"结果列数: {len(merged.columns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
