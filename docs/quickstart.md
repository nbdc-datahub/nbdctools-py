# Quickstart

There are two options for using `nbdctools` to create datasets: 

- The R-backed `create_dataset` wrapper, which has full parity with the R `create_dataset` behavior and forwards all extra keyword arguments to `NBDCtools::create_dataset`.
- The pure-Python `create_dataset_py`, which provides metadata-driven joins from tabulated files but only 
  support joining the dataset but does not support further processing steps like variable type coercion, labeling, missingness handling, etc.

Read the [R wrapper guide](guide/r_wrapper.md) and [pure-Python guide](guide/pure_python.md) for more details on each workflow, including practical guidance on choosing between them.

## R-backed wrapper

```python
from nbdctools import NBDCtoolsRError, create_dataset

try:
    df = create_dataset(
        dir_data="/path/to/tabulated/data",
        study="abcd",
        vars=["var1", "var2", "var3"],
        tables=["table1", "table2"],
        release="latest",
    )
    print(df.shape)
except NBDCtoolsRError as exc:
    print(exc)
    print(exc.r_message)
```

## Pure-Python 

```python
from nbdctools import create_dataset_py, load_metadata, download_metadata

# Download metadata only for the first time
download_metadata(type="dds")
# If downloaded or have it already, load into session
dds = load_metadata("lst_dds.rds")
# choose the study and release of interest
dd = dds["abcd"]["6.1"]

df = create_dataset_py(
    dir_data="/path/to/tabulated/data",
    dd=dd,
    tables=["table1", "table2"],
    vars=["var1", "var2", "var3"],
)

print(df.shape)
```
