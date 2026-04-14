# Troubleshooting

## `NBDCtoolsRError`

When calling `create_dataset`, R-side failures are wrapped as `NBDCtoolsRError`.
Inspect `exc.r_message` to see the original R error.

## Missing R packages

If sink modes fail, verify these dependencies in your R environment:

- `NBDCtools`
- `NBDCtoolsData`
- `arrow` (required for sink modes)

## R library path issues

If R packages are not found via `rpy2`, export `R_LIBS_USER` before running `uv` commands.

## Pure-Python metadata/file issues

- Missing metadata columns in `dd` raise `ValueError`.
- Missing tabulated files raise `FileNotFoundError`.
- No shared identifier columns between join groups raises `ValueError`.
