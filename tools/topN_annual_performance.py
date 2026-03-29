"""
员工绩效分析：在指定年度内，仅统计四个季度均有绩效记录的员工，
按四季度绩效均值从高到低取 TopN，输出员工 ID、姓名、入职时间及均值、最高值。

命令行示例：
  python topN_annual_performance.py --base 基本信息.xlsx --perf 绩效.xlsx --year 2024 --top 5
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

from perf_data_loader import read_performance_files
from read_excel_data import format_df_table, read_table


def analyze_topn_annual_quarters(
    base_df: pd.DataFrame,
    perf_df: pd.DataFrame,
    year: int = 2024,
    top_n: int = 5,
) -> pd.DataFrame:
    """
    返回列：员工ID, 员工姓名, 入职时间, 四季度绩效均值, 四季度绩效最高值
    仅包含该年度 Q1～Q4 四条绩效均存在的员工；排序：均值降序、最高值降序、员工ID升序。
    """
    if top_n < 1:
        raise ValueError("Top 数量须为正整数")

    need_base = {"员工ID", "姓名", "入职日期"}
    need_perf = {"员工ID", "年度", "季度", "绩效评分"}
    mb = need_base - set(base_df.columns)
    mp = need_perf - set(perf_df.columns)
    if mb:
        raise ValueError(f"员工基本信息表缺少字段: {sorted(mb)}")
    if mp:
        raise ValueError(f"员工绩效表缺少字段: {sorted(mp)}")

    p = perf_df[
        (perf_df["年度"] == year) & (perf_df["季度"].isin([1, 2, 3, 4]))
    ].copy()
    empty_cols = [
        "员工ID",
        "员工姓名",
        "入职时间",
        "四季度绩效均值",
        "四季度绩效最高值",
    ]
    if p.empty:
        return pd.DataFrame(columns=empty_cols)

    p = p.drop_duplicates(subset=["员工ID", "季度"], keep="first")

    wide = p.pivot(index="员工ID", columns="季度", values="绩效评分")
    for q in (1, 2, 3, 4):
        if q not in wide.columns:
            wide[q] = pd.NA

    complete = wide.dropna(subset=[1, 2, 3, 4])
    if complete.empty:
        return pd.DataFrame(columns=empty_cols)

    qcols = [1, 2, 3, 4]
    complete = complete.copy()
    complete["_avg"] = complete[qcols].mean(axis=1)
    complete["_max"] = complete[qcols].max(axis=1)
    complete = complete.reset_index()
    complete = complete.sort_values(
        by=["_avg", "_max", "员工ID"],
        ascending=[False, False, True],
    )
    top = complete.head(top_n)
    base_sub = base_df[["员工ID", "姓名", "入职日期"]].drop_duplicates(
        subset=["员工ID"], keep="first"
    )
    out = top.merge(base_sub, on="员工ID", how="left")

    def _fmt_date(v) -> str:
        if pd.isna(v):
            return ""
        if hasattr(v, "strftime"):
            try:
                return v.strftime("%Y-%m-%d")
            except Exception:
                return str(v)
        return str(v)

    rows = []
    for _, r in out.iterrows():
        rows.append(
            {
                "员工ID": r["员工ID"],
                "员工姓名": "" if pd.isna(r["姓名"]) else str(r["姓名"]),
                "入职时间": _fmt_date(r["入职日期"]),
                "四季度绩效均值": round(float(r["_avg"]), 2),
                "四季度绩效最高值": round(float(r["_max"]), 2),
            }
        )
    return pd.DataFrame(rows)


def format_topn_report(result_df: pd.DataFrame) -> str:
    """将结果格式化为对齐文本表。"""
    if result_df.empty:
        return "无符合条件的员工（需该年度四个季度均存在绩效记录）。"
    return format_df_table(result_df, rows=len(result_df))


def _configure_stdio_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> int:
    _configure_stdio_utf8()
    parser = argparse.ArgumentParser(
        description="分析指定年度四个季度均有绩效的员工，按均值取 TopN。"
    )
    parser.add_argument("--base", required=True, help="员工基本信息表路径")
    parser.add_argument(
        "--perf",
        nargs="+",
        required=True,
        help="一个或多个绩效表路径（按年拆分多文件、单文件多 Sheet、单表长表均可）",
    )
    parser.add_argument("--year", type=int, default=2024, help="年度，默认 2024")
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="取前几名（TopN），默认 5",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="可选：将结果另存为 xlsx",
    )
    args = parser.parse_args()

    if args.top < 1:
        print("错误: --top 须为正整数", file=sys.stderr)
        return 1

    base_df = read_table(args.base)
    perf_df, load_note = read_performance_files(list(args.perf))
    print(load_note)
    print()

    result = analyze_topn_annual_quarters(
        base_df, perf_df, year=args.year, top_n=args.top
    )

    print(
        f"=== {args.year} 年四个季度均有绩效记录的员工 — 按均值 Top {args.top} ==="
    )
    print()
    print(format_topn_report(result))

    if args.output and not result.empty:
        result.to_excel(args.output, index=False)
        print()
        print(f"已导出: {os.path.abspath(args.output)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
