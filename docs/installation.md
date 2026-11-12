# Installation

## Requirements

### Python

- Tested with Python 3.11 and 3.13.
- `pip` for package installation

## Install from PyPI

```bash
pip install nbdctools
```

## Install from GitHub

```bash
pip install "git+https://github.com/nbdc-datahub/nbdctools-py.git"
```

## R-backed wrapper

### R packages

If you want to use the R-backed `create_dataset` wrapper, which has
full parity with the R `create_dataset` behavior, you need:

- System R available on `PATH`
- R packages: `NBDCtools`, `NBDCtoolsData`, and `arrow` (for the default `polars_sink` return mode)


### R Library Discovery (`R_LIBS_USER`)

If R packages were installed with `renv` and are not discovered by `rpy2`, export `R_LIBS_USER`:

```bash
export R_LIBS_USER=/path/to/your/renv/library
python your_script.py
```

For one-off commands:

```bash
R_LIBS_USER=/path/to/your/renv/library python your_script.py
```

## Development Setup (Contributors)

If you are working from a cloned repository, use `uv`:

```bash
git clone https://github.com/nbdc-datahub/nbdctools-py.git
cd nbdctools-py

uv sync
uv sync --group dev
uv sync --group docs
```
