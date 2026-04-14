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

## Load Metadata

```python
from nbdctools import load_metadata

dds = load_metadata("./metadata/lst_dds.rds", progress=False)
dd = dds["abcd"]["6.1"]
```

`load_metadata` converts `rds2py` payloads into nested Python structures and Polars DataFrames where applicable.

Currently there are only `abcd` and `hbcd` studies in the metadata, and to find the release of interest one can inspect the keys of the nested dictionaries. For example, `dds["abcd"].keys()` will show all available releases for the ABCD study.