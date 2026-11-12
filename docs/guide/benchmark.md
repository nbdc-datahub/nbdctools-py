# Benchmark Results

## Hardware

- CPU: Intel Core i7-13700H
- RAM: 32 GB DDR5 4800 MHz
- Storage: Samsung SSD 980 PRO

## Benchmark Scope

The benchmark compares these methods:

- `R:create_dataset_direct`: Calling `NBDCtools::create_dataset` in a fresh `Rscript` subprocess. The dataset stays in R and only its dimensions cross the process boundary, so this measures assembly in R with no conversion to Python. It is the baseline the other R-backed rows are compared against.
- `create_dataset:polars_sink`: The `create_dataset` wrapper with `return_mode="polars_sink"`, which writes the dataset to a temporary file via an R Arrow sink and reads it back into Python as a Polars DataFrame.
- `create_dataset:polars`: The wrapper with `return_mode="polars"`, which converts the R dataset to a Polars DataFrame directly through rpy2.
- `create_dataset:pd`: The wrapper with `return_mode="pd"`, which converts the R dataset to a pandas DataFrame directly through rpy2.
- `create_dataset:pd_sink`: The wrapper with `return_mode="pd_sink"`, which writes the dataset to a temporary file via an R Arrow sink and reads it back into Python as a pandas DataFrame.
- `create_dataset_py`: The pure Python `create_dataset_py`, which builds the dataset from tabulated files and metadata without involving R.

## Method

Every timed run executes in its **own operating system process**, so no R
session state is reused between runs. This is not a detail: `NBDCtoolsData`
lazy-loads the data dictionary on first use and caches it for the life of the
session, and R pays further first-call costs for byte-compilation and method
dispatch. Together that is roughly 4.9 seconds per R session on this
workload. Timing repeated calls inside one embedded R session therefore
flatters every method that can reuse it, and penalises the subprocess
baseline, which cannot.

All R-backed methods are called with identical arguments
(`add_labels=False`, `ignore_version_mismatch=True`, `bypass_ram_check=True`),
so the only thing that differs between them is the conversion path. Labels
are off because `create_dataset_py` cannot apply them, which keeps it
comparable to the rest.

**What is timed**: the call that produces the dataset, including the metadata
resolution it performs. For `create_dataset_py` that includes `load_metadata`,
because the R methods pay the equivalent cost inside `create_dataset`.

**What is not timed**: Python interpreter startup. The subprocess baseline
additionally carries about 0.13s of R interpreter startup inside its timed
region, which is inherent to how that method works.

Three timed runs per method, preceded by one untimed run that is discarded.
That run warms the operating system page cache for the data files, which is
shared between processes; the R session it creates is not, which is the point.

## Dataset

ABCD release 7.0, Parquet format. The selection below produces a dataset of
**139,095 rows × 825 columns**, and every method produced exactly that shape.

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
| `R:create_dataset_direct` | 15.58 | 15.46 |
| `create_dataset:polars_sink` | 15.96 | 15.89 |
| `create_dataset:polars` | 172.50 | 172.49 |
| `create_dataset:pd` | 28.60 | 28.48 |
| `create_dataset:pd_sink` | 15.53 | 15.30 |
| `create_dataset_py` | 3.74 | 3.71 |

## What this shows

- **The sink modes are effectively free.** `polars_sink` and `pd_sink` land
  within a few tenths of the R baseline, which does no conversion at all.
  Assembly inside R dominates, and the Arrow round-trip costs almost nothing
  on top of it. If you want the data in Python, a sink mode is the way.
- **`return_mode="polars"` is the one to avoid**, at roughly 11× the sink
  modes. Converting an R data frame to Polars through rpy2 column by column is
  the dominant cost of that path, not the assembly.
- **`return_mode="pd"` sits in between**, about 1.8× the sink modes. rpy2's
  pandas conversion is far better than its Polars conversion, but still much
  worse than going through Arrow.
- **`create_dataset_py` is about 4.2× faster** than the R-backed paths, and
  roughly 2.8s of its 3.74s is `load_metadata` parsing the 14 MB metadata
  file rather than the join itself. It does less, though: it performs the join
  and type casting only, with no labels, value transformations, missingness
  handling or filtering. See [pure Python](pure_python.md) for the full
  comparison of what the two paths cover.

## Notes

- Performance can vary with data location, file format, software versions, and runtime environment.
- These figures were measured on 2026-10-31 with the grain fix present on **both** sides: `NBDCtools` 1.1.2 (which includes the join fix) with `NBDCtoolsData` 6.0.0, and `create_dataset_py` after the equivalent fix. On the same selection the two implementations return identical values in all 823 non-identifier columns across all 139,095 rows.
- `load_metadata` read a 14 MB `lst_dds.rds` saved from `NBDCtoolsData` 6.0.0 with `saveRDS()`.
- Figures published before 2026-10-08 are not comparable and were wrong in two ways. They were recorded on ABCD 6.1 against a pre-fix `create_dataset_py` that silently dropped roughly 41% of the participant-level values it reported. They also timed the four `create_dataset:*` rows in one warm, reused R session while the baseline started cold every time, which made the sink modes look faster than the R call they wrap.
