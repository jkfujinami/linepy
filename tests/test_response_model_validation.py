#!/usr/bin/env python3
"""
Regression tests for the generic response_model validation bug.

``response_model=List[SomeModel]`` (used by ~40 methods, e.g.
``TalkService.get_e2_ee_public_keys``) crashed with
``AttributeError: type object 'list' has no attribute 'model_validate'``
because ``_validate_response`` called ``response_model.model_validate(data)``
directly -- which only exists on plain BaseModel subclasses, not on typing
generic aliases like ``List[X]``/``Dict[K, V]``. This broke
``E2EE.verify_login_key()`` (and every other List/Dict-returning RPC) right
after every successful login.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

import pytest

from linepy._model_base import ModelBase, model_field
from linepy.services.base import validate_response_model, ServiceBase


@dataclass(kw_only=True)
class _Item(ModelBase):
    key_id: int = model_field(alias="2", default=0)
    key_data: Optional[bytes] = model_field(alias="4", default=None)


def test_list_of_models_with_int_keyed_items():
    """The exact shape that crashed verify_login_key()."""
    raw = [{2: 5, 4: b"AAA"}, {2: 9, 4: b"BBB"}]
    result = validate_response_model(raw, List[_Item])
    assert isinstance(result, list) and len(result) == 2
    assert result[0].key_id == 5 and result[0].key_data == b"AAA"
    assert result[1].key_id == 9


def test_plain_model_still_works():
    result = validate_response_model({2: 42, 4: b"X"}, _Item)
    assert isinstance(result, _Item)
    assert result.key_id == 42


def test_dict_of_models():
    raw = {"u1": {2: 1, 4: b"a"}, "u2": {2: 2, 4: b"b"}}
    result = validate_response_model(raw, Dict[str, _Item])
    assert result["u1"].key_id == 1 and result["u2"].key_id == 2


def test_list_of_str_passthrough():
    result = validate_response_model(["a", "b", "c"], List[str])
    assert result == ["a", "b", "c"]


def test_empty_list():
    assert validate_response_model([], List[_Item]) == []


def test_service_base_validate_response_uses_shared_helper():
    class _Svc(ServiceBase):
        pass

    svc = _Svc(client=None)
    result = svc._validate_response([{2: 1, 4: b"z"}], List[_Item])
    assert isinstance(result, list) and result[0].key_id == 1


def test_verify_login_key_end_to_end_with_real_list_response_model():
    """The concrete scenario reported: verify_login_key() calling
    talk.get_e2_ee_public_keys() (response_model=List[Pb1_C13097n4])."""
    import base64
    import os
    import tempfile

    from linepy.base import BaseClient
    from linepy.models.sync_structs import Pb1_C13097n4

    client = BaseClient(device="DESKTOPWIN", storage=os.path.join(tempfile.mkdtemp(), "s.json"))
    e = client.e2ee
    priv = os.urandom(32)
    pub = e.public_from_private(priv)
    e.save_self_key_data(5, {
        "keyId": 5,
        "privKey": base64.b64encode(priv).decode(),
        "pubKey": base64.b64encode(pub).decode(),
    })

    class _FakeTalk:
        def get_e2_ee_public_keys(self):
            raw = [{2: 5, 4: base64.b64encode(pub).decode()}]
            return validate_response_model(raw, List[Pb1_C13097n4])

    client.talk = _FakeTalk()
    assert e.verify_login_key() is True
