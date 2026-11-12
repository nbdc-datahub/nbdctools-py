# nbdctools

Python tooling for tabulated data released by the NIH Brain Development Cohorts
(NBDC) Data Hub (ABCD and HBCD), with two entry points:

- `create_dataset`: R-backed wrapper around `NBDCtools::create_dataset`
- `create_dataset_py`: pure-Python dataset assembly, no R installation needed

## Documentation

For installation, workflow guides, API reference, troubleshooting, and benchmarks,
see the documentation website:

- Python package: https://software.nbdc-datahub.org/nbdctools-py/
- R package: https://software.nbdc-datahub.org/NBDCtools/

## Requirements

- Python `>=3.11`

For the R-backed wrapper (`create_dataset`):

- System R on `PATH`
- R packages `NBDCtools` and `NBDCtoolsData`

## Install

From PyPI:

```bash
pip install nbdctools
```

From GitHub:

```bash
pip install "git+https://github.com/nbdc-datahub/nbdctools-py.git"
```

## Citation

If you use this package for your research, please kindly cite the following paper:

> Zhang, L., Das, B., Celhay, O., Smith, C. J., Ziemer, L. R., Dale, A. M., & Linkersdörfer, J. (2026).
> *NBDC Data Tools: Building Analysis-ready Datasets From ABCD and HBCD Releases in R and Python*.
> bioRxiv. https://doi.org/10.64898/2026.11.02.763757

On GitHub, the "Cite this repository" button provides the same reference in
APA and BibTeX formats.

## License

GNU General Public License v3.0 or later (`GPL-3.0-or-later`).
