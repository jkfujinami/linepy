#!/usr/bin/env python3
"""Package layering.

LINEPY is arranged in layers, and each may only import from the ones below
it. These tests read the import statements out of the source rather than the
loaded modules, so a violation fails even if it happens to work at runtime.

    exceptions / config          (no linepy dependencies at all)
    models                       -> exceptions
    protocol   (thrift, compact, legy)  -> crypto, exceptions
    transport  (http)            -> protocol, exceptions
    crypto     (primitives, e2ee)
    auth       (login, storage)  -> protocol, crypto, models, exceptions
    services / realtime / helpers
    base -> client               (the top)
"""

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
PKG = REPO / "linepy"


def _module_name(path: pathlib.Path) -> str:
    rel = path.relative_to(REPO).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _linepy_imports(path: pathlib.Path):
    """Absolute linepy.* module names this file imports, relative ones resolved."""
    module = _module_name(path)
    package = module.rsplit(".", 1)[0] if "." in module else module
    if path.name == "__init__.py":
        package = module

    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.startswith("linepy"))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - node.level + 1]
                target = ".".join(base + ([node.module] if node.module else []))
            else:
                target = node.module or ""
            if target.startswith("linepy"):
                found.add(target)
    return found


ALL_FILES = sorted(
    p for p in PKG.rglob("*.py") if "__pycache__" not in p.parts
)


def _files_under(*subpackages):
    return [
        p for p in ALL_FILES
        if any(p.relative_to(PKG).parts[0] == s for s in subpackages)
    ]


def _ids(paths):
    return [str(p.relative_to(REPO)) for p in paths]


# ---- expected layout -------------------------------------------------------


@pytest.mark.parametrize(
    "relpath",
    [
        "linepy/exceptions.py",
        "linepy/config.py",
        "linepy/protocol/__init__.py",
        "linepy/protocol/compact.py",
        "linepy/protocol/legy.py",
        "linepy/protocol/thrift/__init__.py",
        "linepy/protocol/thrift/tmc.py",
        "linepy/transport/__init__.py",
        "linepy/transport/http.py",
        "linepy/crypto/__init__.py",
        "linepy/crypto/primitives.py",
        "linepy/crypto/e2ee.py",
        "linepy/auth/__init__.py",
        "linepy/auth/login.py",
        "linepy/auth/storage.py",
        "linepy/models/base.py",
        "linepy/models/generated.py",
        "linepy/models/custom/login.py",
        "linepy/models/custom/timeline.py",
        "linepy/services/__init__.py",
        "linepy/services/base.py",
        "linepy/services/talk.py",
        "linepy/services/square.py",
        "linepy/services/sync.py",
        "linepy/services/auth.py",
        "linepy/services/channel.py",
        "linepy/services/timeline.py",
        "linepy/services/liff.py",
        "linepy/services/voom.py",
        "linepy/services/obs.py",
    ],
)
def test_module_is_where_the_layout_says(relpath):
    assert (REPO / relpath).is_file(), f"{relpath} is missing"


@pytest.mark.parametrize(
    "relpath",
    [
        "linepy/_purecrypto.py",
        "linepy/_model_base.py",
        "linepy/request.py",
        "linepy/legy.py",
        "linepy/compact.py",
        "linepy/e2ee.py",
        "linepy/login.py",
        "linepy/storage.py",
        "linepy/helpers.py",
        "linepy/thrift/__init__.py",
        "linepy/models/_generated.py",
        "linepy/models/talk_structs.py",
        "linepy/models/square_structs.py",
        "linepy/models/sync_structs.py",
        "linepy/talk.py",
        "linepy/square.py",
        "linepy/sync.py",
        "linepy/channel.py",
        "linepy/timeline.py",
        "linepy/liff.py",
        "linepy/voom.py",
        "linepy/obs.py",
    ],
)
def test_old_module_locations_are_gone(relpath):
    assert not (REPO / relpath).exists(), f"{relpath} should have been moved/removed"


# ---- layering --------------------------------------------------------------


@pytest.mark.parametrize("path", _files_under("protocol"), ids=_ids(_files_under("protocol")))
def test_protocol_does_not_depend_on_upper_layers(path):
    """Serialisers must not know about transport, services or the client."""
    forbidden = ("linepy.transport", "linepy.services", "linepy.base",
                 "linepy.client", "linepy.auth", "linepy.push", "linepy.helpers")
    bad = [m for m in _linepy_imports(path) if m.startswith(forbidden)]
    assert not bad, f"{path.name} imports {bad}"


@pytest.mark.parametrize("path", _files_under("crypto"), ids=_ids(_files_under("crypto")))
def test_crypto_does_not_depend_on_transport_or_services(path):
    forbidden = ("linepy.transport", "linepy.services", "linepy.base",
                 "linepy.client", "linepy.helpers")
    bad = [m for m in _linepy_imports(path) if m.startswith(forbidden)]
    assert not bad, f"{path.name} imports {bad}"


@pytest.mark.parametrize("path", _files_under("transport"), ids=_ids(_files_under("transport")))
def test_transport_only_reaches_down_to_protocol(path):
    forbidden = ("linepy.services", "linepy.base", "linepy.client",
                 "linepy.auth", "linepy.helpers", "linepy.models")
    bad = [m for m in _linepy_imports(path) if m.startswith(forbidden)]
    assert not bad, f"{path.name} imports {bad}"


@pytest.mark.parametrize("path", _files_under("models"), ids=_ids(_files_under("models")))
def test_models_depend_on_nothing_but_models(path):
    bad = [
        m for m in _linepy_imports(path)
        if not m.startswith(("linepy.models", "linepy.exceptions"))
    ]
    assert not bad, f"{path.name} imports {bad}"


def test_exceptions_and_config_are_leaves():
    for name in ("exceptions.py", "config.py"):
        assert not _linepy_imports(PKG / name), f"{name} must not import from linepy"


# ---- transport encapsulation ----------------------------------------------


def test_nothing_reaches_into_the_private_httpx_client():
    """OBS/LIFF/VOOM/login used to poke at request._http directly."""
    offenders = [
        str(p.relative_to(REPO))
        for p in ALL_FILES
        if p != PKG / "transport" / "http.py" and "._http" in p.read_text()
    ]
    assert not offenders, f"{offenders} reach into RequestClient._http"


def test_request_client_exposes_plain_http():
    from linepy.transport import RequestClient

    client = RequestClient(device_name="DESKTOPMAC\t1.0\tMAC\t13.0")
    try:
        assert callable(client.get)
        assert callable(client.post)
        assert client.http is client._http
    finally:
        client.close()


# ---- service shapes --------------------------------------------------------


@pytest.mark.parametrize(
    "module_name,class_name",
    [
        ("talk", "TalkService"),
        ("square", "SquareService"),
        ("sync", "SyncService"),
        ("auth", "AuthService"),
        ("channel", "ChannelService"),
        ("timeline", "TimelineService"),
        ("liff", "LiffService"),
        ("voom", "VoomService"),
        ("obs", "ObsService"),
    ],
)
def test_every_service_class_is_named_service(module_name, class_name):
    from importlib import import_module

    module = import_module(f"linepy.services.{module_name}")
    assert hasattr(module, class_name), f"{module_name} has no {class_name}"


@pytest.mark.parametrize(
    "module_name,class_name",
    [
        ("talk", "TalkService"),
        ("square", "SquareService"),
        ("sync", "SyncService"),
        ("auth", "AuthService"),
        ("channel", "ChannelService"),
    ],
)
def test_thrift_services_share_servicebase(module_name, class_name):
    """ChannelService used to carry its own copy of ServiceBase._call."""
    from importlib import import_module

    from linepy.services.base import ServiceBase

    cls = getattr(import_module(f"linepy.services.{module_name}"), class_name)
    assert issubclass(cls, ServiceBase)
    assert "_call" not in vars(cls), f"{class_name} reimplements _call"


def test_base_client_exposes_every_service():
    import os
    import tempfile

    from linepy import BaseClient

    client = BaseClient(
        device="DESKTOPMAC", storage=os.path.join(tempfile.mkdtemp(), "s.json")
    )
    try:
        for attr in ("talk", "square", "sync", "channel", "auth_service",
                     "timeline", "obs", "liff", "voom"):
            assert getattr(client, attr) is not None, attr
            assert type(getattr(client, attr)).__name__.endswith("Service"), attr
    finally:
        client.close()


def test_no_service_creates_its_own_http_client():
    """Services must reuse the transport's pooled client.

    services/timeline.py used to open a fresh httpx.Client for every single
    REST call, so VOOM got no connection reuse at all.
    """
    offenders = [
        str(p.relative_to(REPO))
        for p in _files_under("services")
        if "httpx.Client(" in p.read_text()
    ]
    assert not offenders, f"{offenders} construct their own httpx.Client"
