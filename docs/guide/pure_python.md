# Pure Python

`create_dataset_py` builds joined datasets directly from tabulated files and metadata.

## Requirements

The `dd` data dictionary must include:

- `name`
- `table_name`
- `identifier_columns`

Input file formats supported by `format`:

- `parquet`
- `tsv`

## Example

```python
from nbdctools import create_dataset_py, load_metadata

dds = load_metadata("/path/to/lst_dds.rds", progress=False)
dd = dds["abcd"]["6.1"]

df = create_dataset_py(
    dir_data="/path/to/tabulated/data",
    dd=dd,
    tables=["table1", "table2"],
    tables_add=["table3"],
    vars=["var1", "var2", "var3"],
    vars_add=["var4"],
    format="parquet",
    categ_to_factor=True,
    progress=False,
)
```

## Behavior Notes

- At least one of `vars` or `tables` must be provided.
- Missing metadata columns raise `ValueError`.
- Missing table files raise `FileNotFoundError`.
- Type casting is applied from metadata (`type_data` and optional `type_level`).
