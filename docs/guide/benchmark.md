# Benchmark Results

This page summarizes results from:

- `examples/benchmark_create_dataset_5_methods.py`

## Hardware

- CPU: Intel Core i7-13700H
- RAM: 32 GB DDR5 4800 MHz
- Storage: Samsung SSD 980 PRO

## Benchmark Scope

The benchmark compares these methods:

- `R:create_dataset_direct`: Directly calling `NBDCtools::create_dataset` in R and writing to a temporary Parquet file from a Python subprocess, then reading the Parquet file into Python. This is the baseline for comparison.
- `create_dataset:polars_sink`: Using the `create_dataset` wrapper with `return_mode="polars_sink"`, which writes the dataset to a temporary Parquet file via an R Arrow sink and reads it back into Python as a Polars DataFrame.
- `create_dataset:polars`: Using the `create_dataset` wrapper with `return_mode="polars"`, which directly converts the R dataset to a Polars DataFrame via rpy2.
- `create_dataset:pd`: Using the `create_dataset` wrapper with `return_mode="pd"`, which directly converts the R dataset to a pandas DataFrame via rpy2.
- `create_dataset:pd_sink`: Using the `create_dataset` wrapper with `return_mode="pd_sink"`, which writes the dataset to a temporary Parquet file via an R Arrow sink and reads it back into Python as a pandas DataFrame.
- `create_dataset_py`: Using the pure Python implementation of the `create_dataset_py` function, which builds the dataset directly from tabulated files and metadata without involving R.

## Dataset

```py
TABLES = [
    "sdev_p_vt",
    "covid_p_qtn",
    "mh_y_ksads__bpd",
    "mh_y_sup",
    "fc_y_vs",
    "nc_y_nihtb",
    "ph_y_bld",
    "ph_y_phs",
]

VARS = [
    "ab_g_dyn__design_site",
    "ab_g_dyn__cohort_grade",
    "ab_g_stc__cohort_dob",
]

VARS_ADD = [
    "ab_g_stc__design_id__fam",
    "ab_g_stc__cohort_ethn",
    "ab_g_stc__cohort_sex",
    "ab_g_stc__cohort_acsps",
    "ab_g_dyn__visit_type",
    "ab_g_dyn__visit_age",
    "ab_g_dyn__design_id__school",
    "ab_g_dyn__design_mr__model",
    "ab_g_stc__design_id__fam__gen",
]
```

## Results

| Method | Median (s) | Min (s) |
| --- | ---: | ---: |
| `R:create_dataset_direct` | 7.94 | 7.91 |
| `create_dataset:polars_sink` | 6.05 | 5.68 |
| `create_dataset:polars` | 94.24 | 92.24 |
| `create_dataset:pd` | 13.94 | 13.66 |
| `create_dataset:pd_sink` | 5.63 | 5.61 |
| `create_dataset_py` | 0.60 | 0.60 |

## Notes

- Performance can vary with data location, file format, software versions, and runtime environment.
