from __future__ import annotations

import bz2
import gzip
import io
import json
import lzma
import shutil
import tarfile
import warnings
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import polars as pl
import rds2py


# The r-universe data API (/NBDCtoolsData/data/<name>/rds) converts a dataset in
# an R process limited to 1 GB, which lst_dds outgrew (HTTP 413). The source
# package serves the .rda files as they are.
_PACKAGE_INFO_URL = "https://nbdc-datahub.r-universe.dev/api/packages/NBDCtoolsData"
_SOURCE_URL = "https://nbdc-datahub.r-universe.dev/src/contrib/NBDCtoolsData_{version}.tar.gz"

_DOWNLOAD_HEADERS = {
    # r-universe may reject urllib's default user-agent with HTTP 403.
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
}

# Leading bytes of the compressions R's save() and saveRDS() can write.
_R_COMPRESSION = {b"\x1f\x8b\x08": gzip.open, b"BZh": bz2.open, b"\xfd7z": lzma.open}


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
    default_name = f"lst_{meta_type}.rda"
    if path is None:
        return Path.cwd() / default_name

    out = Path(path)
    if out.exists() and out.is_dir():
        return out / default_name
    if not out.exists() and out.suffix == "":
        return out / default_name
    return out


def _decompressed(f: Any) -> Any:
    """Return a reader for the uncompressed content of the seekable binary file ``f``."""
    opener = _R_COMPRESSION.get(f.read(3))
    f.seek(0)
    return opener(f) if opener else f


def _fetch(url: str) -> bytes:
    with urlopen(Request(url, headers=_DOWNLOAD_HEADERS), timeout=30) as resp:
        return resp.read()


def download_metadata(
    type: str = "dds",
    path: str | Path | None = None,
    progress: bool = True,
) -> Path:
    """Download a metadata file from the NBDCtoolsData source package on r-universe.

    The file is saved as a gzip-compressed ``.rda`` (by default ``lst_<type>.rda``),
    which ``load_metadata`` reads.
    """
    _progress(progress, f"Starting metadata download for type={type!r}.")
    meta_type = _normalize_meta_type(type)
    out = _resolve_output_path(meta_type, path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _progress(progress, f"Resolved output path: {out}")

    attempts = 2
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            _progress(progress, f"Downloading metadata (attempt {attempt}/{attempts})...")
            version = json.loads(_fetch(_PACKAGE_INFO_URL))["Version"]
            payload = _fetch(_SOURCE_URL.format(version=version))
            _progress(progress, f"Downloaded NBDCtoolsData {version} ({len(payload)} bytes).")
            tmp = out.with_name(out.name + ".part")
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
                member = tar.extractfile(f"NBDCtoolsData/data/lst_{meta_type}.rda")
                # rds2py reads gzip but not the package's xz; level 6 is R's default.
                with _decompressed(member) as src, gzip.open(tmp, "wb", compresslevel=6) as dst:
                    shutil.copyfileobj(src, dst, 1 << 24)
            tmp.replace(out)
            _progress(progress, f"Saved lst_{meta_type} ({out.stat().st_size} bytes).")
            return out
        except HTTPError as err:
            last_error = RuntimeError(f"HTTP {err.code} while downloading {err.url}: {err.reason}")
            _progress(progress, f"Download failed with HTTP {err.code}: {err.reason}")
        except Exception as err:
            last_error = err
            _progress(progress, f"Download attempt failed: {err}")

    _progress(progress, "All download attempts failed.")
    raise RuntimeError(
        "Failed to download metadata after 2 attempts. With R and NBDCtoolsData installed, "
        f'saveRDS(NBDCtoolsData::lst_{meta_type}, "lst_{meta_type}.rds") saves the same metadata.'
    ) from last_error


def load_metadata(path: str | Path, progress: bool = True) -> Any:
    """Load a metadata file (``.rda`` or ``.rds``) into nested dicts and Polars DataFrames."""
    _progress(progress, f"Loading metadata from: {path}")
    with open(path, "rb") as f:
        # save() output starts with "RDX", saveRDS() output with "X".
        is_rda = _decompressed(f).read(2) == b"RD"
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="RDS file contains an unknown class")
        if is_rda:
            (raw,) = rds2py.read_rda(str(path)).values()
        else:
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


def _id_cols_in_order(dd: pl.DataFrame) -> list[str]:
    """Identifier columns of a selection, coarsest first.

    Grains are nested (participant - session - run), so the largest identifier
    set spells out the full nesting order.
    """
    grains = sorted(
        (
            _split_identifier_columns(ident)
            for ident in dd.get_column("identifier_columns").unique(maintain_order=True)
        ),
        key=len,
        reverse=True,
    )
    ordered: list[str] = []
    for grain in grains:
        for col in grain:
            if col not in ordered:
                ordered.append(col)
    return ordered


def _grain_frames(
    dir_data: Path,
    dd: pl.DataFrame,
    format: str,
) -> list[tuple[list[str], list[str], pl.DataFrame]]:
    """Read one frame per grain, finest grain first.

    Tables sharing a grain are full-joined on that grain's identifier columns.
    Returning them finest-first lets the caller fan coarser values out onto
    rows already materialized at the finer grain.
    """
    frames: list[tuple[list[str], list[str], pl.DataFrame]] = []

    for ident in dd.get_column("identifier_columns").unique(maintain_order=True).to_list():
        id_cols = _split_identifier_columns(ident)
        grain_dd = dd.filter(pl.col("identifier_columns") == ident)
        tables = grain_dd.get_column("table_name").unique(maintain_order=True).to_list()

        table_frames = [
            _read_table_slice(
                dir_data=dir_data,
                table_name=table_name,
                vars_for_table=grain_dd.filter(pl.col("table_name") == table_name)
                .get_column("name")
                .to_list(),
                identifier_cols=id_cols,
                format=format,
            )
            for table_name in tables
        ]

        grp = table_frames[0]
        for nxt in table_frames[1:]:
            grp = grp.join(nxt, on=id_cols, how="full", coalesce=True)
        frames.append((id_cols, tables, grp))

    frames.sort(key=lambda item: len(item[0]), reverse=True)
    return frames


def _join_main(dir_data: Path, dd: pl.DataFrame, format: str) -> pl.DataFrame:
    """Full-join the main selection, finest grain outwards.

    Folding coarser frames in afterwards keeps every row of the finer grains,
    so a participant-level value lands on each of that participant's sessions
    and runs instead of stranding on a separate all-null row.
    """
    frames = _grain_frames(dir_data, dd, format=format)
    id_cols = _id_cols_in_order(dd)

    merged = frames[0][2]
    for _, _, nxt in frames[1:]:
        by = [c for c in id_cols if c in merged.columns and c in nxt.columns]
        if not by:
            raise ValueError("Unable to join metadata groups: no shared identifier columns found.")
        merged = merged.join(nxt, on=by, how="full", coalesce=True)
    return merged


def _join_additional(
    data: pl.DataFrame,
    data_add: pl.DataFrame,
    add_ids: list[str],
    tables: list[str],
    id_cols: list[str],
) -> pl.DataFrame:
    """Left-join one grain of additional variables onto the main data.

    Each additional grain is joined on its own identifier columns. Joining the
    additional frames to each other first would write nulls into their
    identifier columns, and those nulls then match real nulls in ``data``, so
    one additional table could silently change another's values.
    """
    by = [c for c in id_cols if c in data.columns and c in add_ids]
    if not by:
        raise ValueError(
            f"Unable to left-join additional variables from {tables}: "
            "no shared identifier columns found."
        )

    if data_add.select(add_ids).is_duplicated().any():
        raise ValueError(
            f"Duplicate rows for {add_ids} in {tables}. Additional variables must "
            "have at most one row per identifier combination."
        )

    finer = [c for c in add_ids if c not in by]
    if finer:
        # A finer-grained additional table cannot be attached in full without
        # adding rows, which vars_add/tables_add must never do. Keep one value
        # per row of `data`, picked by the finer identifiers ascending so the
        # choice does not depend on row order within the file.
        deduped = data_add.sort(add_ids).unique(subset=by, keep="first", maintain_order=True)
        n_dropped = data_add.height - deduped.height
        data_add = deduped.drop(finer)
        warnings.warn(
            f"Additional variables from {tables} are more finely grained than the "
            f"main selection ({finer}). Kept the first value per row by {finer} and "
            f"dropped {n_dropped} further value(s). Select {finer} via vars/tables "
            "to keep them all.",
            UserWarning,
            stacklevel=3,
        )

    return data.join(data_add, on=by, how="left", coalesce=True)


def _apply_basic_types(data: pl.DataFrame, dd: pl.DataFrame, categ_to_factor: bool) -> pl.DataFrame:
    expr_map: dict[str, pl.Expr] = {}

    id_cols = _id_cols_in_order(dd)

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

    Tables are joined on the identifier columns they declare in the data
    dictionary, which differ by table: participant-level tables are identified
    by ``participant_id`` alone, session-level tables by ``participant_id`` and
    ``session_id``, and run-level tables also by ``run_id``. A value from a
    coarser table is repeated on every finer row it applies to, so a
    participant-level variable such as birth data appears on every session and
    every run of that participant. The result does not depend on the order
    variables or tables are listed in, and holds one row per distinct
    combination of identifier columns.

    ``vars``/``tables`` are the main selection and determine the row set.
    ``vars_add``/``tables_add`` annotate those rows and never add, remove or
    duplicate one. A variable named in both is taken from the main selection.

    If an additional table is more finely grained than everything in the main
    selection (for example a session-level ``vars_add`` on top of a
    participant-level selection), its values cannot all be attached without
    adding rows. One value per row is kept and the surplus is dropped: the
    value kept is the first by the additional table's own identifier columns,
    i.e. the earliest session or the first run, and the finer identifier
    columns are not added to the result. This always emits a ``UserWarning``.
    To keep every value, select those variables via ``vars``/``tables``
    instead, so the finer grain becomes part of the row set.

    Parameters
    ----------
    dd
        Data dictionary dataframe. Accepts a Polars or pandas DataFrame and
        must include columns: ``name``, ``table_name``, and
        ``identifier_columns``.

    Raises
    ------
    ValueError
        If required metadata columns are missing, if requested variables or
        tables are absent from ``dd``, if two selections share no identifier
        column, or if an additional table has more than one row per identifier
        combination.
    FileNotFoundError
        If a required data file is not present in ``dir_data``.
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
    data = _join_main(dir_path, dd_main, format=format)

    if dd_add.height > 0:
        _progress(progress, f"Joining additional variables ({dd_add.height} metadata rows) with left join.")
        id_cols_all = _id_cols_in_order(dd)
        for add_ids, tables_for_grain, frame in _grain_frames(dir_path, dd_add, format=format):
            data = _join_additional(
                data,
                frame,
                add_ids=add_ids,
                tables=tables_for_grain,
                id_cols=id_cols_all,
            )

    dd_used = pl.concat([dd_main, dd_add]) if dd_add.height > 0 else dd_main
    _progress(progress, "Applying type conversions and final column selection.")
    out = _apply_basic_types(data, dd_used, categ_to_factor=categ_to_factor)
    _progress(progress, f"create_dataset_py complete. Output shape: {out.shape}")
    return out
