# Changelog

## 1.0.5

- Fixed wrong categories from `create_dataset_py` when a nominal or ordinal
  variable is stored as a number, which is the case for most of them in TSV
  files. The numbers were taken for positions in an unrelated list of labels,
  so a code `1` could come back as, for example, `ses-01A`, without any
  warning. Categories are now the stored codes as text, the same for parquet
  and TSV input. Results from parquet files, where NBDC stores these codes as
  text, were correct and are unchanged. If you built datasets from TSV files
  with the default `categ_to_factor=True`, please rebuild them.
- `create_dataset_py` now works with Polars 2, which rejects the conversion
  that caused the problem above instead of returning wrong categories.
- Fixed `create_dataset_py` failing to read some TSV files with
  `could not parse ... as dtype i64`. Column types were guessed from the first
  rows, which went wrong for a column that starts with whole numbers and holds
  a value such as `13.0` or `T127` further down. As in `NBDCtools`, the types
  now come from the data dictionary, and `n/a` and empty fields are missing
  values. With the ABCD 7.0 values written to TSV, 8 tables could not be read
  before; now all 765 tables read and give the same values as the parquet
  files. Timestamps are returned as text and keep the notation of the file.
    - A value that the data dictionary types as a number but that is not one
      becomes a missing value, and a warning names the variables concerned.
    - A variable the data dictionary gives no type for is returned as text
      when read from a TSV file.
    - Only the requested columns of a TSV file are read.
- `download_metadata` now works without access to r-universe. If the download
  fails, it reads the metadata from an `NBDCtoolsData` R package installed on
  the machine, so the same code runs on systems that block r-universe but ship
  the R package. R itself is not needed.
- Added `source` to `download_metadata`: `"auto"` (the default, r-universe
  first, then an installed package), `"remote"` (r-universe only) and
  `"local"` (an installed package only, with no network request).
- Added `r_lib_paths` to `download_metadata` to name the R libraries to search.
  By default the libraries of a standard R, renv, pak or conda setup are
  searched. If several copies of `NBDCtoolsData` are found, the highest version
  is used and all of them are listed.
- `load_metadata` needs less memory. Loading `lst_dds` from `NBDCtoolsData`
  7.0.0 peaked at about 3.1 GB and now peaks at about 2.6 GB. Afterwards the
  process holds about 1 GB instead of about 1.8 GB. It is also slightly
  faster.
- `load_metadata` now returns what R holds. It was compared with R value for
  value on all 24 metadata tables of `NBDCtoolsData` 7.0.0, which showed
  three defects:
    - Missing values (`NA`) are now nulls in every column. Before, a missing
      text value was an empty string, a missing number was NaN and turned an
      integer column into a float column, and a missing logical value was
      `True` or left the column without a usable type, depending on the
      installed `rds2py` version.
    - A column keeps the type it has in R even if all its values are missing,
      such as `label_es` in the HBCD data dictionaries.
    - A factor column holds its labels. Before, it held the position of each
      label, so `session_id` in `lst_sessions` for ABCD 6.0 read 1, 2, 3
      instead of `ses-00S`, `ses-00A`, `ses-00M`.
- `nbdctools` now requires `rds2py` 0.9.1 or later. Version 0.9.0 cannot tell
  a missing text value from an empty one.
- `import nbdctools` no longer prints a `Package '...' is not installed.`
  line for each optional package of `rds2py` 0.10.
- `load_metadata` now returns a Polars DataFrame for every R data frame.
  Previously a plain `data.frame`, as opposed to a tibble, could come back as
  a different type depending on which optional packages were installed.

## 1.0.4

- Fixed `download_metadata(type="dds")`, which failed with HTTP 413 because
  r-universe can no longer convert `lst_dds` for download. It now saves the
  metadata file from the `NBDCtoolsData` source package as `lst_<type>.rda`,
  and `load_metadata` reads `.rda` as well as `.rds` files.
- Fixed `create_dataset_py` join semantics so that results no longer depend on
  the order variables and tables are listed in, and so that a coarser-grained
  value reaches every finer row it applies to. Previously a participant-level
  variable could land on a separate all-null row instead of on that
  participant's sessions.
- Fixed `create_dataset_py` additional selections (`vars_add` / `tables_add`):
  each is now joined on its own identifier columns. Previously they were joined
  to each other first, which wrote nulls into identifier columns and let one
  additional table silently blank out another's values.
- `vars_add` / `tables_add` no longer change the row set. An additional table
  finer than the main selection now keeps one value per row, leaves the finer
  identifier columns out of the result, and warns.
- An additional table with duplicate identifier rows now raises `ValueError`
  instead of silently multiplying rows.
- Documented the join and grain semantics for `create_dataset_py`, including
  that they match `NBDCtools::join_tabulated()` with `finer_add = "first"`.
- Re-ran the benchmark page on ABCD 7.0 with `NBDCtools` 1.1.2 and this
  release's code.
- Added the package citation: Zhang, L., Das, B., Celhay, O., Smith, C. J.,
  Ziemer, L. R., Dale, A. M., & Linkersdörfer, J. (2026). *NBDC Data Tools:
  Building Analysis-ready Datasets From ABCD and HBCD Releases in R and
  Python*. bioRxiv. <https://doi.org/10.64898/2026.11.02.763757>. It is shown
  in the import message, the README, and the documentation home page, and
  GitHub's "Cite this repository" reads it from the new `CITATION.cff`.
- Corrected wording and links throughout the documentation. The quickstart no
  longer claims that `create_dataset_py` skips type coercion; it applies the
  variable types from the data dictionary.

## 1.0.3

- No changes from 1.0.2. This version was released before the changes listed
  under 1.0.4 were merged.

## 1.0.2

- Updated docs with better instructions.

## 1.0.1

- Initial Python package release.
- Added R-backed `create_dataset` wrapper behavior.
- Added pure-Python workflow with `create_dataset_py`.
- Added metadata helpers: `download_metadata` and `load_metadata`.
- Added MkDocs documentation site and GitHub Pages deployment workflow.
