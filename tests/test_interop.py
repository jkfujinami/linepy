#!/usr/bin/env python3
"""
Bidirectional E2EE wire-interop tests against 本家 (linejs).

These prove the Python port is wire-compatible with the real linejs code for
the randomized text-message path (random salt/nonce), in both directions:

  * Python encrypts  -> 本家 (Deno) decrypts
  * 本家 (Deno) encrypts -> Python decrypts

Skipped automatically when Deno or the linejs sources are unavailable.
"""

import json
import os
import shutil
import subprocess

import pytest

from linepy.e2ee import E2EE

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTEROP_TS = os.path.join(REPO, "tools", "interop.ts")
DENO_CONFIG = os.path.join(REPO, "resource", "linejs", "deno.json")

deno = shutil.which("deno")
pytestmark = pytest.mark.skipif(
    not deno or not os.path.exists(INTEROP_TS) or not os.path.exists(DENO_CONFIG),
    reason="deno or linejs sources unavailable",
)


class _FakeClient:
    mid = "u-self"
    talk = None
    token_manager = None


def _run_interop(job: dict) -> dict:
    proc = subprocess.run(
        [deno, "run", "--quiet", "--config", DENO_CONFIG,
         "--allow-read", "--allow-env", INTEROP_TS],
        input=json.dumps(job).encode("utf-8"),
        capture_output=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace"))
    return json.loads(proc.stdout.decode("utf-8"))


# Fixed keypairs so failures are reproducible.
_PRIV_S = bytes(range(1, 33))
_PRIV_R = bytes(range(33, 65))


def _e2ee():
    return E2EE(_FakeClient())


def test_python_encrypt_honmoto_decrypt():
    """Python encrypts a text message; 本家 decrypts it."""
    e = _e2ee()
    pub_r = e.public_from_private(_PRIV_R)
    pub_s = e.public_from_private(_PRIV_S)
    to, frm = "u" + "a" * 32, "u" + "b" * 32
    text = "相互運用テスト🌐 interop"
    key_data = e.generate_shared_secret(_PRIV_S, pub_r)
    chunks = e.encrypt_e2ee_text_message(3, 7, key_data, 2, text, to, frm)

    res = _run_interop({
        "op": "decryptV2",
        "to": to, "from": frm,
        "privKey": _PRIV_R.hex(), "pubKey": pub_s.hex(),
        "chunks": [c.hex() for c in chunks],
        "spec": 2, "contentType": 0,
    })
    assert res["text"] == text


def test_honmoto_encrypt_python_decrypt():
    """本家 encrypts a text message; Python decrypts it."""
    e = _e2ee()
    pub_r = e.public_from_private(_PRIV_R)
    pub_s = e.public_from_private(_PRIV_S)
    to, frm = "u" + "c" * 32, "u" + "d" * 32
    text = "逆方向テスト 🔁 reverse"
    key_data = e.generate_shared_secret(_PRIV_S, pub_r)

    res = _run_interop({
        "op": "encryptText",
        "senderKeyId": 3, "receiverKeyId": 7,
        "keyData": key_data.hex(), "spec": 2,
        "text": text, "to": to, "from": frm,
    })
    chunks = [bytes.fromhex(c) for c in res["chunks"]]
    dec = e.decrypt_e2ee_message_v2(to, frm, chunks, _PRIV_R, pub_s, 2, 0)
    assert dec["text"] == text
