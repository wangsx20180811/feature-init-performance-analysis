"""
将各公司异名列映射为内部标准列名，便于统一分析逻辑。
配置为 JSON：见 hr_config.example.json；未上传配置时使用内置默认别名。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd

# 标准名 -> 可选别名列表（表中已为标准名则不改）
DEFAULT_ALIASES: dict[str, list[str]] = {
    "员工ID": ["工号", "员工编号", "人员编号", "EmpID", "emp_id", "职工编号"],
    "姓名": ["员工姓名", "名字", "人员姓名"],
    "部门": ["所属部门", "Dept", "部门名称", "组织"],
    "入职日期": ["入职时间", "入司日期", "到岗日期"],
    "绩效评分": ["分数", "得分", "绩效分", "评分"],
    "绩效等级": ["等级", "考核等级", "绩效结果"],
    "评分人": ["评价人", "上级", "考评人"],
    "目标值": ["业绩目标", "计划值"],
    "完成值": ["实际值", "达成值"],
    "校准前评分": ["校准前", "原始分"],
    "校准后评分": ["校准后", "调整后分"],
}


def load_hr_config(path: Optional[str]) -> dict[str, Any]:
    """加载 JSON 配置；路径为空或文件不存在时返回空字典。"""
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build_alias_map(config: dict[str, Any]) -> dict[str, list[str]]:
    """合并默认别名与用户配置 aliases。"""
    merged = {k: list(v) for k, v in DEFAULT_ALIASES.items()}
    user = config.get("aliases") or {}
    for k, v in user.items():
        if k not in merged:
            merged[k] = []
        for a in v if isinstance(v, list) else [v]:
            if a not in merged[k]:
                merged[k].append(a)
    return merged


def normalize_columns(df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    """按别名表将列重命名为标准名（每个标准名只映射一次）。"""
    if df is None or df.empty:
        return df
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    aliases = build_alias_map(config)
    renamed: set[str] = set()

    for canonical, alts in aliases.items():
        if canonical in out.columns:
            renamed.add(canonical)
            continue
        for alt in alts:
            if alt in out.columns:
                out = out.rename(columns={alt: canonical})
                renamed.add(canonical)
                break

    # 绩效分数字段：允许配置主列名
    score_col = config.get("performance_score_column") or "绩效评分"
    if score_col != "绩效评分" and score_col in out.columns and "绩效评分" not in out.columns:
        out = out.rename(columns={score_col: "绩效评分"})

    for src, dst in [
        (config.get("grade_column"), "绩效等级"),
        (config.get("rater_column"), "评分人"),
        (config.get("goal_target_column"), "目标值"),
        (config.get("goal_actual_column"), "完成值"),
        (config.get("calibration_before_column"), "校准前评分"),
        (config.get("calibration_after_column"), "校准后评分"),
    ]:
        if src and dst and src in out.columns and dst not in out.columns:
            out = out.rename(columns={src: dst})
    return out
