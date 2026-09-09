# -*- coding: utf-8 -*-
"""
Pure-Python (stdlib-only) replacement for the pydantic v2 subset LINEPY's
generated models used.

Why this exists: pydantic v2's validation core (``pydantic-core``) is a Rust
extension with no iOS wheels and no pure-Python fallback (upstream has
confirmed none is planned). Sandboxed/no-compiler Python environments (e.g.
a-Shell on iOS) can never install it. Every one of LINEPY's ~6000 generated
model classes only ever used a narrow slice of pydantic's API -- plain
fields with a Thrift field-id ``alias``, ``default``/``default_factory``,
``model_validate``, ``model_dump(by_alias=True)``, and (in ~10 places)
``TypeAdapter`` for ``List[X]``/``Dict[K, V]`` responses. No validators, no
constraints, no computed fields, no custom ``ConfigDict`` were ever used.

This module reproduces exactly that slice on top of stdlib
:mod:`dataclasses`, so every generated class becomes a plain
``@dataclass`` -- fully understood natively by every editor/type-checker,
no plugin needed, no Rust anywhere in the stack.

Design notes:
  * Generated files still have ``from __future__ import annotations``, so
    every annotation (including forward references like
    ``Optional["OtherModel"]``) is a *string* at class-body-execution time.
    Real pydantic resolves these lazily (that's what the handful of explicit
    ``model_rebuild()`` calls in square.py are for). We do the same via
    :func:`typing.get_type_hints`, cached per class and invalidated by
    :meth:`ModelBase.model_rebuild`.
  * Thrift-decoded data always already carries correctly-typed leaf values
    (str/int/bytes/bool/float from :mod:`linepy.thrift`), so unlike real
    pydantic there is no type coercion/validation to perform on scalars --
    only *structural* recursion into nested dataclasses/lists/dicts is
    needed to turn raw dicts into the right nested object graph.
"""

from __future__ import annotations

import dataclasses
import sys
import typing
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

T = TypeVar("T")

_MISSING = dataclasses.MISSING


def model_field(alias: str, default: Any = _MISSING, default_factory: Any = _MISSING):
    """``Field(alias=..., default=...)`` equivalent -> a ``dataclasses.field``
    carrying the Thrift field id in ``metadata["alias"]``.

    Mirrors the exact call shape ``tools/generate_models.py`` already emits:
    exactly one of ``default``/``default_factory`` is ever passed.
    """
    kwargs: Dict[str, Any] = {"metadata": {"alias": alias}}
    if default_factory is not _MISSING:
        kwargs["default_factory"] = default_factory
    elif default is not _MISSING:
        kwargs["default"] = default
    else:
        kwargs["default"] = None
    return dataclasses.field(**kwargs)


# ---------------------------------------------------------------------------
# Lazy forward-ref resolution (model_rebuild equivalent)
# ---------------------------------------------------------------------------

_hints_cache: Dict[type, Dict[str, Any]] = {}


def _resolve_hints(cls: type) -> Dict[str, Any]:
    cached = _hints_cache.get(cls)
    if cached is not None:
        return cached
    try:
        module = sys.modules.get(cls.__module__)
        globalns = vars(module) if module else {}
        hints = typing.get_type_hints(cls, globalns=globalns)
    except Exception:
        # A still-undefined forward ref (rare, self/mutually-referencing
        # classes before the whole module finishes loading) -- fall back to
        # no structural knowledge for this field; from_dict/to_dict degrade
        # to passing the raw value through unchanged rather than crashing.
        hints = {}
    _hints_cache[cls] = hints
    return hints


def _unwrap_optional(tp: Any) -> Any:
    """``Optional[X]`` (i.e. ``Union[X, None]``) -> ``X``; anything else
    unchanged. LINEPY's generated models never use non-Optional Unions."""
    if typing.get_origin(tp) is Union:
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return tp


def _coerce_value(field_type: Any, value: Any) -> Any:
    """Structurally recurse into dataclasses/List/Dict; pass everything
    else through unchanged (see module docstring: no scalar coercion)."""
    if value is None or field_type is None:
        return value

    tp = _unwrap_optional(field_type)
    origin = typing.get_origin(tp)

    if origin is list or origin is List:
        (inner,) = typing.get_args(tp) or (Any,)
        if isinstance(value, list):
            return [_coerce_value(inner, item) for item in value]
        return value

    if origin is dict or origin is Dict:
        args = typing.get_args(tp)
        vt = args[1] if len(args) == 2 else Any
        if isinstance(value, dict):
            return {k: _coerce_value(vt, v) for k, v in value.items()}
        return value

    if isinstance(tp, type):
        if dataclasses.is_dataclass(tp):
            if isinstance(value, tp):
                return value
            if isinstance(value, dict):
                return tp.from_dict(value)
            return value
        try:
            import enum

            if issubclass(tp, enum.IntEnum) and isinstance(value, int) and not isinstance(value, tp):
                return tp(value)
        except (TypeError, ValueError):
            pass

    return value


def _dump_value(value: Any, by_alias: bool) -> Any:
    if isinstance(value, ModelBase):
        return value.to_dict(by_alias=by_alias)
    if isinstance(value, list):
        return [_dump_value(v, by_alias) for v in value]
    if isinstance(value, dict):
        return {k: _dump_value(v, by_alias) for k, v in value.items()}
    return value


def _strip_none(data: Any) -> Any:
    """Recursively drop ``None`` values (``exclude_none=True`` equivalent)."""
    if isinstance(data, dict):
        return {k: _strip_none(v) for k, v in data.items() if v is not None}
    if isinstance(data, list):
        return [_strip_none(v) for v in data]
    return data


# ---------------------------------------------------------------------------
# ModelBase mixin
# ---------------------------------------------------------------------------

class ModelBase:
    """Mixin for generated ``@dataclass`` model classes.

    Usage (matches what ``tools/generate_models.py`` emits)::

        @dataclass
        class RSAKeyInfo(ModelBase):
            keynm: str = model_field(alias="1")
    """

    @classmethod
    def from_dict(cls: Type[T], data: Any) -> Optional[T]:
        """``model_validate`` equivalent. Accepts a dict keyed by Thrift
        field-id alias *or* by field name (matching the old
        ``populate_by_name = True`` behaviour), and recursively constructs
        nested dataclass/List/Dict fields."""
        if data is None:
            return None
        if isinstance(data, cls):
            return data
        if not isinstance(data, dict):
            # A bare scalar routed here by a generic caller -- nothing to do.
            return data  # type: ignore[return-value]

        hints = _resolve_hints(cls)
        kwargs: Dict[str, Any] = {}
        for f in dataclasses.fields(cls):
            alias = f.metadata.get("alias")
            if alias is not None and alias in data:
                raw = data[alias]
            elif f.name in data:
                raw = data[f.name]
            else:
                continue  # let the field's default/default_factory apply
            kwargs[f.name] = _coerce_value(hints.get(f.name), raw)
        return cls(**kwargs)

    # Kept as an alias so any code written against the pydantic-era name
    # keeps working verbatim.
    model_validate = from_dict

    def to_dict(self, by_alias: bool = True) -> Dict[str, Any]:
        """``model_dump(by_alias=...)`` equivalent."""
        out: Dict[str, Any] = {}
        for f in dataclasses.fields(self):
            key = f.metadata.get("alias") if by_alias and f.metadata.get("alias") else f.name
            out[key] = _dump_value(getattr(self, f.name), by_alias)
        return out

    def model_dump(self, by_alias: bool = False, **_ignored: Any) -> Dict[str, Any]:
        return self.to_dict(by_alias=by_alias)

    def model_dump_json(self, by_alias: bool = False, indent: Optional[int] = None,
                        exclude_none: bool = False, **_ignored: Any) -> str:
        """``model_dump_json(...)`` equivalent -- JSON-serialize this model
        (recursively, for nested ModelBase/list/dict fields)."""
        import json

        data = self.to_dict(by_alias=by_alias)
        if exclude_none:
            data = _strip_none(data)
        return json.dumps(data, indent=indent, ensure_ascii=False, default=str)

    @classmethod
    def model_rebuild(cls) -> None:
        """Force re-resolution of forward-referenced field types. Needed
        only for the handful of self-/mutually-referencing classes that
        called this explicitly under pydantic (square.py)."""
        _hints_cache.pop(cls, None)
        _resolve_hints(cls)


# ---------------------------------------------------------------------------
# TypeAdapter(...).validate_python(...) equivalent
# ---------------------------------------------------------------------------

def validate_python(tp: Any, data: Any) -> Any:
    """Structural equivalent of ``pydantic.TypeAdapter(tp).validate_python(data)``
    for the shapes LINEPY actually uses: a plain ``ModelBase`` dataclass,
    ``List[X]``, or ``Dict[str, X]`` (each possibly nested)."""
    if data is None:
        return None

    tp = _unwrap_optional(tp)
    origin = typing.get_origin(tp)

    if origin is list or origin is List:
        (inner,) = typing.get_args(tp) or (Any,)
        return [validate_python(inner, item) for item in data]

    if origin is dict or origin is Dict:
        args = typing.get_args(tp)
        vt = args[1] if len(args) == 2 else Any
        return {k: validate_python(vt, v) for k, v in data.items()}

    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        return tp.from_dict(data)

    return data


class TypeAdapter:
    """Drop-in shape-compatible replacement for ``pydantic.TypeAdapter`` --
    only the one method LINEPY calls."""

    def __init__(self, tp: Any):
        self.tp = tp

    def validate_python(self, data: Any) -> Any:
        return validate_python(self.tp, data)
