# Troubleshooting

## `NBDCtoolsRError`

When calling `create_dataset`, R-side failures are wrapped as `NBDCtoolsRError`.
Inspect `exc.r_message` to see the original R error.

## Missing R packages

If `create_dataset` fails to find R packages, verify these are installed in your R environment:

- `NBDCtools`
- `NBDCtoolsData`
- `arrow` (required for sink modes)

## R library path issues

If R packages are not found via `rpy2`, export `R_LIBS_USER` before starting Python. See
[R library discovery](../installation.md#r-library-discovery-r_libs_user).

## "Failed to download metadata"

`download_metadata` could not reach r-universe. If the `NBDCtoolsData` R package is
installed on the machine, it is used instead, and this error only appears when no installed
copy was found either.

- If the package is installed in an unusual place, pass its library with `r_lib_paths`.
  In R, `.libPaths()` lists the libraries and `find.package("NBDCtoolsData")` shows which
  one holds the package.
- Otherwise, save the metadata on a machine with R and copy the file over:
  `saveRDS(NBDCtoolsData::lst_dds, "lst_dds.rds")`. `load_metadata` reads it.

See [where the metadata comes from](metadata.md#where-the-metadata-comes-from).

## "No installed NBDCtoolsData R package found"

Raised with `source="local"` when none of the searched R libraries holds `NBDCtoolsData`.
Pass the right library with `r_lib_paths`, or use the default `source="auto"` to download
the metadata instead.

## Running out of memory in `load_metadata`

`lst_dds` contains the data dictionary of every release. Loading it needs about 2.6 GB of
free memory. Load it once per session and keep only the release you work with:

```python
dd = load_metadata("lst_dds.rda")["abcd"]["7.0"]
```

## Pure-Python metadata/file issues

- Missing metadata columns in `dd` raise `ValueError`.
- Missing tabulated files raise `FileNotFoundError`.
- No shared identifier columns between join groups raises `ValueError`.

## "Values that are not numbers were read as missing"

A TSV file does not carry column types, so `create_dataset_py` takes them from the data
dictionary. This `UserWarning` appears when a variable that the dictionary types as
`integer` or `double` holds text that is not a number, for example `2.5` in an integer
column. Those values are missing in the result. The warning lists each variable with the
number of rows concerned. Check that the data dictionary belongs to the release the file
is from.

## "Additional variables ... are more finely grained"

`create_dataset_py` emits this `UserWarning` when a table in
`vars_add`/`tables_add` is at a finer grain than anything in `vars`/`tables` —
for example a session-level variable added to a participant-level selection.
The additional selection is not allowed to change the row set, so only the
first value per row is kept and the warning reports how many were dropped.

Move those variables into `vars`/`tables` if you need all of their values. See
[join semantics](pure_python.md#join-semantics).

## "Duplicate rows for ... in ..."

A table used in `vars_add`/`tables_add` has more than one row per identifier
combination, which would multiply the rows of your dataset. This usually means
the data file does not match the grain its `identifier_columns` declare. Check
the file, or request the variables through `vars`/`tables` instead.
