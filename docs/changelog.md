# Changelog

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
