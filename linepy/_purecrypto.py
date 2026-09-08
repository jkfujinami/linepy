# -*- coding: utf-8 -*-
"""
Pure-Python crypto backend for LINEPY.

Drop-in, API-compatible replacements for the small subset of
``pycryptodome`` (``Crypto.Cipher.AES/PKCS1_v1_5/PKCS1_OAEP``,
``Crypto.Hash.SHA1/SHA256/HMAC``, ``Crypto.PublicKey.RSA``) and
``cryptography`` (X25519, AES-GCM-SIV) actually used by linepy, built only on
top of the stdlib (``hashlib``/``hmac``/``os``) plus ``pyaes`` (a pure-Python,
dependency-free AES block cipher).

Motivation: sandboxed/no-compiler Python environments (e.g. a-Shell on iOS)
cannot build C or Rust extensions, so ``pycryptodome`` and ``cryptography``
can never install there. This module lets ``linepy/e2ee.py``, ``login.py``
and ``legy.py`` keep their existing ``AES.new(...)``/``RSA.construct(...)``
call sites unchanged -- only the import line changes.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac_mod
import os
from typing import Optional, Tuple

import pyaes as _pyaes

__all__ = [
    "AES",
    "SHA1",
    "SHA256",
    "HMAC",
    "RSA",
    "PKCS1_v1_5",
    "PKCS1_OAEP",
    "AESGCMSIV",
    "x25519_scalarmult",
    "x25519_scalarmult_base",
]


# ======================================================================
# AES: ECB / CBC / CTR / GCM, matching pycryptodome's ``Crypto.Cipher.AES``
# call surface used by linepy (no automatic padding anywhere).
# ======================================================================


def _chunk16(data: bytes):
    for i in range(0, len(data), 16):
        yield data[i : i + 16]


def _pad_to_16(b: bytes) -> bytes:
    rem = len(b) % 16
    return b if rem == 0 else b + b"\x00" * (16 - rem)


class _ECBCipher:
    def __init__(self, key: bytes):
        self._mode = _pyaes.AESModeOfOperationECB(key)

    def encrypt(self, data: bytes) -> bytes:
        if len(data) % 16:
            raise ValueError("Data must be block aligned")
        return b"".join(self._mode.encrypt(b) for b in _chunk16(data))

    def decrypt(self, data: bytes) -> bytes:
        if len(data) % 16:
            raise ValueError("Data must be block aligned")
        return b"".join(self._mode.decrypt(b) for b in _chunk16(data))


class _CBCCipher:
    def __init__(self, key: bytes, iv: bytes):
        self._mode = _pyaes.AESModeOfOperationCBC(key, iv=iv)

    def encrypt(self, data: bytes) -> bytes:
        if len(data) % 16:
            raise ValueError("Data must be padded to 16 bytes boundary in CBC mode")
        return b"".join(self._mode.encrypt(b) for b in _chunk16(data))

    def decrypt(self, data: bytes) -> bytes:
        if len(data) % 16:
            raise ValueError("Data must be padded to 16 bytes boundary in CBC mode")
        return b"".join(self._mode.decrypt(b) for b in _chunk16(data))


class _CTRCipher:
    """Matches ``AES.new(key, AES.MODE_CTR, nonce=b"", initial_value=N)``:
    a bare 128-bit big-endian counter, no separate nonce prefix (pyaes'
    ``Counter`` increments the full 128-bit big-endian value, which is
    exactly pycryptodome's semantics for this call form)."""

    def __init__(self, key: bytes, initial_value: int):
        counter = _pyaes.Counter(initial_value=initial_value)
        self._mode = _pyaes.AESModeOfOperationCTR(key, counter=counter)

    def encrypt(self, data: bytes) -> bytes:
        return self._mode.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        return self._mode.decrypt(data)


# ---- GHASH / GCM (NIST SP 800-38D) ----------------------------------

_GHASH_R = 0xE1000000000000000000000000000000  # top-bit-set reduction constant


def _ghash_gf_mult(x: int, y: int) -> int:
    """Multiply two 128-bit integers in GHASH's GF(2^128) (bit 127 = MSB)."""
    z = 0
    v = x
    for i in range(127, -1, -1):
        if (y >> i) & 1:
            z ^= v
        v = (v >> 1) ^ _GHASH_R if v & 1 else v >> 1
    return z


def _ghash(h: int, aad: bytes, ciphertext: bytes) -> bytes:
    y = 0
    for block in _chunk16(_pad_to_16(aad)):
        y = _ghash_gf_mult(y ^ int.from_bytes(block, "big"), h)
    for block in _chunk16(_pad_to_16(ciphertext)):
        y = _ghash_gf_mult(y ^ int.from_bytes(block, "big"), h)
    length_block = (len(aad) * 8).to_bytes(8, "big") + (len(ciphertext) * 8).to_bytes(
        8, "big"
    )
    y = _ghash_gf_mult(y ^ int.from_bytes(length_block, "big"), h)
    return y.to_bytes(16, "big")


def _gcm_j0(h: int, nonce: bytes) -> bytes:
    """Initial counter block J0 (SP 800-38D section 7.1)."""
    if len(nonce) == 12:
        return nonce + b"\x00\x00\x00\x01"
    y = 0
    for block in _chunk16(_pad_to_16(nonce)):
        y = _ghash_gf_mult(y ^ int.from_bytes(block, "big"), h)
    length_block = (0).to_bytes(8, "big") + (len(nonce) * 8).to_bytes(8, "big")
    y = _ghash_gf_mult(y ^ int.from_bytes(length_block, "big"), h)
    return y.to_bytes(16, "big")


class _GCMCipher:
    def __init__(self, key: bytes, nonce: bytes):
        self._key = key
        self._block = _pyaes.AES(key)
        self._h = int.from_bytes(bytes(self._block.encrypt(bytes(16))), "big")
        self._aad = bytearray()
        self._j0 = _gcm_j0(self._h, nonce)

    def update(self, aad: bytes) -> None:
        self._aad += aad

    def _ctr_crypt(self, data: bytes) -> bytes:
        start_counter = (int.from_bytes(self._j0, "big") + 1) & ((1 << 128) - 1)
        counter = _pyaes.Counter(initial_value=start_counter)
        mode = _pyaes.AESModeOfOperationCTR(self._key, counter=counter)
        return mode.encrypt(data)

    def _compute_tag(self, ciphertext: bytes) -> bytes:
        s = _ghash(self._h, bytes(self._aad), ciphertext)
        e_j0 = bytes(self._block.encrypt(self._j0))
        return bytes(a ^ b for a, b in zip(s, e_j0))

    def encrypt_and_digest(self, plaintext: bytes) -> Tuple[bytes, bytes]:
        ct = self._ctr_crypt(plaintext)
        return ct, self._compute_tag(ct)

    def decrypt_and_verify(self, ciphertext: bytes, tag: bytes) -> bytes:
        expected = self._compute_tag(ciphertext)
        if not _hmac_mod.compare_digest(expected, bytes(tag)):
            raise ValueError("MAC check failed")
        return self._ctr_crypt(ciphertext)


class AES:
    MODE_ECB = 1
    MODE_CBC = 2
    MODE_CTR = 3
    MODE_GCM = 4

    @staticmethod
    def new(key, mode, *args, **kwargs):
        key = bytes(key)
        if mode == AES.MODE_ECB:
            return _ECBCipher(key)
        if mode == AES.MODE_CBC:
            iv = args[0] if args else kwargs.get("iv")
            return _CBCCipher(key, bytes(iv))
        if mode == AES.MODE_CTR:
            return _CTRCipher(key, kwargs.get("initial_value", 0))
        if mode == AES.MODE_GCM:
            nonce = kwargs.get("nonce") or os.urandom(12)
            return _GCMCipher(key, bytes(nonce))
        raise ValueError(f"Unsupported AES mode: {mode!r}")


# ======================================================================
# Hashing / HMAC (thin wrappers around stdlib hashlib/hmac, matching the
# pycryptodome ``Crypto.Hash`` call surface used by linepy).
# ======================================================================


class SHA256:
    @staticmethod
    def new(data: bytes = b""):
        return hashlib.sha256(data)


class SHA1:
    @staticmethod
    def new(data: bytes = b""):
        return hashlib.sha1(data)


class HMAC:
    @staticmethod
    def new(key: bytes, msg: bytes = b"", digestmod=None):
        digest_name = "sha1" if digestmod is SHA1 else "sha256"
        return _hmac_mod.new(bytes(key), msg, digest_name)


class SHA256Algorithm:
    """Stand-in for ``cryptography.hazmat.primitives.hashes.SHA256()``."""

    name = "sha256"


class HKDF:
    """HKDF-SHA256 (RFC 5869), matching
    ``cryptography.hazmat.primitives.kdf.hkdf.HKDF(...).derive(ikm)``."""

    def __init__(self, algorithm, length: int, salt: Optional[bytes], info: bytes):
        self._length = length
        self._salt = salt or b"\x00" * 32
        self._info = info or b""

    def derive(self, key_material: bytes) -> bytes:
        prk = _hmac_mod.new(self._salt, bytes(key_material), "sha256").digest()
        okm = b""
        t = b""
        counter = 1
        while len(okm) < self._length:
            t = _hmac_mod.new(
                prk, t + self._info + bytes([counter]), "sha256"
            ).digest()
            okm += t
            counter += 1
        return okm[: self._length]


# ======================================================================
# RSA: PKCS1v1.5 and OAEP *encryption* only (linepy never decrypts with
# its own RSA private key -- these two flows just wrap a plaintext toward
# LINE's servers using their published public key).
# ======================================================================


class _RsaKey:
    def __init__(self, n: int, e: int):
        self.n = n
        self.e = e

    def size_in_bytes(self) -> int:
        return (self.n.bit_length() + 7) // 8


class RSA:
    @staticmethod
    def construct(rsa_components) -> _RsaKey:
        n, e = rsa_components[0], rsa_components[1]
        return _RsaKey(int(n), int(e))

    @staticmethod
    def import_key(key_data) -> _RsaKey:
        n, e = _parse_public_key(key_data)
        return _RsaKey(n, e)


def _der_read_len(data: bytes, pos: int) -> Tuple[int, int]:
    first = data[pos]
    pos += 1
    if first < 0x80:
        return first, pos
    n_bytes = first & 0x7F
    length = int.from_bytes(data[pos : pos + n_bytes], "big")
    return length, pos + n_bytes


def _der_read_tlv(data: bytes, pos: int) -> Tuple[int, bytes, int]:
    tag = data[pos]
    length, pos = _der_read_len(data, pos + 1)
    value = data[pos : pos + length]
    return tag, value, pos + length


def _parse_public_key(key_data) -> Tuple[int, int]:
    """Parse a DER or PEM-encoded RSA public key (SubjectPublicKeyInfo or
    plain RSAPublicKey) into ``(n, e)`` using a tiny hand-rolled DER/ASN.1
    reader -- avoids depending on ``cryptography``/``pyasn1``."""
    if isinstance(key_data, str):
        key_data = key_data.encode("ascii")
    if b"-----BEGIN" in key_data:
        import base64

        b64 = b"".join(
            line
            for line in key_data.splitlines()
            if line and not line.startswith(b"-----")
        )
        der = base64.b64decode(b64)
    else:
        der = key_data

    tag, seq, _ = _der_read_tlv(der, 0)
    if tag != 0x30:
        raise ValueError("Not a DER SEQUENCE")

    # Try RSAPublicKey ::= SEQUENCE { modulus INTEGER, publicExponent INTEGER }
    tag2, first_val, next_pos = _der_read_tlv(seq, 0)
    if tag2 == 0x02:
        n = int.from_bytes(first_val, "big")
        _, e_val, _ = _der_read_tlv(seq, next_pos)
        return n, int.from_bytes(e_val, "big")

    # Otherwise: SubjectPublicKeyInfo ::= SEQUENCE { AlgorithmIdentifier, BIT STRING }
    tag3, bitstring, _ = _der_read_tlv(seq, next_pos)
    if tag3 != 0x03:
        raise ValueError("Expected BIT STRING for SubjectPublicKeyInfo")
    rsa_pub_der = bitstring[1:]  # skip "unused bits" leading byte
    _, rsa_seq, _ = _der_read_tlv(rsa_pub_der, 0)
    _, n_val, next_pos2 = _der_read_tlv(rsa_seq, 0)
    _, e_val, _ = _der_read_tlv(rsa_seq, next_pos2)
    return int.from_bytes(n_val, "big"), int.from_bytes(e_val, "big")


def _i2osp(x: int, size: int) -> bytes:
    return x.to_bytes(size, "big")


def _os2ip(x: bytes) -> int:
    return int.from_bytes(x, "big")


class PKCS1_v1_5:
    """RSAES-PKCS1-v1_5 *encryption* (RFC 8017 section 7.2.1)."""

    def __init__(self, key: _RsaKey):
        self._key = key

    @staticmethod
    def new(key: _RsaKey) -> "PKCS1_v1_5":
        return PKCS1_v1_5(key)

    def encrypt(self, message: bytes) -> bytes:
        k = self._key.size_in_bytes()
        if len(message) > k - 11:
            raise ValueError("Message too long for RSA PKCS1v1.5 encryption")
        ps_len = k - len(message) - 3
        ps = bytearray()
        while len(ps) < ps_len:
            b = os.urandom(1)
            if b != b"\x00":
                ps += b
        em = b"\x00\x02" + bytes(ps) + b"\x00" + message
        c_int = pow(_os2ip(em), self._key.e, self._key.n)
        return _i2osp(c_int, k)


class PKCS1_OAEP:
    """RSAES-OAEP *encryption* (RFC 8017 section 7.1.1), MGF1 with the
    given hash (SHA-1 by default, matching pycryptodome's default)."""

    def __init__(self, key: _RsaKey, hash_module=None):
        self._key = key
        self._hash_module = hash_module or SHA1

    @staticmethod
    def new(key: _RsaKey, hashAlgo=None) -> "PKCS1_OAEP":
        return PKCS1_OAEP(key, hashAlgo)

    def _hash(self, data: bytes) -> bytes:
        return self._hash_module.new(data).digest()

    def _mgf1(self, seed: bytes, mask_len: int) -> bytes:
        out = bytearray()
        counter = 0
        while len(out) < mask_len:
            out += self._hash(seed + counter.to_bytes(4, "big"))
            counter += 1
        return bytes(out[:mask_len])

    def encrypt(self, message: bytes) -> bytes:
        k = self._key.size_in_bytes()
        h_len = len(self._hash(b""))
        if len(message) > k - 2 * h_len - 2:
            raise ValueError("Message too long for RSA OAEP encryption")
        l_hash = self._hash(b"")
        ps = b"\x00" * (k - len(message) - 2 * h_len - 2)
        db = l_hash + ps + b"\x01" + message
        seed = os.urandom(h_len)
        db_mask = self._mgf1(seed, k - h_len - 1)
        masked_db = bytes(a ^ b for a, b in zip(db, db_mask))
        seed_mask = self._mgf1(masked_db, h_len)
        masked_seed = bytes(a ^ b for a, b in zip(seed, seed_mask))
        em = b"\x00" + masked_seed + masked_db
        c_int = pow(_os2ip(em), self._key.e, self._key.n)
        return _i2osp(c_int, k)


# ======================================================================
# X25519 (RFC 7748 Montgomery ladder over GF(2^255 - 19))
# ======================================================================

_P25519 = (1 << 255) - 19
_A24 = 121665  # (486662 - 2) / 4
_BASE_POINT_U = (9).to_bytes(32, "little")


def _decode_u_coordinate(u: bytes) -> int:
    u_list = bytearray(u)
    u_list[31] &= 0x7F  # RFC 7748: mask the top bit of the last byte
    return int.from_bytes(bytes(u_list), "little")


def _decode_scalar(k: bytes) -> int:
    k_list = bytearray(k)
    k_list[0] &= 248
    k_list[31] &= 127
    k_list[31] |= 64
    return int.from_bytes(bytes(k_list), "little")


def _cswap(swap: int, x2: int, x3: int) -> Tuple[int, int]:
    return (x3, x2) if swap else (x2, x3)


def _x25519(k_bytes: bytes, u_bytes: bytes) -> bytes:
    k = _decode_scalar(k_bytes)
    u = _decode_u_coordinate(u_bytes)
    p = _P25519

    x1 = u
    x2, z2 = 1, 0
    x3, z3 = u, 1
    swap = 0

    for t in range(254, -1, -1):
        k_t = (k >> t) & 1
        swap ^= k_t
        x2, x3 = _cswap(swap, x2, x3)
        z2, z3 = _cswap(swap, z2, z3)
        swap = k_t

        a = (x2 + z2) % p
        aa = (a * a) % p
        b = (x2 - z2) % p
        bb = (b * b) % p
        e = (aa - bb) % p
        c = (x3 + z3) % p
        d = (x3 - z3) % p
        da = (d * a) % p
        cb = (c * b) % p
        x3 = pow((da + cb) % p, 2, p)
        z3 = (x1 * pow((da - cb) % p, 2, p)) % p
        x2 = (aa * bb) % p
        z2 = (e * ((aa + _A24 * e) % p)) % p

    x2, x3 = _cswap(swap, x2, x3)
    z2, z3 = _cswap(swap, z2, z3)

    result = (x2 * pow(z2, p - 2, p)) % p
    return result.to_bytes(32, "little")


def x25519_scalarmult(private_key: bytes, public_key: bytes) -> bytes:
    return _x25519(bytes(private_key), bytes(public_key))


def x25519_scalarmult_base(private_key: bytes) -> bytes:
    return _x25519(bytes(private_key), _BASE_POINT_U)


# ======================================================================
# AES-GCM-SIV (RFC 8452) -- used only for decrypting the "secure QR"
# identifier blob. Implements POLYVAL + the RFC 8452 key derivation and
# its little-endian, 32-bit-wraparound AES-CTR variant.
# ======================================================================


_POLYVAL_MOD = (1 << 0) | (1 << 121) | (1 << 126) | (1 << 127) | (1 << 128)
_POLYVAL_INV = (1 << 0) | (1 << 114) | (1 << 121) | (1 << 124) | (1 << 127)


def _polyval_reduce(a: int, m: int) -> int:
    """Reduce ``a`` modulo the (little-endian-bit) polynomial ``m`` by
    long division, per RFC 8452's ``Field.mod``."""
    m2 = m
    shifts = 0
    while m2 < a:
        m2 <<= 1
        shifts += 1
    while shifts >= 0:
        a2 = a ^ m2
        if a2 < a:
            a = a2
        m2 >>= 1
        shifts -= 1
    return a


def _polyval_mul(x: int, y: int) -> int:
    """Carry-less multiply of two 128-bit field elements (bit ``i`` =
    coefficient of x^i, little-endian) then reduce mod x^128+x^127+x^126+x^121+1."""
    res = 0
    for bit in range(128):
        if (y >> bit) & 1:
            res ^= x << bit
    return _polyval_reduce(res, _POLYVAL_MOD)


def _polyval_dot(a: int, b: int) -> int:
    """POLYVAL's ``dot`` product: ``mul(mul(a, b), x^-128)`` -- the extra
    factor is what distinguishes POLYVAL from plain GF(2^128) multiplication
    (it compensates for POLYVAL's little-endian/bit-reversed convention)."""
    return _polyval_mul(_polyval_mul(a, b), _POLYVAL_INV)


def _polyval(h: bytes, blocks) -> bytes:
    h_int = int.from_bytes(h, "little")
    s = 0
    for block in blocks:
        s = _polyval_dot(s ^ int.from_bytes(block, "little"), h_int)
    return s.to_bytes(16, "little")


def _gcmsiv_derive_keys(key: bytes, nonce: bytes) -> Tuple[bytes, bytes]:
    block_cipher = _pyaes.AES(key)
    n_blocks = 6 if len(key) == 32 else 4
    out = bytearray()
    for i in range(n_blocks):
        counter_block = i.to_bytes(4, "little") + nonce
        out += bytes(block_cipher.encrypt(counter_block))[:8]
    record_key = bytes(out[0:16])
    enc_key = bytes(out[16 : 16 + len(key)])
    return record_key, enc_key


def _gcmsiv_ctr(enc_key: bytes, start_block: bytes, data: bytes) -> bytes:
    """RFC 8452's AES-CTR: only the low 32 bits (little-endian) of the
    16-byte counter block increment, modulo 2**32; the rest is fixed."""
    block_cipher = _pyaes.AES(enc_key)
    base = bytearray(start_block)
    base[15] |= 0x80
    low = int.from_bytes(bytes(base[0:4]), "little")
    fixed_tail = bytes(base[4:16])
    out = bytearray()
    for index, chunk in enumerate(_chunk16(data)):
        ctr = (low + index) & 0xFFFFFFFF
        keystream = bytes(block_cipher.encrypt(ctr.to_bytes(4, "little") + fixed_tail))
        out += bytes(a ^ b for a, b in zip(chunk, keystream))
    return bytes(out)


class AESGCMSIV:
    def __init__(self, key: bytes):
        self._key = bytes(key)

    def decrypt(
        self, nonce: bytes, data: bytes, aad: Optional[bytes] = None
    ) -> bytes:
        aad = aad or b""
        nonce = bytes(nonce)
        if len(data) < 16:
            raise ValueError("ciphertext too short for AES-GCM-SIV tag")
        ciphertext, tag = data[:-16], data[-16:]

        record_key, enc_key = _gcmsiv_derive_keys(self._key, nonce)
        plaintext = _gcmsiv_ctr(enc_key, tag, ciphertext)

        blocks = list(_chunk16(_pad_to_16(aad))) + list(_chunk16(_pad_to_16(plaintext)))
        length_block = (len(aad) * 8).to_bytes(8, "little") + (
            len(plaintext) * 8
        ).to_bytes(8, "little")
        blocks.append(length_block)
        s = bytearray(_polyval(record_key, blocks))
        for i in range(12):
            s[i] ^= nonce[i]
        s[15] &= 0x7F

        expected_tag = bytes(_pyaes.AES(enc_key).encrypt(bytes(s)))
        if not _hmac_mod.compare_digest(expected_tag, tag):
            raise ValueError("AES-GCM-SIV tag verification failed")
        return plaintext
