from __future__ import annotations

import bz2
import contextlib
import ctypes
import glob
import gzip
import io
import json
import lzma
import os
import re
import shutil
import tarfile
import warnings
import zlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import polars as pl

# rds2py 0.10 prints a line for each optional package it does not find.
with contextlib.redirect_stdout(io.StringIO()):
    import rds2py
    from rds2py.generics import _dispatcher
    from rds2py.PyRdaReader import PyRdaParser, _RdsProcessorHelper
    from rds2py.PyRdsReader import PyRdsParser


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

# Decompressors for an object in an installed package's lazy-load database, by the type
# byte R writes in front of it (R_compress1 to R_compress3 in R's src/main/serialize.c).
# R writes xz as a headerless LZMA2 stream at preset 6, which the reader has to be told.
_LAZY_DATA_CODECS = {
    b"Z": lambda: lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=[{"id": lzma.FILTER_LZMA2, "preset": 6}]),
    b"2": bz2.BZ2Decompressor,
    b"1": zlib.decompressobj,
    b"0": lambda: None,
}

# rds2py's converter of one parsed R object, which its file readers are built on.
_R_OBJECT = _RdsProcessorHelper()

# How R stores a missing logical or integer value.
_R_NA_INTEGER = -(2**31)


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


def _download(meta_type: str, out: Path, progress: bool) -> Exception | None:
    """Save ``lst_<type>`` from the NBDCtoolsData source package on r-universe, or return why not."""
    _progress(progress, f"Starting metadata download for type={meta_type!r}.")
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
            return None
        except HTTPError as err:
            last_error = RuntimeError(f"HTTP {err.code} while downloading {err.url}: {err.reason}")
            _progress(progress, f"Download failed with HTTP {err.code}: {err.reason}")
        except Exception as err:
            last_error = err
            _progress(progress, f"Download attempt failed: {err}")

    _progress(progress, "All download attempts failed.")
    return last_error


def _r_library_globs() -> list[str]:
    """Glob patterns for the R libraries of a standard R, renv, pak or conda setup.

    pak has no library of its own and installs into R's default one. Patterns for
    another operating system simply match nothing.
    """
    env = os.environ.get
    home = os.path.expanduser("~")

    def below(folder: str | None, *parts: str) -> list[str]:
        return [os.path.join(glob.escape(folder), *parts)] if folder else []

    def renv_libraries(roots: list[str]) -> list[str]:
        # renv keeps a library in [<platform>/]R-<version>/<architecture> below its root.
        return [os.path.join(root, *tail) for root in roots for tail in (("R-*", "*"), ("*", "R-*", "*"))]

    renv_roots = below(env("RENV_PATHS_ROOT")) or [
        *below(env("XDG_CACHE_HOME") or os.path.join(home, ".cache"), "R", "renv"),
        *below(home, "Library", "Caches", "org.R-project.R", "R", "renv"),
        *below(env("LOCALAPPDATA"), "R", "cache", "R", "renv"),
        # Where renv kept its files before R 4.0, and still does while that folder exists.
        *below(home, ".local", "share", "renv"),
        *below(home, "Library", "Application Support", "renv"),
        *below(env("LOCALAPPDATA"), "renv"),
    ]
    renv_caches = below(env("RENV_PATHS_CACHE")) or [os.path.join(root, "cache") for root in renv_roots]
    renv_outside = below(env("RENV_PATHS_LIBRARY_ROOT")) + [os.path.join(root, "library") for root in renv_roots]
    return [
        *(
            lib
            for name in ("R_LIBS", "R_LIBS_USER", "R_LIBS_SITE")
            for path in (env(name) or "").split(os.pathsep)
            for lib in below(os.path.expanduser(path))
        ),
        # renv library of the project in the working directory.
        *renv_libraries(below(env("RENV_PATHS_LIBRARY") or os.path.join("renv", "library"))),
        # Default user libraries: Linux, macOS, macOS before R 4.1, Windows, Windows before R 4.2.
        *below(home, "R", "*-library", "*"),
        *below(home, "Library", "R", "*", "*", "library"),
        *below(home, "Library", "R", "*", "library"),
        *below(env("LOCALAPPDATA"), "R", "win-library", "*"),
        *below(home, "Documents", "R", "win-library", "*"),
        # The R installation in use, a conda environment, then system-wide libraries
        # on Linux, macOS and Windows.
        *below(env("R_HOME"), "library"),
        *below(env("R_HOME"), "site-library"),
        *below(env("CONDA_PREFIX"), "lib", "R", "library"),
        "/usr/local/lib/R/site-library",
        "/usr/local/lib/R/library",
        "/usr/lib/R/site-library",
        "/usr/lib/R/library",
        "/usr/lib64/R/library",
        "/opt/R/*/lib/R/library",
        "/Library/Frameworks/R.framework/Versions/*/Resources/library",
        "/opt/homebrew/lib/R/*/site-library",
        "/usr/local/lib/R/*/site-library",
        *below(env("ProgramFiles"), "R", "R-*", "library"),
        # Libraries renv keeps outside a project, then its package cache, which
        # holds a package in <package>/<version>/<hash>/.
        *renv_libraries([os.path.join(root, "*") for root in renv_outside]),
        *(
            os.path.join(lib, "NBDCtoolsData", "*", "*")
            for lib in renv_libraries([os.path.join(cache, "v*") for cache in renv_caches])
        ),
    ]


def _installed_packages(libs: list[str]) -> list[tuple[tuple[int, ...], str, Path]]:
    """Each NBDCtoolsData installed in ``libs``, as (comparable version, version, package folder)."""
    found: dict[Path, tuple[tuple[int, ...], str, Path]] = {}
    for lib in libs:
        # R installs LazyData as a lazy-load database: Rdata.rdx indexes the objects in Rdata.rdb.
        for rdx in glob.glob(os.path.join(lib, "NBDCtoolsData", "data", "Rdata.rdx")):
            pkg = Path(rdx).parents[1]
            try:
                description = (pkg / "DESCRIPTION").read_text(encoding="utf-8", errors="replace")
                version = re.search(r"^Version:\s*(\S+)", description, re.MULTILINE)[1]
            except (OSError, TypeError):
                continue
            # A library can link to a copy another one holds, as renv's do to its cache.
            found.setdefault(pkg.resolve(), (tuple(map(int, re.findall(r"\d+", version))), version, pkg))
    return list(found.values())


def _save_installed(
    meta_type: str,
    out: Path,
    r_lib_paths: str | Path | Sequence[str | Path] | None,
    progress: bool,
) -> None:
    """Save ``lst_<type>`` from the newest NBDCtoolsData installed in an R library."""
    if r_lib_paths is None:
        libs, where = _r_library_globs(), "the default R library locations"
    else:
        if isinstance(r_lib_paths, (str, os.PathLike)):
            r_lib_paths = [r_lib_paths]
        libs = [glob.escape(os.path.expanduser(lib)) for lib in r_lib_paths]
        where = ", ".join(str(lib) for lib in r_lib_paths)

    installs = _installed_packages(libs)
    if not installs:
        raise FileNotFoundError(
            f"No installed NBDCtoolsData R package found in {where}. If it is installed, "
            "pass the folders R prints for .libPaths() as r_lib_paths."
        )
    if len(installs) > 1:
        _progress(progress, f"Found {len(installs)} installed copies of NBDCtoolsData:")
        for _, version, pkg in installs:
            _progress(progress, f"  {version} in {pkg.parent}")
    _, version, pkg = max(installs, key=lambda install: install[0])
    _progress(
        progress,
        f"Using NBDCtoolsData {version} from {pkg.parent}"
        + (", the highest version." if len(installs) > 1 else "."),
    )

    name = f"lst_{meta_type}"
    index = rds2py.read_rds(str(pkg / "data" / "Rdata.rdx"))
    if name not in index["variables"]:
        raise RuntimeError(f"NBDCtoolsData {version} at {pkg} has no {name}.")
    offset, length = (int(n) for n in index["variables"][name])
    # FALSE, TRUE (zlib), 2 (bzip2) or 3 (xz).
    compressed = int(index["compressed"][0])

    tmp = out.with_name(out.name + ".part")
    with open(pkg / "data" / "Rdata.rdb", "rb") as rdb, gzip.open(tmp, "wb", compresslevel=6) as dst:
        rdb.seek(offset)
        # A compressed object follows its 4-byte length and, unless always zlib, a type byte.
        header = rdb.read({0: 0, 1: 4}.get(compressed, 5))
        decoder = _LAZY_DATA_CODECS[header[4:] or (b"1" if compressed else b"0")]()
        remaining = length - len(header)
        while remaining > 0:
            # lst_dds expands about a hundredfold, so read it in small pieces.
            chunk = rdb.read(min(remaining, 1 << 16))
            if not chunk:
                raise EOFError(f"{rdb.name} ends before {name} does.")
            remaining -= len(chunk)
            dst.write(decoder.decompress(chunk) if decoder else chunk)
    tmp.replace(out)


def download_metadata(
    type: str = "dds",
    path: str | Path | None = None,
    progress: bool = True,
    source: str = "auto",
    r_lib_paths: str | Path | Sequence[str | Path] | None = None,
) -> Path:
    """Save a metadata file from the ``NBDCtoolsData`` R package.

    The metadata is taken from the package on r-universe or, where r-universe
    cannot be reached, from a copy of the package installed in an R library on
    this machine. Neither needs R itself. The file is saved gzip-compressed, by
    default as ``lst_<type>.rda``, and ``load_metadata`` reads it.

    Parameters
    ----------
    type
        ``"dds"`` for the data dictionaries, ``"levels"`` or ``"sessions"``.
    path
        File or folder to save to. Defaults to the working directory.
    progress
        Print what is being done, including which installed package is used.
    source
        Where to take the metadata from. ``"auto"`` tries r-universe, which
        always has the latest release, and uses an installed package if the
        download fails. ``"remote"`` uses r-universe only. ``"local"`` uses an
        installed package only and makes no network request; use it offline,
        or to work with the same metadata version as R does.
    r_lib_paths
        R library folders to look in for an installed ``NBDCtoolsData``, as R
        prints them for ``.libPaths()``. By default the libraries of a standard
        R, renv, pak or conda setup are searched. If several copies are found,
        the highest version is used and all of them are reported. This does not
        change ``source``: with ``"auto"``, r-universe is still tried first.

    Returns
    -------
    Path
        The saved file. From r-universe it is an R data file as ``save()``
        writes it; from an installed package it holds the same object as
        ``saveRDS()`` writes it, so R reads that one with ``readRDS()``.
        ``load_metadata`` reads both.

    Raises
    ------
    RuntimeError
        If the download fails and no installed package can be used instead.
    FileNotFoundError
        If ``source="local"`` and no installed package is found.
    ValueError
        If ``type`` or ``source`` is not one of the values above.
    """
    meta_type = _normalize_meta_type(type)
    if source not in {"auto", "remote", "local"}:
        raise ValueError(f"Invalid source={source!r}. Valid values: auto, local, remote")
    out = _resolve_output_path(meta_type, path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _progress(progress, f"Resolved output path: {out}")

    download_error: Exception | None = None
    if source != "local":
        download_error = _download(meta_type, out, progress)
        if download_error is not None and source == "remote":
            raise RuntimeError(
                "Failed to download metadata after 2 attempts. With R and NBDCtoolsData installed, "
                f'saveRDS(NBDCtoolsData::lst_{meta_type}, "lst_{meta_type}.rds") saves the same metadata.'
            ) from download_error
        if download_error is not None:
            _progress(progress, "Looking for an installed NBDCtoolsData R package instead.")

    if source == "local" or download_error is not None:
        try:
            _save_installed(meta_type, out, r_lib_paths, progress)
        except FileNotFoundError as err:
            if download_error is None:
                raise
            raise RuntimeError(f"Failed to download metadata ({download_error}). {err}") from download_error

    _progress(progress, f"Saved lst_{meta_type} ({out.stat().st_size} bytes).")
    return out


def _column(name: str, col: Any) -> pl.Series:
    """A data frame column as a Series typed after its R type, with missing values as nulls.

    What rds2py makes of a column depends on its version and on the values: a missing
    logical comes out as ``True`` or in an untyped array, a missing integer as NaN in a
    float array, a column without any value untyped, and a factor as its integer codes.
    """
    rtype = col.get_rtype()
    if rtype == "string":
        return pl.Series(name, col.get_string_arr(), dtype=pl.String)
    if rtype == "double":
        # R's NA is one of the NaN values; is.na() is true for all of them.
        return pl.Series(name, col.get_numeric_data(), dtype=pl.Float64).fill_nan(None)
    if rtype in {"integer", "boolean"}:
        values = pl.Series(name, col.get_numeric_data(), dtype=pl.Int32)
        values = values.set(values == _R_NA_INTEGER, None)
        if rtype == "boolean":
            return values.cast(pl.Boolean)
        if "levels" in col.get_attribute_names():
            # A factor holds the position of each value among its levels, counted from 1.
            levels = pl.Series(col.load_attribute_by_name("levels").get_string_arr(), dtype=pl.String)
            return levels.gather(values - 1).alias(name)
        return values
    return pl.Series(name, _R_OBJECT._process_object(col)["data"])


def _to_python(obj: Any) -> Any:
    """Convert a parsed R object, building each data frame as soon as it is reached.

    rds2py's file readers turn the whole file into Python lists before any
    dataframe can be built from them, which for ``lst_dds`` takes well over a
    gigabyte more than converting one column at a time.
    """
    if obj.get_rtype() != "vector":
        return _dispatcher(_R_OBJECT._process_object(obj))

    attributes = obj.get_attribute_names()
    names = obj.load_attribute_by_name("names").get_string_arr() if "names" in attributes else None
    items = (obj.load_vec_element(i) for i in range(obj.get_rsize()))
    if "class" in attributes and "data.frame" in obj.load_attribute_by_name("class").get_string_arr():
        return pl.DataFrame([_column(str(name), col) for name, col in zip(names, items)])
    if names is None:
        return [_to_python(item) for item in items]
    return {name: _to_python(item) for name, item in zip(names, items)}


def _trim_memory() -> None:
    """Return freed memory to the operating system, which glibc otherwise keeps for the process."""
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass  # No glibc: macOS, Windows, musl.


def load_metadata(path: str | Path, progress: bool = True) -> Any:
    """Load a metadata file into nested dicts and Polars DataFrames.

    Reads what ``download_metadata`` saves, and files written in R with
    ``save()`` or ``saveRDS()``. The format is taken from the content of the
    file, not from its extension.
    """
    _progress(progress, f"Loading metadata from: {path}")
    with open(path, "rb") as f:
        # save() output starts with "RDX", saveRDS() output with "X".
        is_rda = _decompressed(f).read(2) == b"RD"
    if is_rda:
        parser = PyRdaParser(str(path))
        (root,) = (parser.rda_object.get_object_by_index(i) for i in range(parser.get_object_count()))
    else:
        parser = PyRdsParser(str(path))
        root = parser.root_object
    _progress(progress, "File parsed; converting data frames to Polars DataFrames.")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="RDS file contains an unknown class")
        converted = _to_python(root)
    # ponytail: rds2py parses a file whole, 1.2 to 1.7 GB for lst_dds 7.0.0 against 0.4 GB of
    # dataframes. Read the data frames straight from the stream if files outgrow memory.
    del parser, root
    _trim_memory()
    _progress(progress, "Metadata conversion complete.")
    return converted


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

    # A TSV file carries no types, and a guess from its first rows fails on a column that
    # starts with whole numbers and holds "13.0" or "T127" further down. Read text, as
    # NBDCtools does, and leave the types to the data dictionary.
    return pl.read_csv(
        file_path, separator="\t", columns=cols, infer_schema=False, null_values=["n/a"]
    ).select(cols)


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

    # Columns read as text, from a TSV file, that the data dictionary types as numbers.
    numbers_from_text: dict[str, pl.Expr] = {}

    if "type_data" in dd.columns:
        type_map = dict(zip(dd.get_column("name").to_list(), dd.get_column("type_data").to_list(), strict=False))
        for var, dtype in type_map.items():
            if var not in data.columns:
                continue
            if dtype == "integer":
                expr_map[var] = pl.col(var).cast(pl.Int64, strict=False).alias(var)
            elif dtype == "double":
                expr_map[var] = pl.col(var).cast(pl.Float64, strict=False).alias(var)
            if dtype in {"integer", "double"} and data.schema[var] == pl.String:
                numbers_from_text[var] = expr_map[var]
            elif dtype in {"character", "text", "time", "date", "timestamp"}:
                expr_map[var] = pl.col(var).cast(pl.Utf8, strict=False).alias(var)

    if categ_to_factor and "type_level" in dd.columns:
        level_map = dict(zip(dd.get_column("name").to_list(), dd.get_column("type_level").to_list(), strict=False))
        for var, level_type in level_map.items():
            if var in data.columns and level_type in {"nominal", "ordinal"}:
                numbers_from_text.pop(var, None)
                # Go through text: Polars takes a number for the index of a category, not
                # for its label, and a TSV file yields numbers where parquet holds text.
                expr_map[var] = pl.col(var).cast(pl.String, strict=False).cast(pl.Categorical).alias(var)

    if numbers_from_text:
        # The casts turn text that is not a number into a missing value. Say so, as R does.
        lost = data.select(
            (pl.col(var).is_not_null() & number.is_null()).sum() for var, number in numbers_from_text.items()
        ).row(0, named=True)
        if any(lost.values()):
            warnings.warn(
                "Values that are not numbers were read as missing, for the number of rows in "
                "brackets: " + ", ".join(f"{var} ({n})" for var, n in lost.items() if n) + ".",
                UserWarning,
                stacklevel=3,
            )

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
