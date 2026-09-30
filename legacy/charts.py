"""
Auto chart selection — a lightweight, LIDA-style heuristic.

Given a result DataFrame, pick a sensible chart (or none). Rules, in order:
  - 1 categorical + 1 numeric  -> bar
  - 2 numeric                  -> scatter
  - 1 datetime + 1 numeric     -> line
  - a single numeric column    -> histogram
  - otherwise                  -> no chart (just show the table)

Returns a plotly Figure or None.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px


def _numeric_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]


def _datetime_cols(df: pd.DataFrame) -> list[str]:
    out = []
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            out.append(c)
    return out


def pick_chart(df: pd.DataFrame):
    if df is None or df.empty or len(df.columns) < 1:
        return None
    # Too many rows for a categorical bar becomes noise; cap it.
    if len(df) > 50:
        df = df.head(50)

    num = _numeric_cols(df)
    dt = _datetime_cols(df)
    cat = [c for c in df.columns if c not in num and c not in dt]

    try:
        if len(dt) >= 1 and len(num) >= 1:
            return px.line(df, x=dt[0], y=num[0], title=f"{num[0]} over {dt[0]}")
        if len(cat) >= 1 and len(num) >= 1:
            return px.bar(df, x=cat[0], y=num[0], title=f"{num[0]} by {cat[0]}")
        if len(num) >= 2:
            return px.scatter(df, x=num[0], y=num[1], title=f"{num[1]} vs {num[0]}")
        if len(num) == 1:
            return px.histogram(df, x=num[0], title=f"distribution of {num[0]}")
    except Exception:  # noqa: BLE001 - charting is best-effort, never break the app
        return None
    return None
