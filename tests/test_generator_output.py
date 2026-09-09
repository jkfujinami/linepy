#!/usr/bin/env python3
"""tools/generate_models.py must emit code that fits the current layout.

The generator is run rarely, so a stale template goes unnoticed until a
regeneration silently reintroduces the old module paths (or the star import
that hid a dozen undefined names). These tests pin the emitted header. They
need no .thrift input: an empty parser still renders it.
"""

import ast
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from generate_models import ThriftParser  # noqa: E402


@pytest.fixture
def parser():
    return ThriftParser([], "unused.py")


def _imports(source):
    """{"..models.generated": {"Chat", ...}} -- ast keeps the dots in `level`."""
    return {
        "." * node.level + (node.module or ""): {a.name for a in node.names}
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }


def test_generated_models_import_modelbase_from_its_new_home(parser):
    source = parser.generate_code()

    assert "from .base import ModelBase, model_field" in source
    assert "_model_base" not in source


def test_generated_service_targets_linepy_services(parser):
    """Default layout: the file lands in linepy/services/, so models are
    two levels up and ServiceBase is a sibling."""
    source = parser.generate_service("TalkService", endpoint="/S4")

    imports = _imports(source)
    assert "..models.generated" in imports or ".base" in imports
    assert imports[".base"] == {"ServiceBase"}
    assert ".services.base" not in imports


def test_models_module_option_moves_both_imports(parser):
    """--models-module also decides where ServiceBase comes from, so the
    generator can still target a file at the package root."""
    source = parser.generate_service(
        "TalkService", endpoint="/S4", models_module=".models.generated"
    )

    imports = _imports(source)
    assert imports[".services.base"] == {"ServiceBase"}


def test_generated_service_never_star_imports(parser):
    source = parser.generate_service("TalkService", endpoint="/S4")

    stars = [
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
        and any(a.name == "*" for a in node.names)
    ]
    assert not stars


def test_generated_service_is_valid_python(parser):
    for module in (None, ".models.generated"):
        kwargs = {"models_module": module} if module else {}
        ast.parse(parser.generate_service("TalkService", endpoint="/S4", **kwargs))


def test_model_names_in_extracts_identifiers():
    names = ThriftParser._model_names_in('Optional[List["SquareEvent"]]')

    assert {"Optional", "List", "SquareEvent"} <= names
