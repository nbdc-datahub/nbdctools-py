from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import polars as pl
import rds2py


_METADATA_URLS = {
    "dds": "https://nbdc-datahub.r-universe.dev/NBDCtoolsData/data/lst_dds/rds",
    "levels": "https://nbdc-datahub.r-universe.dev/NBDCtoolsData/data/lst_levels/rds",
    "sessions": "https://nbdc-datahub.r-universe.dev/NBDCtoolsData/data/lst_sessions/rds",
}

_DOWNLOAD_HEADERS = {
    # r-universe may reject urllib's default user-agent with HTTP 403.
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
}


def _progress(enabled: bool, message: str) -> None:
    if enabled:
        print(f"[nbdctools] {message}")


def _normalize_meta_type(meta_type: str) -> str:
    if meta_type == "seesions":
        return "sessions"
    if meta_type not in {"dds", "levels", "sessions"}:
        valid = ", ".join(sorted(["dds", "levels", "sessions", "seesions"]))
        raise ValueError(f"Invalid type={meta_type!r}. Valid values: {valid}")
    return meta_type


def _resolve_output_path(meta_type: str, path: str | Path | None) -> Path:
    default_name = f"lst_{meta_type}.rds"
    if path is None:
        return Path.cwd() / default_name

    out = Path(path)
    if out.exists() and out.is_dir():
        return out / default_name
    if not out.exists() and out.suffix == "":
        return out / default_name
    return out


def download_metadata(
    type: str = "dds",
    path: str | Path | None = None,
    progress: bool = True,
) -> Path:
    """Download metadata RDS file from NBDCtoolsData r-universe."""
    _progress(progress, f"Starting metadata download for type={type!r}.")
    meta_type = _normalize_meta_type(type)
    out = _resolve_output_path(meta_type, path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _progress(progress, f"Resolved output path: {out}")

    url = _METADATA_URLS[meta_type]
    attempts = 2
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            _progress(progress, f"Downloading metadata (attempt {attempt}/{attempts})...")
            req = Request(url, headers=_DOWNLOAD_HEADERS)
            with urlopen(req, timeout=30) as resp:
                payload = resp.read()
            out.write_bytes(payload)
            _progress(progress, f"Download complete ({len(payload)} bytes).")
            return out
        except HTTPError as err:
            last_error = RuntimeError(f"HTTP {err.code} while downloading {url}: {err.reason}")
            _progress(progress, f"Download failed with HTTP {err.code}: {err.reason}")
        except Exception as err:
            last_error = err
            _progress(progress, f"Download attempt failed: {err}")

    _progress(progress, "All download attempts failed.")
    raise RuntimeError(
        "Failed to download metadata after 2 attempts. "
        "Please manually download from https://nbdc-datahub.r-universe.dev/datasets"
    ) from last_error


def load_metadata(path: str | Path, progress: bool = True) -> Any:
    """Load an RDS metadata file into nested dicts and Polars DataFrames."""
    _progress(progress, f"Loading metadata from: {path}")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="RDS file contains an unknown class")
        raw = rds2py.read_rds(str(path))
    _progress(progress, "RDS payload loaded; converting nested payloads to Polars DataFrames.")
    converted = _convert_rds2py_payload(raw)
    _progress(progress, "Metadata conversion complete.")
    return converted


def _is_rds2py_df_payload(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    if not {"type", "data", "attributes"}.issubset(obj.keys()):
        return False

    attributes = obj.get("attributes")
    if not isinstance(attributes, dict):
        return False

    cls_attr = attributes.get("class")
    if not isinstance(cls_attr, dict):
        return False

    classes = cls_attr.get("data")
    return isinstance(classes, list) and "data.frame" in classes


def _payload_to_polars_dataframe(obj: dict[str, Any]) -> pl.DataFrame:
    attributes = obj["attributes"]
    names_attr = attributes.get("names")
    if not isinstance(names_attr, dict):
        raise ValueError("Malformed rds2py payload: missing column names metadata.")

    col_names = names_attr.get("data")
    if not isinstance(col_names, list):
        raise ValueError("Malformed rds2py payload: invalid column names metadata.")

    cols = obj.get("data")
    if not isinstance(cols, list):
        raise ValueError("Malformed rds2py payload: invalid dataframe payload.")

    values: dict[str, Any] = {}
    for idx, col_name in enumerate(col_names):
        if idx >= len(cols):
            raise ValueError("Malformed rds2py payload: fewer columns than declared names.")
        col_payload = cols[idx]
        if not isinstance(col_payload, dict) or "data" not in col_payload:
            raise ValueError("Malformed rds2py payload: invalid column payload.")
        values[str(col_name)] = col_payload["data"]

    return pl.DataFrame(values)


def _convert_rds2py_payload(obj: Any) -> Any:
    if _is_rds2py_df_payload(obj):
        return _payload_to_polars_dataframe(obj)

    if isinstance(obj, dict):
        return {k: _convert_rds2py_payload(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [_convert_rds2py_payload(v) for v in obj]

    return obj


def _as_polars_dataframe(dd: Any) -> pl.DataFrame:
    if isinstance(dd, pl.DataFrame):
        return dd

    if hasattr(dd, "to_dict"):
        try:
            as_dict = dd.to_dict(orient="list")
            return pl.DataFrame(as_dict)
        except Exception:
            pass

    if isinstance(dd, dict):
        if {"name", "table_name", "identifier_columns"}.issubset(dd.keys()):
            return pl.DataFrame(dd)
        if len(dd) == 1:
            return _as_polars_dataframe(next(iter(dd.values())))

    return pl.DataFrame(dd)


def _split_identifier_columns(identifier_columns: str) -> list[str]:
    return [part.strip() for part in str(identifier_columns).split("|") if part.strip()]


def _select_dd(dd: pl.DataFrame, vars: list[str], tables: list[str]) -> pl.DataFrame:
    return dd.filter(
        pl.col("name").is_in(vars) | pl.col("table_name").is_in(tables)
    )


def _validate_requests(
    dd: pl.DataFrame,
    vars: list[str],
    tables: list[str],
    vars_add: list[str],
    tables_add: list[str],
) -> None:
    available_vars = set(dd.get_column("name").to_list())
    available_tables = set(dd.get_column("table_name").to_list())

    missing_vars = (set(vars) | set(vars_add)) - available_vars
    if missing_vars:
        raise ValueError(f"Variables not found in metadata: {sorted(missing_vars)}")

    missing_tables = (set(tables) | set(tables_add)) - available_tables
    if missing_tables:
        raise ValueError(f"Tables not found in metadata: {sorted(missing_tables)}")


def _read_table_slice(
    dir_data: Path,
    table_name: str,
    vars_for_table: list[str],
    identifier_cols: list[str],
    format: str,
) -> pl.DataFrame:
    file_path = dir_data / f"{table_name}.{format}"
    if not file_path.exists():
        raise FileNotFoundError(f"Required data file does not exist: {file_path}")

    cols = list(dict.fromkeys(identifier_cols + vars_for_table))

    if format == "parquet":
        return pl.read_parquet(file_path, columns=cols)

    return pl.read_csv(file_path, separator="\t").select(cols)


def _join_grouped_tables(
    dir_data: Path,
    dd: pl.DataFrame,
    format: str,
) -> pl.DataFrame:
    groups = dd.group_by("identifier_columns").agg(
        pl.col("table_name").unique().alias("tables"),
        pl.col("name").alias("vars"),
    )

    joined_groups: list[pl.DataFrame] = []
    for row in groups.iter_rows(named=True):
        id_cols = _split_identifier_columns(row["identifier_columns"])
        table_frames: list[pl.DataFrame] = []

        for table_name in row["tables"]:
            vars_for_table = (
                dd.filter(pl.col("table_name") == table_name)
                .get_column("name")
                .to_list()
            )
            table_frames.append(
                _read_table_slice(
                    dir_data=dir_data,
                    table_name=table_name,
                    vars_for_table=vars_for_table,
                    identifier_cols=id_cols,
                    format=format,
                )
            )

        grp = table_frames[0]
        for nxt in table_frames[1:]:
            grp = grp.join(nxt, on=id_cols, how="full", coalesce=True)
        joined_groups.append(grp)

    merged = joined_groups[0]
    global_id_cols: list[str] = []
    for ident in dd.get_column("identifier_columns").unique().to_list():
        for col in _split_identifier_columns(ident):
            if col not in global_id_cols:
                global_id_cols.append(col)

    for nxt in joined_groups[1:]:
        by = [c for c in global_id_cols if c in merged.columns and c in nxt.columns]
        if not by:
            raise ValueError("Unable to join metadata groups: no shared identifier columns found.")
        merged = merged.join(nxt, on=by, how="full", coalesce=True)

    return merged


def _apply_basic_types(data: pl.DataFrame, dd: pl.DataFrame, categ_to_factor: bool) -> pl.DataFrame:
    expr_map: dict[str, pl.Expr] = {}

    id_cols: list[str] = []
    for ident in dd.get_column("identifier_columns").unique().to_list():
        for col in _split_identifier_columns(ident):
            if col not in id_cols:
                id_cols.append(col)

    for col_name in id_cols:
        if col_name in data.columns:
            expr_map[col_name] = pl.col(col_name).cast(pl.Utf8, strict=False).alias(col_name)

    if "type_data" in dd.columns:
        type_map = dict(zip(dd.get_column("name").to_list(), dd.get_column("type_data").to_list(), strict=False))
        for var, dtype in type_map.items():
            if var not in data.columns:
                continue
            if dtype == "integer":
                expr_map[var] = pl.col(var).cast(pl.Int64, strict=False).alias(var)
            elif dtype == "double":
                expr_map[var] = pl.col(var).cast(pl.Float64, strict=False).alias(var)
            elif dtype in {"character", "text", "time", "date", "timestamp"}:
                expr_map[var] = pl.col(var).cast(pl.Utf8, strict=False).alias(var)

    if categ_to_factor and "type_level" in dd.columns:
        level_map = dict(zip(dd.get_column("name").to_list(), dd.get_column("type_level").to_list(), strict=False))
        for var, level_type in level_map.items():
            if var in data.columns and level_type in {"nominal", "ordinal"}:
                expr_map[var] = pl.col(var).cast(pl.Categorical, strict=False).alias(var)

    if expr_map:
        data = data.with_columns(list(expr_map.values()))

    desired_vars = dd.get_column("name").to_list()
    keep_id = [c for c in id_cols if c in data.columns]
    keep_vars = [c for c in desired_vars if c in data.columns]
    return data.select(list(dict.fromkeys(keep_id + keep_vars)))


def create_dataset_py(
    dir_data: str | Path,
    dd: Any,
    vars: list[str] | None = None,
    tables: list[str] | None = None,
    vars_add: list[str] | None = None,
    tables_add: list[str] | None = None,
    format: str = "parquet",
    categ_to_factor: bool = True,
    progress: bool = True,
) -> pl.DataFrame:
    """Pure Python dataset joiner based on a data-dictionary dataframe.

    Parameters
    ----------
    dd
        Data dictionary dataframe. Accepts a Polars or pandas DataFrame and
        must include columns: ``name``, ``table_name``, and
        ``identifier_columns``.
    """
    _progress(progress, "Starting create_dataset_py.")
    if format not in {"parquet", "tsv"}:
        raise ValueError("format must be one of 'parquet' or 'tsv'.")

    vars = vars or []
    tables = tables or []
    vars_add = vars_add or []
    tables_add = tables_add or []

    if not vars and not tables:
        raise ValueError("At least one of vars or tables must be specified.")

    _progress(progress, "Validating metadata and requested variables/tables.")
    dd = _as_polars_dataframe(dd)
    required_cols = {"name", "table_name", "identifier_columns"}
    missing_cols = required_cols - set(dd.columns)
    if missing_cols:
        raise ValueError(f"dd is missing required columns: {sorted(missing_cols)}")

    _validate_requests(dd, vars, tables, vars_add, tables_add)

    dd_main = _select_dd(dd, vars, tables)
    if dd_main.height == 0:
        raise ValueError("No variables selected from vars/tables after metadata filtering.")
    _progress(progress, f"Main selection includes {dd_main.height} metadata rows.")

    dd_add = _select_dd(dd, vars_add, tables_add)
    if dd_add.height > 0:
        dd_add = dd_add.filter(~pl.col("name").is_in(dd_main.get_column("name").to_list()))

    dir_path = Path(dir_data)
    _progress(progress, f"Reading and joining main tables from: {dir_path}")
    data = _join_grouped_tables(dir_path, dd_main, format=format)

    if dd_add.height > 0:
        _progress(progress, f"Joining additional variables ({dd_add.height} metadata rows) with left join.")
        data_add = _join_grouped_tables(dir_path, dd_add, format=format)

        id_cols_all: list[str] = []
        for ident in dd.get_column("identifier_columns").unique().to_list():
            for col in _split_identifier_columns(ident):
                if col not in id_cols_all:
                    id_cols_all.append(col)

        by = [c for c in id_cols_all if c in data.columns and c in data_add.columns]
        if not by:
            raise ValueError("Unable to left-join additional variables: no shared identifier columns found.")
        data = data.join(data_add, on=by, how="left", coalesce=True)

    dd_used = pl.concat([dd_main, dd_add]) if dd_add.height > 0 else dd_main
    _progress(progress, "Applying type conversions and final column selection.")
    out = _apply_basic_types(data, dd_used, categ_to_factor=categ_to_factor)
    _progress(progress, f"create_dataset_py complete. Output shape: {out.shape}")
    return out
