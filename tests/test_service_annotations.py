#!/usr/bin/env python3
"""Every service method must reference model names that actually exist.

The service modules used to star-import the generated models, which hid a
set of names that were never generated at all: three methods raised
NameError the moment they were called, and ten more carried return
annotations naming types that do not exist. Explicit imports surface those
statically; these tests keep them surfaced.
"""

import ast
import pathlib

import pytest

import linepy.models as models

SERVICE_FILES = ["linepy/talk.py", "linepy/square.py", "linepy/sync.py"]
REPO = pathlib.Path(__file__).resolve().parent.parent


def _module_source(path):
    return (REPO / path).read_text()


def _defined_names(tree):
    """Every name bound at module level or inside a function body."""
    bound = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
    return bound


@pytest.mark.parametrize("path", SERVICE_FILES)
def test_return_annotations_name_real_models(path):
    """`-> "SomeResponse"` must name a model, not a type that never existed."""
    tree = ast.parse(_module_source(path))
    known = set(models.__all__)

    unknown = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        returns = node.returns
        if isinstance(returns, ast.Constant) and isinstance(returns.value, str):
            if returns.value not in known:
                unknown.append(f"{node.name} -> {returns.value}")

    assert not unknown, f"{path} annotates non-existent models: {unknown}"


@pytest.mark.parametrize("path", SERVICE_FILES)
def test_no_undefined_names_at_module_scope(path):
    """Anything evaluated at call time must be imported or locally bound."""
    import builtins

    tree = ast.parse(_module_source(path))
    bound = _defined_names(tree) | set(dir(builtins))

    undefined = sorted(
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and node.id not in bound
    )

    assert not undefined, f"{path} uses undefined names: {undefined}"


@pytest.mark.parametrize("path", SERVICE_FILES)
def test_no_star_imports(path):
    """Star imports are what hid the undefined names in the first place."""
    tree = ast.parse(_module_source(path))

    stars = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and any(alias.name == "*" for alias in node.names)
    ]

    assert not stars, f"{path} star-imports {stars}"


@pytest.mark.parametrize(
    "method,response_model",
    [
        # The three that raised NameError when called.
        ("getSquarePopularKeywords", "GetPopularKeywordsResponse"),
        ("unsendSquareMessage", "UnsendMessageResponse"),
        ("getJoinedSquareChatThreads", "GetJoinedSquareChatThreadsResponse"),
    ],
)
def test_repaired_square_methods_resolve_their_response_model(method, response_model):
    tree = ast.parse(_module_source("linepy/square.py"))

    node = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == method
    )
    models_used = [
        ast.unparse(kw.value)
        for kw in ast.walk(node)
        if isinstance(kw, ast.keyword) and kw.arg == "response_model"
    ]

    assert models_used == [response_model]
    assert hasattr(models, response_model)


def test_unsend_square_message_builds_its_request_inline():
    """It used to call SquareServiceStruct.UnsendMessageRequest, which is
    defined nowhere in the codebase."""
    source = _module_source("linepy/square.py")

    assert "SquareServiceStruct" not in source
