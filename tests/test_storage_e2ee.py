#!/usr/bin/env python3
"""E2EE key persistence tests for TokenManager (Phase 1 Step 1.2)."""

import os
import tempfile

import pytest

from linepy.storage import FileStorage, MemoryStorage, TokenManager


@pytest.fixture
def tm():
    return TokenManager(MemoryStorage())


def test_e2ee_key_roundtrip(tm):
    tm.save_e2ee_key(5, {"privKey": "aa", "pubKey": "bb", "keyId": 5})
    assert tm.get_e2ee_key(5) == {"privKey": "aa", "pubKey": "bb", "keyId": 5}
    assert tm.get_e2ee_key(999) is None


def test_get_all_e2ee_keys(tm):
    tm.save_e2ee_key(1, {"privKey": "x"})
    tm.save_e2ee_key(2, {"privKey": "y"})
    all_keys = tm.get_all_e2ee_keys()
    assert set(all_keys.keys()) == {"e2ee_key_1", "e2ee_key_2"}


def test_user_public_key_roundtrip(tm):
    tm.save_user_public_key("u123:2", {"key": "cc", "keyId": 2})
    assert tm.get_user_public_key("u123:2")["key"] == "cc"
    assert tm.get_user_public_key("missing") is None


def test_group_key_roundtrip(tm):
    tm.save_group_key("cgroup", {"privKey": "dd", "keyId": 7})
    assert tm.get_group_key("cgroup") == {"privKey": "dd", "keyId": 7}
    assert tm.get_group_key("cother") is None


def test_persistence_across_instances():
    path = os.path.join(tempfile.mkdtemp(), "store.json")
    tm1 = TokenManager(FileStorage(path))
    tm1.save_e2ee_key(3, {"privKey": "persist"})
    tm1.save_user_public_key("u9:1", {"key": "pub"})

    tm2 = TokenManager(FileStorage(path))
    assert tm2.get_e2ee_key(3) == {"privKey": "persist"}
    assert tm2.get_user_public_key("u9:1")["key"] == "pub"
