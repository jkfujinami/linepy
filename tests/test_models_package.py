#!/usr/bin/env python3
"""The linepy.models package: layout, lazy resolution, and re-export surface."""

import subprocess
import sys

import pytest

import linepy.models as models
from linepy.models.base import ModelBase


def test_layers_are_importable():
    import linepy.models.custom.login as login
    import linepy.models.custom.timeline as timeline
    import linepy.models.generated as generated

    assert generated.__name__ == "linepy.models.generated"
    assert login.__name__ == "linepy.models.custom.login"
    assert timeline.__name__ == "linepy.models.custom.timeline"


def test_aggregates_all_three_sources():
    from linepy.models import (
        Chat,  # generated (Thrift)
        PostInfo,  # custom.timeline (VOOM JSON)
        RSAKeyInfo,  # custom.login (login JSON)
    )

    for cls in (Chat, RSAKeyInfo, PostInfo):
        assert issubclass(cls, ModelBase)


def test_base_helpers_are_re_exported():
    from linepy.models import ModelBase as MB
    from linepy.models import TypeAdapter, model_field, validate_python

    assert MB is ModelBase
    assert callable(model_field) and callable(validate_python) and TypeAdapter


def test_all_covers_every_public_model():
    names = set(models.__all__)

    assert {"ModelBase", "model_field", "validate_python", "TypeAdapter"} <= names
    assert {"Chat", "Message", "SquareEvent", "RSAKeyInfo", "PostInfo"} <= names
    # Names the model modules merely imported must not leak into the surface.
    assert names.isdisjoint({"Optional", "List", "Dict", "IntEnum", "dataclass"})
    assert sorted(names) == models.__all__ == dir(models)


def test_unknown_attribute_raises_attribute_error():
    with pytest.raises(AttributeError, match="NoSuchModel"):
        models.NoSuchModel


def test_dunder_probe_does_not_resolve_models():
    """A dunder lookup must not drag in the 3000-class generated module."""
    with pytest.raises(AttributeError):
        models.__wrapped__


def test_importing_linepy_does_not_import_generated():
    """`import linepy` costs ~60 ms only while models stay unresolved."""
    code = (
        "import sys, linepy; "
        "assert 'linepy.models.generated' not in sys.modules, "
        "'generated was imported eagerly'"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_importing_a_model_resolves_generated():
    code = (
        "import sys; from linepy.models import Chat; "
        "assert 'linepy.models.generated' in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_message_status_type_passes_ints_through():
    """MessageStatusType is generated empty, so values stay raw ints.

    models/square.py used to override it with `int`; the override is gone and
    ModelBase's enum coercion falls back to the raw value instead.
    """
    from linepy.models import SquareMessageStatus

    status = SquareMessageStatus.from_dict({"1": "m" + "1" * 32, "3": 2, "5": 17})

    assert status.type_ == 2
    assert status.published_at == 17


@pytest.mark.parametrize(
    "cls_name",
    ["FetchMyEventsResponse", "FetchSquareChatEventsResponse", "SquareEvent",
     "SquareEventPayload"],
)
def test_forward_references_resolve_without_model_rebuild(cls_name):
    """These four needed an explicit model_rebuild() under pydantic.

    ModelBase resolves hints lazily on first use, by which point the module
    is fully loaded, so the explicit calls in the old models/square.py shim
    were dead weight. This pins that they really do resolve on their own.
    """
    import typing

    cls = getattr(models, cls_name)
    hints = typing.get_type_hints(cls)

    assert hints
    assert not any(isinstance(h, str) for h in hints.values())
