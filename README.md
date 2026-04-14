# nbdctools

Python tooling for NIH NBDC Data Hub tabulated datasets, with two entry points:

- `create_dataset`: R-backed wrapper around `NBDCtools::create_dataset`
- `create_dataset_py`: pure-Python dataset assembly

## Documentation

For full installation, workflow guides, API reference, troubleshooting, and benchmarks,
use the documentation website:

- Main site: https://software.nbdc-datahub.org/nbdctools-py/
- R package: https://software.nbdc-datahub.org/NBDCtools/
  
## Requirements

- Python `>=3.11`

For the R-backed  (`create_dataset`):

- System R on `PATH`
- R packages `NBDCtools` and `NBDCtoolsData`

## Install

From PyPI:

```bash
pip install nbdctools
```

From source repo:

```bash
pip install "git+https://github.com/nbdc-datahub/nbdctools-py.git"
```

## License

GNU General Public License v3.0 or later (`GPL-3.0-or-later`).

