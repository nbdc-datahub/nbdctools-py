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

## Pure-Python metadata/file issues

- Missing metadata columns in `dd` raise `ValueError`.
- Missing tabulated files raise `FileNotFoundError`.
- No shared identifier columns between join groups raises `ValueError`.

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
