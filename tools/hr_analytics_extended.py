"""
HR 绩效扩展分析：描述统计、缺评、离群、等级占比、一致性、年度对比、部门内 TopN、
评分人统计、目标达成、校准对比、多 Sheet 汇总报表。

供 Web 与命令行调用；依赖列映射见 hr_column_mapper、绩效合并见 perf_data_loader。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from hr_column_mapper import load_hr_config, normalize_columns
from read_excel_data import format_df_table, read_table
from perf_data_loader import read_performance_files


def _need_cols(df: pd.DataFrame, cols: list[str], ctx: str) -> None:
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise ValueError(f"{ctx} 缺少列: {miss}")


def descriptive_by_department(
    base_df: pd.DataFrame, perf_df: pd.DataFrame, year: int
) -> tuple[str, pd.DataFrame]:
    """按部门汇总指定年度绩效分数（描述统计）。"""
    _need_cols(base_df, ["员工ID", "部门"], "基本信息表")
    _need_cols(perf_df, ["员工ID", "年度", "绩效评分"], "绩效表")
    p = perf_df[perf_df["年度"] == year].copy()
    if p.empty:
        return f"{year} 年无绩效数据。", pd.DataFrame()
    b = base_df[["员工ID", "部门"]].drop_duplicates(subset=["员工ID"], keep="first")
    m = b.merge(p, on="员工ID", how="inner")
    if m.empty:
        return "合并后无重叠员工，无法按部门统计。", pd.DataFrame()
    g = (
        m.groupby("部门", dropna=False)["绩效评分"]
        .agg(人数="count", 均值="mean", 标准差="std", 中位数="median", 最小值="min", 最大值="max")
        .reset_index()
        .sort_values("均值", ascending=False)
    )
    for c in ["均值", "标准差", "中位数", "最小值", "最大值"]:
        g[c] = g[c].round(4)
    text = f"=== {year} 年按部门绩效描述统计 ===\n\n" + format_df_table(g, rows=len(g))
    return text, g


def missing_performance_report(
    base_df: pd.DataFrame, perf_df: pd.DataFrame, year: int
) -> tuple[str, pd.DataFrame]:
    """指定年度在基本信息中有、但无任何绩效记录的员工。"""
    _need_cols(base_df, ["员工ID"], "基本信息表")
    _need_cols(perf_df, ["员工ID", "年度"], "绩效表")
    base_ids = set(base_df["员工ID"].dropna().unique())
    perf_ids = set(perf_df.loc[perf_df["年度"] == year, "员工ID"].dropna().unique())
    missing = base_ids - perf_ids
    sub = base_df[base_df["员工ID"].isin(missing)].drop_duplicates(subset=["员工ID"])
    cols = [c for c in ["员工ID", "姓名", "部门", "入职日期"] if c in sub.columns]
    sub = sub[cols] if cols else sub
    text = (
        f"=== {year} 年缺评/无绩效记录员工（共 {len(sub)} 人）===\n\n"
        + (format_df_table(sub, rows=min(200, len(sub))) if not sub.empty else "无")
    )
    return text, sub


def outliers_iqr_report(
    perf_df: pd.DataFrame, year: int
) -> tuple[str, pd.DataFrame]:
    """按年度对绩效评分做 IQR 离群检测。"""
    _need_cols(perf_df, ["员工ID", "年度", "绩效评分"], "绩效表")
    p = perf_df[perf_df["年度"] == year].copy()
    if p.empty:
        return f"{year} 年无数据。", pd.DataFrame()
    s = p["绩效评分"].dropna()
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    flag = (p["绩效评分"] < low) | (p["绩效评分"] > high)
    out = p.loc[flag].copy()
    out["离群类型"] = out["绩效评分"].apply(
        lambda x: "偏低" if pd.notna(x) and x < low else "偏高"
    )
    text = (
        f"=== {year} 年绩效评分 IQR 离群（下界={low:.4f}, 上界={high:.4f}）===\n"
        f"离群条数: {len(out)} / {len(p)}\n\n"
        + (format_df_table(out, rows=min(150, len(out))) if not out.empty else "无离群记录")
    )
    return text, out


def grade_distribution_report(
    perf_df: pd.DataFrame,
    year: int,
    config: dict[str, Any],
) -> tuple[str, pd.DataFrame]:
    """等级分布及与配置中占比上限的简单对比（若有绩效等级列）。"""
    if "绩效等级" not in perf_df.columns:
        return (
            "当前数据无「绩效等级」列（可在 hr_config.json 中配置 grade_column 映射）。",
            pd.DataFrame(),
        )
    _need_cols(perf_df, ["员工ID", "年度", "绩效等级"], "绩效表")
    p = perf_df[perf_df["年度"] == year].copy()
    if p.empty:
        return f"{year} 年无数据。", pd.DataFrame()
    # 每人每年取最后一次季度记录代表当年等级（可按业务改为「最高季度」等）
    if "季度" in p.columns:
        p = p.sort_values(["员工ID", "季度"]).drop_duplicates(
            subset=["员工ID"], keep="last"
        )
    else:
        p = p.drop_duplicates(subset=["员工ID"], keep="first")
    vc = p["绩效等级"].astype(str).value_counts().reset_index()
    vc.columns = ["绩效等级", "人数"]
    n = vc["人数"].sum()
    vc["占比"] = (vc["人数"] / n * 100).round(2).astype(str) + "%"
    bands = config.get("grade_band_max_pct") or {}
    alerts = []
    for _, r in vc.iterrows():
        g = str(r["绩效等级"])
        if g in bands and r["人数"] / n > float(bands[g]) + 1e-9:
            alerts.append(f"等级「{g}」占比 {r['人数']/n:.1%} 超过配置上限 {bands[g]:.0%}")
    extra = "\n预警:\n" + "\n".join(alerts) if alerts else "\n（无占比超标）"
    text = f"=== {year} 年绩效等级分布 ===\n\n" + format_df_table(vc, rows=len(vc)) + extra
    return text, vc


def consistency_check_report(
    base_df: pd.DataFrame, perf_df: pd.DataFrame
) -> tuple[str, pd.DataFrame]:
    """重复员工 ID、绩效中存在但人事中不存在等。"""
    lines: list[str] = ["=== 数据一致性检查 ===\n"]
    rows: list[dict[str, Any]] = []

    if "员工ID" not in base_df.columns or "员工ID" not in perf_df.columns:
        lines.append("缺少员工ID列，跳过检查。")
        return "\n".join(lines), pd.DataFrame(rows)

    bd = base_df["员工ID"].duplicated(keep=False)
    dup_base = base_df.loc[bd, ["员工ID"] + [c for c in ["姓名", "部门"] if c in base_df.columns]]
    lines.append(f"基本信息表中重复出现的员工ID: {dup_base['员工ID'].nunique()} 个（展示前 50 行）")
    if not dup_base.empty:
        lines.append(format_df_table(dup_base.head(50), rows=None))

    base_ids = set(base_df["员工ID"].dropna().unique())
    perf_ids = set(perf_df["员工ID"].dropna().unique())
    orphan = perf_ids - base_ids
    lines.append(f"\n绩效中有而基本信息中无的员工ID: {len(orphan)} 个")
    if orphan:
        sample = sorted(list(orphan))[:100]
        lines.append("示例: " + ", ".join(str(x) for x in sample))

    if all(c in perf_df.columns for c in ["员工ID", "年度", "季度"]):
        ddup = perf_df.duplicated(subset=["员工ID", "年度", "季度"], keep=False)
        n_dup = perf_df.loc[ddup].shape[0]
        lines.append(f"\n绩效表 (员工ID+年度+季度) 重复行数: {n_dup}")
        if n_dup:
            lines.append(format_df_table(perf_df.loc[ddup].head(40), rows=None))

    rows.append({"检查项": "汇总", "说明": "见上方文本"})
    return "\n".join(lines), pd.DataFrame(rows)


def year_over_year_compare(
    base_df: pd.DataFrame,
    perf_df: pd.DataFrame,
    year_a: int,
    year_b: int,
    top_changes: int = 15,
) -> tuple[str, pd.DataFrame]:
    """两年人均分（跨季度平均）对比，列出升降幅最大的员工。"""
    _need_cols(perf_df, ["员工ID", "年度", "绩效评分"], "绩效表")

    def yearly_mean(y: int) -> pd.DataFrame:
        x = perf_df[perf_df["年度"] == y]
        return (
            x.groupby("员工ID", as_index=False)["绩效评分"]
            .mean()
            .rename(columns={"绩效评分": f"均值_{y}"})
        )

    a = yearly_mean(year_a)
    b = yearly_mean(year_b)
    if a.empty or b.empty:
        return f"{year_a} 或 {year_b} 年无绩效数据。", pd.DataFrame()
    m = a.merge(b, on="员工ID", how="outer")
    m["差值"] = m[f"均值_{year_b}"] - m[f"均值_{year_a}"]
    if "姓名" in base_df.columns:
        nm = base_df[["员工ID", "姓名"]].drop_duplicates("员工ID")
        m = m.merge(nm, on="员工ID", how="left")
    up = m.nlargest(top_changes, "差值")
    down = m.nsmallest(top_changes, "差值")
    up = up.assign(类型="上升")
    down = down.assign(类型="下降")
    comb = pd.concat([up, down], ignore_index=True)
    text = (
        f"=== {year_a} vs {year_b} 年度均分对比（各取升降 Top {top_changes}）===\n\n"
        + format_df_table(comb, rows=len(comb))
    )
    return text, comb


def dept_internal_topn(
    base_df: pd.DataFrame,
    perf_df: pd.DataFrame,
    year: int,
    top_n: int = 3,
) -> tuple[str, pd.DataFrame]:
    """各部门内，按该年度绩效均值排名取 TopN。"""
    _need_cols(base_df, ["员工ID", "部门"], "基本信息表")
    _need_cols(perf_df, ["员工ID", "年度", "绩效评分"], "绩效表")
    p = perf_df[perf_df["年度"] == year]
    if p.empty:
        return f"{year} 年无数据。", pd.DataFrame()
    ym = p.groupby("员工ID", as_index=False)["绩效评分"].mean()
    b = base_df[["员工ID", "部门"] + ([c for c in ["姓名"] if c in base_df.columns])].drop_duplicates(
        "员工ID"
    )
    m = ym.merge(b, on="员工ID", how="inner")
    m = m.sort_values(["部门", "绩效评分", "员工ID"], ascending=[True, False, True])
    m["_rank"] = m.groupby("部门")["绩效评分"].rank(method="first", ascending=False)
    top = m[m["_rank"] <= top_n].drop(columns=["_rank"])
    text = (
        f"=== {year} 年各部门内绩效均值 Top {top_n} ===\n\n"
        + format_df_table(top, rows=min(300, len(top)))
    )
    return text, top


def rater_summary_report(perf_df: pd.DataFrame, year: int) -> tuple[str, pd.DataFrame]:
    """按评分人聚合：人数、均分、标准差（用于宽松度粗看）。"""
    if "评分人" not in perf_df.columns:
        return "无「评分人」列（可在配置中映射 rater_column）。", pd.DataFrame()
    p = perf_df[perf_df["年度"] == year].copy()
    if p.empty:
        return f"{year} 年无数据。", pd.DataFrame()
    g = (
        p.groupby("评分人", dropna=False)["绩效评分"]
        .agg(评分条数="count", 均分="mean", 标准差="std")
        .reset_index()
        .sort_values("均分", ascending=False)
    )
    g["均分"] = g["均分"].round(4)
    g["标准差"] = g["标准差"].round(4)
    text = f"=== {year} 年按评分人汇总 ===\n\n" + format_df_table(g, rows=len(g))
    return text, g


def goal_achievement_report(perf_df: pd.DataFrame, year: int) -> tuple[str, pd.DataFrame]:
    """目标值/完成值达成率（列存在时）。"""
    if "目标值" not in perf_df.columns or "完成值" not in perf_df.columns:
        return "无「目标值/完成值」列（可在配置中映射）。", pd.DataFrame()
    p = perf_df[perf_df["年度"] == year].copy()
    if p.empty:
        return f"{year} 年无数据。", pd.DataFrame()
    p["达成率"] = p["完成值"] / p["目标值"].replace(0, pd.NA)
    p["达成率"] = p["达成率"].replace([float("inf"), -float("inf")], pd.NA)
    show = p[
        [c for c in ["员工ID", "年度", "季度", "目标值", "完成值", "达成率"] if c in p.columns]
    ].copy()
    show["达成率"] = (show["达成率"] * 100).round(2)
    text = f"=== {year} 年目标达成（达成率为百分比）===\n\n" + format_df_table(
        show.head(200), rows=None
    )
    return text, show


def calibration_compare_report(perf_df: pd.DataFrame, year: int) -> tuple[str, pd.DataFrame]:
    """校准前/后评分对比（列存在时）。"""
    if "校准前评分" not in perf_df.columns or "校准后评分" not in perf_df.columns:
        return "无「校准前评分/校准后评分」列（可在配置中映射）。", pd.DataFrame()
    p = perf_df[perf_df["年度"] == year].copy()
    if p.empty:
        return f"{year} 年无数据。", pd.DataFrame()
    p["调整差"] = pd.to_numeric(p["校准后评分"], errors="coerce") - pd.to_numeric(
        p["校准前评分"], errors="coerce"
    )
    cols = [
        c
        for c in ["员工ID", "年度", "季度", "校准前评分", "校准后评分", "调整差"]
        if c in p.columns
    ]
    show = p[cols].head(200)
    text = f"=== {year} 年校准前后对比（节选）===\n\n" + format_df_table(show, rows=None)
    return text, show


def build_full_analytics_workbook(
    base_df: pd.DataFrame,
    perf_df: pd.DataFrame,
    year: int,
    year2: Optional[int],
    config: dict[str, Any],
    dept_top_n: int = 3,
    yoy_top: int = 15,
) -> dict[str, pd.DataFrame]:
    """生成多 Sheet 字典，供导出 xlsx。"""
    sheets: dict[str, pd.DataFrame] = {}
    _, df = descriptive_by_department(base_df, perf_df, year)
    if not df.empty:
        sheets["部门描述统计"] = df
    _, df = missing_performance_report(base_df, perf_df, year)
    if not df.empty:
        sheets["缺评名单"] = df
    _, df = outliers_iqr_report(perf_df, year)
    if not df.empty:
        sheets["离群记录"] = df
    _, df = grade_distribution_report(perf_df, year, config)
    if not df.empty:
        sheets["等级分布"] = df
    _, df = dept_internal_topn(base_df, perf_df, year, dept_top_n)
    if not df.empty:
        sheets["部门内TopN"] = df
    if year2 and year2 != year:
        _, df = year_over_year_compare(base_df, perf_df, year, year2, yoy_top)
        if not df.empty:
            sheets["两年对比"] = df
    _, df = rater_summary_report(perf_df, year)
    if not df.empty:
        sheets["评分人汇总"] = df
    _, df = goal_achievement_report(perf_df, year)
    if not df.empty:
        sheets["目标达成"] = df
    _, df = calibration_compare_report(perf_df, year)
    if not df.empty:
        sheets["校准对比"] = df
    return sheets


def run_extended_operation(
    op: str,
    base_df: pd.DataFrame,
    perf_df: pd.DataFrame,
    config: dict[str, Any],
    *,
    year: int = 2024,
    year2: Optional[int] = None,
    top_n: int = 5,
) -> tuple[str, dict[str, pd.DataFrame]]:
    """统一入口：返回展示文本 + 各表（用于导出）。"""
    base_df = normalize_columns(base_df, config)
    perf_df = normalize_columns(perf_df, config)

    sheets: dict[str, pd.DataFrame] = {}
    text = ""

    if op == "ext_desc_dept":
        text, df = descriptive_by_department(base_df, perf_df, year)
        if not df.empty:
            sheets["结果"] = df
    elif op == "ext_missing":
        text, df = missing_performance_report(base_df, perf_df, year)
        if not df.empty:
            sheets["缺评名单"] = df
    elif op == "ext_outliers":
        text, df = outliers_iqr_report(perf_df, year)
        if not df.empty:
            sheets["离群"] = df
    elif op == "ext_grade":
        text, df = grade_distribution_report(perf_df, year, config)
        if not df.empty:
            sheets["等级分布"] = df
    elif op == "ext_consistency":
        text, df = consistency_check_report(base_df, perf_df)
    elif op == "ext_yoy":
        y2 = year2 or (year - 1)
        text, df = year_over_year_compare(base_df, perf_df, y2, year, top_changes=top_n)
        if not df.empty:
            sheets["两年对比"] = df
    elif op == "ext_dept_top":
        text, df = dept_internal_topn(base_df, perf_df, year, top_n=top_n)
        if not df.empty:
            sheets["部门内TopN"] = df
    elif op == "ext_rater":
        text, df = rater_summary_report(perf_df, year)
        if not df.empty:
            sheets["评分人"] = df
    elif op == "ext_goal":
        text, df = goal_achievement_report(perf_df, year)
        if not df.empty:
            sheets["目标达成"] = df
    elif op == "ext_calib":
        text, df = calibration_compare_report(perf_df, year)
        if not df.empty:
            sheets["校准"] = df
    elif op == "ext_full_report":
        ys = build_full_analytics_workbook(
            base_df, perf_df, year, year2, config, dept_top_n=top_n, yoy_top=top_n
        )
        lines = [f"=== 汇总报表（主年={year}" + (f", 对比年={year2}" if year2 else "") + "）===\n"]
        for name, sdf in ys.items():
            lines.append(f"\n--- Sheet: {name} ({len(sdf)} 行) ---")
        text = "\n".join(lines) + "\n\n各 Sheet 已写入 Excel，请下载。"
        sheets = ys
    elif op == "ext_platform_notes":
        text = (
            "=== 以下能力需对接公司基础设施，当前为说明占位 ===\n"
            "- E3 定时订阅：需任务调度（Windows 计划任务 / Airflow）+ 邮件或网盘。\n"
            "- F3 SSO/企微钉钉：需 OAuth 或网关统一认证。\n"
            "- G 大模型：需 API Key 与白名单工具调用策略。\n"
            "- G 预测类：需历史样本与特征工程，建议独立建模项目。\n"
            "本页不生成数据文件。"
        )
    else:
        raise ValueError(f"未知扩展操作: {op}")

    return text, sheets


def write_sheets_to_excel(sheets: dict[str, pd.DataFrame], path: str) -> None:
    if not sheets:
        pd.DataFrame({"说明": ["无数据表输出"]}).to_excel(path, index=False)
        return
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        for name, df in sheets.items():
            sn = str(name)[:31].replace("/", "_").replace("\\", "_")
            df.to_excel(w, sheet_name=sn or "Sheet", index=False)


def _configure_stdio_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> int:
    _configure_stdio_utf8()
    p = argparse.ArgumentParser(description="HR 绩效扩展分析（命令行）")
    p.add_argument("--base", required=True)
    p.add_argument("--perf", nargs="+", required=True)
    p.add_argument("--config", default=None, help="hr_config.json 路径")
    p.add_argument("--op", required=True, help="如 ext_desc_dept / ext_full_report")
    p.add_argument("--year", type=int, default=2024)
    p.add_argument("--year2", type=int, default=None)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--output", default=None)
    args = p.parse_args()

    cfg = load_hr_config(args.config)
    base_df = normalize_columns(read_table(args.base), cfg)
    perf_df, note = read_performance_files(list(args.perf))
    perf_df = normalize_columns(perf_df, cfg)

    text, sheets = run_extended_operation(
        args.op,
        base_df,
        perf_df,
        cfg,
        year=args.year,
        year2=args.year2,
        top_n=args.top,
    )
    print(note)
    print()
    print(text)
    if args.output:
        write_sheets_to_excel(sheets, args.output)
        print()
        print(f"已导出: {os.path.abspath(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
