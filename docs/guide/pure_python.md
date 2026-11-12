# Pure Python

`create_dataset_py` builds joined datasets directly from tabulated files and metadata,
without an R installation. It covers the join step only: type coercion from the data
dictionary is applied, but labelling, missingness handling and the other
post-processing steps of the [R wrapper](r_wrapper.md) are not.

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

dds = load_metadata("/path/to/lst_dds.rda", progress=False)
dd = dds["abcd"]["7.0"]

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

## Join semantics

Tables are joined on the identifier columns they declare in the data dictionary.
Three levels are in use, and they nest:

| Grain | `identifier_columns` | Example |
| --- | --- | --- |
| participant | `participant_id` | demographics, birth data |
| session | `participant_id \| session_id` | most assessments |
| run | `participant_id \| session_id \| run_id` | some HBCD instruments |

A value from a coarser table is repeated on every finer row it applies to, so a
participant-level variable appears on every session and every run of that
participant. The result holds one row per distinct combination of identifier
columns, and does not depend on the order you list variables or tables in.

### Main and additional selections

- `vars` / `tables` are the **main** selection and determine the row set. Every
  row present in any selected table appears in the result.
- `vars_add` / `tables_add` **annotate** those rows. They never add, remove or
  duplicate a row.
- A variable named in both is taken from the main selection.

### When an additional table is finer than the main selection

A session-level `vars_add` on top of a participant-level selection, or a run-level
one on top of a session-level selection, has more values than there are rows to
put them on. Because the additional selection must not change the row set, one
value per row is kept and the rest are dropped:

- The kept value is the first by the additional table's own identifier columns —
  the earliest session, or the first run. The choice never depends on row order
  within the file.
- The finer identifier columns are **not** added to the result, so the output
  does not look as though it were at the finer grain.
- A `UserWarning` names the tables, the finer identifier columns, and how many
  values were dropped.

To keep every value, request those variables through `vars`/`tables` instead, which
puts the finer grain into the row set.

These semantics match `NBDCtools::join_tabulated()` in the R package called with
`finer_add = "first"`, so the two implementations agree on the same inputs. Note that
the R default, `finer_add = "error"`, raises an error in this case instead.

## Behavior notes

- At least one of `vars` or `tables` must be provided.
- Missing metadata columns raise `ValueError`.
- Missing table files raise `FileNotFoundError`.
- An additional table with more than one row per identifier combination raises
  `ValueError`, rather than silently multiplying rows.
- Type casting is applied from metadata (`type_data` and optional `type_level`).
