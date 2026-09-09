#!/usr/bin/env python3
"""
Tests for linepy._model_base -- the pure-stdlib (dataclasses-based)
replacement for the pydantic v2 subset LINEPY's generated models used.

Covers: alias-keyed / name-keyed construction (populate_by_name parity),
recursive nested-model/List/Dict construction, to_dict(by_alias=...)
round-trips, IntEnum coercion, lazy forward-ref resolution (including
self-referencing classes needing model_rebuild), and the TypeAdapter
equivalent for List[X]/Dict[str, X].
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import IntEnum
from typing import Dict, List, Optional

from linepy._model_base import ModelBase, TypeAdapter, model_field, validate_python


@dataclass
class Inner(ModelBase):
    x: int = model_field(alias="1")
    y: Optional[str] = model_field(alias="2", default=None)


@dataclass
class Outer(ModelBase):
    name: str = model_field(alias="1")
    inner: Optional["Inner"] = model_field(alias="2", default=None)
    items: List["Inner"] = model_field(alias="3", default_factory=list)
    mapping: Dict[str, "Inner"] = model_field(alias="4", default_factory=dict)


class Color(IntEnum):
    RED = 1
    BLUE = 2


@dataclass
class WithEnum(ModelBase):
    color: Optional["Color"] = model_field(alias="1", default=None)


@dataclass
class Node(ModelBase):
    child: Optional["Node"] = model_field(alias="1", default=None)
    value: int = model_field(alias="2", default=0)


# ------------------------------------------------------------------ basics

def test_is_real_dataclass():
    """The whole point: these are genuine stdlib dataclasses, not magic."""
    import dataclasses

    assert dataclasses.is_dataclass(Outer)
    assert {f.name for f in fields(Outer)} == {"name", "inner", "items", "mapping"}


def test_model_field_alias_metadata():
    f = {f.name: f for f in fields(Inner)}
    assert f["x"].metadata["alias"] == "1"
    assert f["y"].metadata["alias"] == "2"
    assert f["y"].default is None


# ------------------------------------------------------------- from_dict

def test_from_dict_alias_keyed():
    o = Outer.from_dict({"1": "hello", "2": {"1": 42, "2": "y-val"}})
    assert o.name == "hello"
    assert isinstance(o.inner, Inner)
    assert o.inner.x == 42 and o.inner.y == "y-val"


def test_from_dict_name_keyed_populate_by_name_parity():
    o = Outer.from_dict({"name": "byname", "inner": {"x": 5}})
    assert o.name == "byname"
    assert o.inner.x == 5


def test_from_dict_recurses_into_list():
    o = Outer.from_dict({"1": "n", "3": [{"1": 1}, {"1": 2}]})
    assert [x.x for x in o.items] == [1, 2]
    assert all(isinstance(x, Inner) for x in o.items)


def test_from_dict_recurses_into_dict():
    o = Outer.from_dict({"1": "n", "4": {"k": {"1": 9}}})
    assert isinstance(o.mapping["k"], Inner)
    assert o.mapping["k"].x == 9


def test_from_dict_missing_fields_use_defaults():
    o = Outer.from_dict({"1": "onlyname"})
    assert o.inner is None
    assert o.items == []
    assert o.mapping == {}


def test_from_dict_passthrough_for_already_constructed_instance():
    o = Outer(name="direct", inner=Inner(x=1))
    assert o.inner.x == 1  # plain dataclass __init__, no from_dict involved


def test_from_dict_idempotent_on_existing_instance():
    inner = Inner(x=1)
    assert Inner.from_dict(inner) is inner


def test_from_dict_none_returns_none():
    assert Outer.from_dict(None) is None


def test_model_validate_is_alias_for_from_dict():
    # Bound classmethod accesses aren't `is`-identical, but must wrap the
    # same underlying function.
    assert Outer.model_validate.__func__ is Outer.from_dict.__func__
    assert Outer.model_validate({"1": "v"}).name == "v"


# ------------------------------------------------------------------ to_dict

def test_to_dict_by_alias_roundtrip():
    o = Outer.from_dict({"1": "hello", "2": {"1": 42, "2": "y-val"},
                         "3": [{"1": 1}], "4": {"k": {"1": 9}}})
    dumped = o.to_dict(by_alias=True)
    assert dumped == {
        "1": "hello",
        "2": {"1": 42, "2": "y-val"},
        "3": [{"1": 1, "2": None}],
        "4": {"k": {"1": 9, "2": None}},
    }


def test_to_dict_by_name():
    o = Inner(x=1, y="z")
    assert o.to_dict(by_alias=False) == {"x": 1, "y": "z"}


def test_model_dump_matches_to_dict():
    o = Inner(x=1, y="z")
    assert o.model_dump(by_alias=True) == o.to_dict(by_alias=True)
    assert o.model_dump(by_alias=False) == o.to_dict(by_alias=False)


# -------------------------------------------------------------------- enum

def test_intenum_coercion_from_int():
    w = WithEnum.from_dict({"1": 2})
    assert w.color is Color.BLUE
    assert isinstance(w.color, Color)


def test_intenum_none_stays_none():
    w = WithEnum.from_dict({})
    assert w.color is None


# --------------------------------------------------------- forward refs

def test_lazy_forward_ref_to_later_defined_class():
    """Early references Later (defined after it in the module) -- must
    resolve correctly since resolution happens at first from_dict() call,
    not at class-body-execution time."""
    e = Outer.from_dict({"1": "x", "2": {"1": 1}})
    assert isinstance(e.inner, Inner)


def test_self_referencing_class():
    n = Node.from_dict({"1": {"2": 5}, "2": 1})
    assert isinstance(n.child, Node)
    assert n.child.value == 5 and n.value == 1


def test_model_rebuild_does_not_raise_and_refreshes_cache():
    Node.model_rebuild()
    n = Node.from_dict({"2": 7})
    assert n.value == 7


# ------------------------------------------------------------ TypeAdapter

def test_type_adapter_list_of_model():
    result = TypeAdapter(List[Inner]).validate_python([{"1": 1}, {"1": 2}])
    assert [x.x for x in result] == [1, 2]
    assert all(isinstance(x, Inner) for x in result)


def test_type_adapter_dict_of_model():
    result = TypeAdapter(Dict[str, Inner]).validate_python({"a": {"1": 7}})
    assert isinstance(result["a"], Inner) and result["a"].x == 7


def test_type_adapter_list_of_scalar_passthrough():
    assert TypeAdapter(List[str]).validate_python(["a", "b"]) == ["a", "b"]


def test_type_adapter_plain_model():
    result = TypeAdapter(Inner).validate_python({"1": 3})
    assert isinstance(result, Inner) and result.x == 3


def test_validate_python_none():
    assert validate_python(List[Inner], None) is None


def test_validate_python_empty_list():
    assert validate_python(List[Inner], []) == []


# ------------------------------------------------------------ model_dump_json

def test_model_dump_json_basic():
    o = Inner(x=1, y="z")
    import json
    assert json.loads(o.model_dump_json()) == {"x": 1, "y": "z"}


def test_model_dump_json_by_alias():
    o = Inner(x=1, y="z")
    import json
    assert json.loads(o.model_dump_json(by_alias=True)) == {"1": 1, "2": "z"}


def test_model_dump_json_exclude_none():
    o = Inner(x=1, y=None)
    import json
    assert json.loads(o.model_dump_json(exclude_none=True)) == {"x": 1}


def test_model_dump_json_indent_is_valid_json():
    o = Outer.from_dict({"1": "hello", "2": {"1": 42}})
    import json
    parsed = json.loads(o.model_dump_json(by_alias=True, indent=2))
    assert parsed["1"] == "hello"
