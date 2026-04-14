from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._convert import (
    r_dataframe_to_pandas,
    r_dataframe_to_pandas_sink,
    r_dataframe_to_polars,
    r_dataframe_to_polars_sink,
)
from ._r_bridge import call_create_dataset


_VALID_RETURN_MODES = frozenset(("polars_sink", "pd", "pd_sink", "polars"))


def create_dataset(
    dir_data: str,
    study: str,
    *,
    return_mode: str = "polars_sink",
    **kwargs: Any,
) -> Any:
    """Python wrapper around NBDCtools::create_dataset.

    This function forwards all R arguments to the backend implementation and
    only validates Python-specific return mode behavior.
    """
    if return_mode not in _VALID_RETURN_MODES:
        valid = ", ".join(sorted(_VALID_RETURN_MODES))
        raise ValueError(f"Invalid return_mode={return_mode!r}. Valid values: {valid}")

    forwarded_kwargs: dict[str, Any] = {
        "dir_data": dir_data,
        "study": study,
    }
    if isinstance(kwargs, Mapping):
        forwarded_kwargs.update(kwargs)

    r_df = call_create_dataset(forwarded_kwargs)

    if return_mode == "polars_sink":
        return r_dataframe_to_polars_sink(r_df)
    if return_mode == "polars":
        return r_dataframe_to_polars(r_df)
    if return_mode == "pd":
        return r_dataframe_to_pandas(r_df)
    return r_dataframe_to_pandas_sink(r_df)
