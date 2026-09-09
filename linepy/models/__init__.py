# -*- coding: utf-8 -*-
"""Data models for LINEPY.

Three layers, and only three:

* :mod:`linepy.models.base` -- ``ModelBase``, the stdlib-dataclass stand-in
  for a pydantic ``BaseModel`` (see that module for why LINEPY carries no
  pydantic dependency).
* :mod:`linepy.models.generated` -- every Thrift struct and enum, built from
  ``line.thrift`` + ``chrline.thrift`` by ``tools/generate_models.py``.
  Never edit by hand.
* :mod:`linepy.models.custom` -- hand-written models for the endpoints that
  return real JSON rather than Thrift (login, timeline/VOOM).

This package is the aggregation point: ``from linepy.models import X`` finds
a model wherever it lives.

Resolution is deferred. ``generated`` defines ~3000 dataclasses and costs
~320 ms to import, and Python runs this ``__init__`` whenever *any*
submodule is imported -- so importing it eagerly here would make even
``from linepy.models.base import ModelBase`` pay for the whole Thrift
catalogue. Names are therefore resolved on first attribute access (PEP 562),
while the ``TYPE_CHECKING`` block below keeps every one of them visible to
type checkers, linters and IDEs.
"""

from typing import TYPE_CHECKING, Any, Dict, List

from .base import ModelBase, TypeAdapter, model_field, validate_python

if TYPE_CHECKING:  # pragma: no cover - static analysis only
    from .custom.login import *  # noqa: F401,F403
    from .custom.timeline import *  # noqa: F401,F403
    from .generated import *  # noqa: F401,F403

#: Submodules whose public classes are re-exported from ``linepy.models``.
_SOURCE_MODULES = ("generated", "custom.login", "custom.timeline")

_BASE_EXPORTS = ("ModelBase", "TypeAdapter", "model_field", "validate_python")

_index: Dict[str, Any] = {}


def _build_index() -> Dict[str, Any]:
    """Import the model modules once and map every public name they define."""
    if not _index:
        from importlib import import_module

        for suffix in _SOURCE_MODULES:
            module = import_module(f"{__name__}.{suffix}")
            _index.update(
                {
                    name: value
                    for name, value in vars(module).items()
                    if not name.startswith("_")
                    and getattr(value, "__module__", None) == module.__name__
                }
            )
    return _index


def __getattr__(name: str) -> Any:
    # Never build the index for a dunder probe (copy, pickle, doctest and
    # friends look up plenty of them); only __all__ is worth resolving.
    if name == "__all__":
        return sorted(set(_BASE_EXPORTS) | set(_build_index()))
    if name.startswith("__"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        return _build_index()[name]
    except KeyError:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from None


def __dir__() -> List[str]:
    return __getattr__("__all__")
