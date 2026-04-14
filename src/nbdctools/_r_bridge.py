from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from rpy2.robjects import NULL, StrVector
from rpy2.robjects.packages import PackageNotInstalledError, importr
from rpy2.rinterface_lib.embedded import RRuntimeError

from .exceptions import NBDCtoolsRError


def _normalize_value(value: Any) -> Any:
    if value is None:
        return NULL
    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and all(isinstance(item, str) for item in value)
    ):
        return StrVector(value)
    return value


def call_create_dataset(kwargs: Mapping[str, Any]) -> Any:
    """Call NBDCtools::create_dataset with normalized keyword arguments."""
    normalized_kwargs = {key: _normalize_value(val) for key, val in kwargs.items()}

    try:
        pkg = importr("NBDCtools")
    except PackageNotInstalledError as exc:
        raise NBDCtoolsRError(
            "R package 'NBDCtools' is not installed or not visible to rpy2.",
            r_message=str(exc),
        ) from exc

    try:
        return pkg.create_dataset(**normalized_kwargs)
    except RRuntimeError as exc:
        raise NBDCtoolsRError(
            "R call NBDCtools::create_dataset failed. Check the R message for details.",
            r_message=str(exc),
        ) from exc
