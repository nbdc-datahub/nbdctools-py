# Metadata Workflow

`nbdctools` provides metadata helpers for download and local loading.

## Download Metadata

```python
from nbdctools import download_metadata

dds_path = download_metadata(type="dds", path="./metadata", progress=True)
levels_path = download_metadata(type="levels", path="./metadata", progress=True)
sessions_path = download_metadata(type="sessions", path="./metadata", progress=True)
```

Supported `type` values:

- `dds`
- `levels`
- `sessions`

The legacy alias `seesions` is accepted for compatibility.

Each call saves one metadata file from the `NBDCtoolsData` R package, by default `lst_<type>.rda`.
R does not need to be installed.

## Where the Metadata Comes From

`download_metadata` can take the metadata from two places, selected with `source`:

| `source` | Takes the metadata from | Use it when |
| --- | --- | --- |
| `"auto"` (default) | r-universe, or an installed `NBDCtoolsData` R package if the download fails | Always, unless one of the cases below applies |
| `"remote"` | r-universe only | You want the latest release or an error, never an older installed copy |
| `"local"` | An installed `NBDCtoolsData` R package only, with no network request | You are offline, or you want the same metadata version your R session uses |

With the default, the same code works with and without internet access. This matters on
systems that block r-universe but ship the R package, such as some containers and
compute clusters:

```python
from nbdctools import download_metadata, load_metadata

download_metadata(type="dds")
dds = load_metadata("lst_dds.rda")
```

r-universe is tried first because it always has the latest release, while an installed
package may be older. The progress messages name the version that was used.

### Installed Packages

An installed `NBDCtoolsData` is looked for in the R libraries of a standard setup:

- the libraries named by `R_LIBS`, `R_LIBS_USER`, `R_LIBS_SITE` and `R_HOME`,
- the default user and system-wide libraries on Linux, macOS and Windows,
- the R library of an active conda environment,
- the renv library of the project in the working directory, renv libraries kept outside a
  project, and the renv package cache.

Packages installed with pak are found as well, since pak installs into R's default library.

If several copies are found, the highest version is used and every copy is listed:

```text
[nbdctools] Found 2 installed copies of NBDCtoolsData:
[nbdctools]   6.0.0 in /home/user/R/x86_64-pc-linux-gnu-library/4.5
[nbdctools]   7.0.0 in /usr/local/lib/R/site-library
[nbdctools] Using NBDCtoolsData 7.0.0 from /usr/local/lib/R/site-library, the highest version.
```

If your R library is somewhere else, pass it with `r_lib_paths`. Only the folders you name
are searched then. R lists its libraries with `.libPaths()`:

```python
download_metadata(
    type="dds",
    source="local",
    r_lib_paths=["/apps/R/4.5.1/lib64/R/library"],
)
```

`r_lib_paths` does not change `source`: with the default `"auto"`, r-universe is still
tried first.

## Load Metadata

```python
from nbdctools import load_metadata

dds = load_metadata("./metadata/lst_dds.rda", progress=False)
dd = dds["abcd"]["6.1"]
```

`load_metadata` returns nested Python dictionaries with a Polars DataFrame per study and release.
Each column has the type it has in R (text, integer, double or logical), an R factor is
returned as its labels, and values that are missing in R (`NA`) are nulls.

Currently there are only `abcd` and `hbcd` studies in the metadata, and to find the release of interest one can inspect the keys of the nested dictionaries. For example, `dds["abcd"].keys()` will show all available releases for the ABCD study.

`lst_dds` holds the data dictionary of every release and is by far the largest file.
Loading the one from `NBDCtoolsData` 7.0.0 takes about 2.6 GB of memory at its peak and
about 1 GB once it has finished.

### File Formats

`load_metadata` reads R data files (`save()`) and single-object files (`saveRDS()`), for example
one saved in R with `saveRDS(NBDCtoolsData::lst_dds, "lst_dds.rds")`. It recognizes the format from
the content of the file, not from its extension.

This matters in one case. A file that `download_metadata` took from an installed package is named
`lst_<type>.rda` like a downloaded one, so that the same code works either way, but it holds the
object as `saveRDS()` writes it. In R, read that file with `readRDS()` rather than `load()`.
