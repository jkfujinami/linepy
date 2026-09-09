# -*- coding: utf-8 -*-
"""Cryptography for LINEPY.

* :mod:`~linepy.crypto.primitives` -- AES, RSA, SHA, HKDF, X25519, AES-GCM-SIV
  and xxHash32, all pure Python (see pyproject.toml for why no C extensions).
* :mod:`~linepy.crypto.e2ee` -- LINE's own E2EE protocol on top of them:
  V1/V2 message encryption, key registration and the OBS media key exchange.
"""
