# Quickstart

There are two options for using `nbdctools` to create datasets: 

- The R-backed `create_dataset` wrapper, which has full parity with the R `create_dataset` behavior and forwards all extra keyword arguments to `NBDCtools::create_dataset`.
- The pure-Python `create_dataset_py`, which joins tabulated files using the data dictionary and applies its
  variable types, but does not cover further processing steps such as labeling or missingness handling.

Read the [R wrapper guide](guide/r_wrapper.md) and the [pure-Python guide](guide/pure_python.md) for more details on each workflow.

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

# Download the metadata once; it is saved as lst_dds.rda
download_metadata(type="dds")
# Load the downloaded file into the session
dds = load_metadata("lst_dds.rda")
# Choose the study and release of interest
dd = dds["abcd"]["7.0"]

df = create_dataset_py(
    dir_data="/path/to/tabulated/data",
    dd=dd,
    tables=["table1", "table2"],
    vars=["var1", "var2", "var3"],
)

print(df.shape)
```
