# R wrapper (`create_dataset`)

The R wrapper function `create_dataset` provides a convenient interface for Python users to
create datasets with exactly the [same functionality as the R version](https://software.nbdc-datahub.org/NBDCtools/reference/create_dataset.html).
It runs R in the backend to leverage its data manipulation capabilities,
while providing a Pythonic interface for ease of use. Therefore, an R installation and the R packages are required.
See the [installation guide](../installation.md#r-backed-wrapper) for details on setting up the R environment and dependencies.

## Use the R wrapper

```python
from nbdctools import create_dataset
# Example usage
create_dataset(
    dir_data="/path/to/tabulated/data",
    study="abcd",
    vars=["var1", "var2", "var3"],
    tables=["table1", "table2"],
    release="latest",
)
```

`create_dataset` accepts all the same arguments as the R version and forwards them to `NBDCtools::create_dataset`.
All arguments must be passed by name; positional arguments are not supported.


## Return Modes

`create_dataset` supports four return modes.

```py
create_dataset(..., return_mode="polars_sink")  # default
```

| Mode | Output | Conversion Path | Requirements |
| --- | --- | --- | --- |
| `polars_sink` (default) | Polars DataFrame | R Arrow sink -> Feather -> Polars | R `arrow` |
| `polars` | Polars DataFrame | Direct rpy2 conversion | R + rpy2 |
| `pd` | pandas DataFrame | Direct rpy2 conversion | Python `pandas` |
| `pd_sink` | pandas DataFrame | R Arrow sink -> Feather -> pandas | R `arrow`, Python `pandas`, Python `pyarrow` |

### Practical Guidance

- Use `polars_sink` (the default) for the fastest path to a Polars DataFrame.
- Use `polars` only when sink dependencies are unavailable (see the tradeoffs below).
- Use `pd` or `pd_sink` only when downstream code requires pandas.
- Sink modes fail fast when required dependencies are not available.

Read the [benchmark results guide](benchmark.md) for performance comparisons of these modes.
It is highly recommended to use `*_sink` modes for large datasets due to their superior performance.

### Tradeoffs

- Sink modes write large temporary files, which can be a concern when storage space is limited
  or storage I/O is slow. In such cases, direct rpy2 conversion modes may be more suitable despite their higher memory usage and slower performance.
- If storage is a concern, consider `pd` mode. pandas may be slower than Polars in downstream processing, but its
  rpy2 conversion is more memory efficient and much faster than `polars` mode. You can convert the pandas DataFrame to Polars afterwards if needed, which is generally faster than direct rpy2 conversion to Polars.
- Use `polars` mode only as a last resort, when sink dependencies are unavailable and pandas is not an option. This mode has the worst performance
  and highest memory usage due to the inefficiency of rpy2 conversion to Polars, and it is not recommended for large datasets.