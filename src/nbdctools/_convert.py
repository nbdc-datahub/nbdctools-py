from __future__ import annotations

import os
from typing import Any

import polars as pl
import rpy2.robjects as ro
from rpy2.robjects import pandas2ri
from rpy2.robjects.conversion import localconverter


_R_HAS_ARROW = ro.r["requireNamespace"]("arrow", quietly=True)[0]

if _R_HAS_ARROW:
    _R_DF_TO_ARROW_IPC = ro.r(
        """
        function(df) {
                    path <- tempfile(fileext = ".feather")
                    arrow::write_feather(df, sink = path)
                    path
        }
        """
    )
else:
    _R_DF_TO_ARROW_IPC = None

if _R_HAS_ARROW:
    _R_WRITE_FEATHER = ro.r(
        """
        function(df, path) {
          arrow::write_feather(df, sink = path)
          invisible(NULL)
        }
        """
    )
else:
    _R_WRITE_FEATHER = None


def _is_na(value: Any) -> bool:
    return (
        value is ro.NA_Character
        or value is ro.NA_Integer
        or value is ro.NA_Logical
        or value is ro.NA_Real
    )


def _col_to_python(col: Any) -> list[Any]:
    is_factor = bool(ro.r["inherits"](col, "factor")[0])
    is_time_like = bool(ro.r["inherits"](col, "hms")[0]) or bool(ro.r["inherits"](col, "POSIXt")[0])

    if is_factor or is_time_like:
        as_char = ro.r["as.character"](col)
        return [None if _is_na(item) else str(item) for item in as_char]

    result = []
    for item in col:
        if _is_na(item):
            result.append(None)
        else:
            result.append(item)
    return result


def has_r_arrow() -> bool:
    return bool(_R_HAS_ARROW)


def _require_r_arrow(mode: str) -> None:
    if not has_r_arrow() or _R_WRITE_FEATHER is None:
        raise RuntimeError(
            f"return_mode={mode!r} requires R package 'arrow' to be installed and available."
        )


def _require_pandas(mode: str) -> Any:
    try:
        import pandas as pd
    except ImportError as err:
        raise RuntimeError(
            f"return_mode={mode!r} requires optional dependency 'pandas'. Install it to use this mode."
        ) from err
    return pd


def _require_pyarrow(mode: str) -> None:
    try:
        import pyarrow  # noqa: F401
    except ImportError as err:
        raise RuntimeError(
            f"return_mode={mode!r} requires optional dependency 'pyarrow'. Install it to use this mode."
        ) from err


def _write_feather_to_tempfile(r_df: Any, mode: str) -> str:
    _require_r_arrow(mode)
    path = str(ro.r["tempfile"](fileext=".feather")[0])
    _R_WRITE_FEATHER(r_df, path)
    return path


def r_dataframe_to_polars(r_df: Any) -> pl.DataFrame:
    """Convert an R data.frame/tibble to polars.DataFrame via direct rpy2 mapping."""
    columns: dict[str, list[Any]] = {}

    for name in r_df.names:
        columns[str(name)] = _col_to_python(r_df.rx2(name))

    return pl.DataFrame(columns)


def r_dataframe_to_polars_sink(r_df: Any) -> pl.DataFrame:
    """Convert an R data.frame/tibble to polars.DataFrame via Arrow sink."""
    if _R_DF_TO_ARROW_IPC is not None:
        ipc_path = str(_R_DF_TO_ARROW_IPC(r_df)[0])
    else:
        ipc_path = _write_feather_to_tempfile(r_df, mode="polars_sink")

    try:
        return pl.read_ipc(ipc_path, memory_map=False)
    finally:
        if os.path.exists(ipc_path):
            os.remove(ipc_path)


def r_dataframe_to_pandas(r_df: Any) -> Any:
    """Convert an R data.frame/tibble to pandas.DataFrame via rpy2 conversion."""
    _require_pandas("pd")
    with localconverter(ro.default_converter + pandas2ri.converter):
        return ro.conversion.rpy2py(r_df)


def r_dataframe_to_pandas_sink(r_df: Any) -> Any:
    """Convert an R data.frame/tibble to pandas.DataFrame via Arrow sink."""
    pd = _require_pandas("pd_sink")
    _require_pyarrow("pd_sink")
    ipc_path = _write_feather_to_tempfile(r_df, mode="pd_sink")
    try:
        return pd.read_feather(ipc_path)
    finally:
        if os.path.exists(ipc_path):
            os.remove(ipc_path)
