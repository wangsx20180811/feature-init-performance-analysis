"""
员工绩效数据统一加载：适配多种 HR 存放方式。

- 单文件多 Sheet：合并所有含「员工ID+季度+绩效评分」的 Sheet；缺「年度」时从 Sheet 名或文件名推断 20xx。
- 单 Sheet 长表：含「年度」「季度」列，直接读取。
- 按年度拆成多个 Excel：传入多个路径，纵向合并；单文件无「年度」列时从文件名推断。
- CSV/TSV：整表读取，缺「年度」时从文件名推断。

合并后按 (员工ID, 年度, 季度) 去重，保留首条。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pandas as pd

from read_excel_data import format_df_table, read_table

# 绩效表必备列（「年度」可通过文件名/Sheet 名补全）
_PERF_CORE = {"员工ID", "季度", "绩效评分"}


def infer_year_from_text(text: str) -> Optional[int]:
    """从文件名、Sheet 名等字符串中提取四位年份（20xx）。"""
    if not text:
        return None
    m = re.search(r"(20\d{2})", str(text))
    return int(m.group(1)) if m else None


def _strip_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    return out


def _is_perf_shape(df: pd.DataFrame) -> bool:
    d = _strip_columns(df)
    return _PERF_CORE.issubset(set(d.columns))


def _ensure_year(
    df: pd.DataFrame, *, file_path: str, sheet_name: str
) -> Optional[pd.DataFrame]:
    """若缺「年度」，用 Sheet 名或文件名补全；无法推断则返回 None 表示该表不可用。"""
    d = _strip_columns(df)
    if not _is_perf_shape(d):
        return None
    if "年度" in d.columns:
        return d
    y = infer_year_from_text(sheet_name) or infer_year_from_text(Path(file_path).name)
    if y is None:
        return None
    d = d.copy()
    d["年度"] = y
    return d


def read_performance_from_excel_file(path: str) -> pd.DataFrame:
    """读取单个 xlsx/xls：遍历全部 Sheet，合并有效片段。"""
    ext = Path(path).suffix.lower()
    if ext not in {".xlsx", ".xls"}:
        raise ValueError(f"非 Excel 文件: {path}")

    xl = pd.ExcelFile(path)
    frames: list[pd.DataFrame] = []
    for sheet in xl.sheet_names:
        raw = pd.read_excel(path, sheet_name=sheet)
        d = _ensure_year(raw, file_path=path, sheet_name=sheet)
        if d is not None and not d.empty:
            frames.append(d)

    if frames:
        return pd.concat(frames, ignore_index=True)

    # 无有效 Sheet 时退回仅读第一张表（兼容旧表）
    raw = pd.read_excel(path)
    d = _ensure_year(raw, file_path=path, sheet_name=xl.sheet_names[0])
    if d is None or d.empty:
        raise ValueError(
            f"无法解析绩效数据（需含列 员工ID、季度、绩效评分，且需「年度」列或能从文件名推断年份）: {path}"
        )
    return d


def read_performance_from_csv_like(path: str) -> pd.DataFrame:
    """读取 csv/tsv 单表。"""
    d = read_table(path, sheet=None)
    d = _ensure_year(d, file_path=path, sheet_name="")
    if d is None or d.empty:
        raise ValueError(f"无法解析绩效 CSV/TSV: {path}")
    return d


def read_performance_file(path: str) -> pd.DataFrame:
    ext = Path(path).suffix.lower()
    if ext in {".xlsx", ".xls"}:
        return read_performance_from_excel_file(path)
    if ext in {".csv", ".tsv"}:
        return read_performance_from_csv_like(path)
    raise ValueError(f"不支持的绩效文件类型: {path}")


def read_performance_files(paths: list[str]) -> tuple[pd.DataFrame, str]:
    """
    合并多个绩效文件为一张长表，并返回简短加载说明（供页面展示）。
    """
    if not paths:
        return (
            pd.DataFrame(
                columns=["员工ID", "年度", "季度", "绩效评分"],
            ),
            "未上传绩效文件。",
        )

    parts: list[pd.DataFrame] = []
    notes: list[str] = []
    for p in paths:
        df = read_performance_file(p)
        parts.append(df)
        notes.append(f"{Path(p).name}({len(df)}行)")

    merged = pd.concat(parts, ignore_index=True)
    merged = _normalize_perf_dtypes(merged)
    merged = merged.drop_duplicates(subset=["员工ID", "年度", "季度"], keep="first")

    summary = "已合并绩效来源: " + "；".join(notes) + f"；合计 {len(merged)} 行（去重后）。"
    return merged, summary


def _normalize_perf_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["员工ID"] = pd.to_numeric(out["员工ID"], errors="coerce")
    out["年度"] = pd.to_numeric(out["年度"], errors="coerce").astype("Int64")
    out["季度"] = pd.to_numeric(out["季度"], errors="coerce").astype("Int64")
    out["绩效评分"] = pd.to_numeric(out["绩效评分"], errors="coerce")
    return out


def preview_performance_union_text(perf_paths: list[str], rows: int = 5) -> str:
    """展示合并后绩效表前若干行（用于 Web「预览表二」）。"""
    if not perf_paths:
        return "未上传绩效文件。"
    df, summary = read_performance_files(perf_paths)
    lines = [summary, ""]
    if df.empty:
        lines.append("合并后无数据行。")
        return "\n".join(lines)
    lines.append(f"=== 合并后绩效表（前 {rows} 行）===")
    lines.append(format_df_table(df, rows=rows))
    return "\n".join(lines)


def filter_by_employee_union_text(
    base_path: str,
    perf_paths: list[str],
    employee_ids: str,
    id_column: str,
) -> str:
    """按员工 ID 在基本信息表与合并后的绩效表中分别筛选并格式化输出。"""
    if not perf_paths:
        raise ValueError("未提供绩效文件")

    perf_df, summary = read_performance_files(perf_paths)
    # 复用解析 ID 与单列筛选逻辑：写入临时双路径不优雅，直接调现有函数需两个路径
    # 这里对合并后的单 DataFrame 手写展示
    ids_raw = employee_ids.replace("，", ",").split(",")
    ids = []
    for p in ids_raw:
        p = p.strip()
        if not p:
            continue
        try:
            ids.append(int(p))
        except ValueError:
            ids.append(p)

    base_df = read_table(base_path)
    if id_column not in base_df.columns:
        raise ValueError(f"基本信息表缺少列: {id_column}")
    if id_column not in perf_df.columns:
        raise ValueError(f"绩效合并表缺少列: {id_column}")

    blocks = [summary, ""]
    sb = base_df[base_df[id_column].isin(ids)]
    blocks.append(f"=== 基本信息表 ===\n匹配行数: {len(sb)} / {len(base_df)}")
    blocks.append(
        format_df_table(sb, rows=None) if not sb.empty else "(无匹配行)"
    )
    sp = perf_df[perf_df[id_column].isin(ids)]
    blocks.append("")
    blocks.append(
        f"=== 绩效数据（已合并多文件/多 Sheet）===\n匹配行数: {len(sp)} / {len(perf_df)}"
    )
    blocks.append(
        format_df_table(sp, rows=None) if not sp.empty else "(无匹配行)"
    )
    return "\n".join(blocks)
