# -*- coding: utf-8 -*-
"""
End-to-End Encryption (E2EE) core engine for LINEPY.

Faithful Python port of linejs
(resource/linejs/packages/linejs/base/e2ee/mod.ts).

LINE's E2EE derives symmetric material from a raw Curve25519 (X25519) shared
secret and SHA-256, *not* from HKDF. Two message generations exist:

* **V1** — AES-256-CBC, key/iv derived as
  ``SHA256(secret, salt, "Key")`` / ``xor(SHA256(secret, salt, "IV"))``.
* **V2** — AES-256-GCM with a 12-byte nonce and an AAD built from the
  sender/receiver MIDs, key ids, spec version and content type.

Media (OBS "E2EE Next") uses HKDF-SHA256 with the info string
``"FileEncryption"`` and AES-256-CTR + HMAC-SHA256, exposed here as
``derive_key_material`` / ``encrypt_by_key_material`` /
``decrypt_by_key_material``.
"""

import json
import os
import struct
from typing import Any, Dict, List, Optional, Tuple

from nacl.bindings import crypto_scalarmult, crypto_scalarmult_base

from Crypto.Cipher import AES
from Crypto.Hash import SHA256, HMAC
import hashlib

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

try:  # AES-GCM-SIV: cryptography >= 42
    from cryptography.hazmat.primitives.ciphers.aead import AESGCMSIV
except Exception:  # pragma: no cover
    AESGCMSIV = None


# MIDType enum (matches LINE): USER=0, ROOM=1, GROUP=2, SQUARE_CHAT etc.
MID_TYPE_USER = 0
MID_TYPE_ROOM = 1
MID_TYPE_GROUP = 2


def get_to_type(mid: str) -> int:
    """Infer a chat's MIDType from its prefix (u/r/c)."""
    if not mid:
        return MID_TYPE_USER
    prefix = mid[0]
    if prefix == "u":
        return MID_TYPE_USER
    if prefix == "r":
        return MID_TYPE_ROOM
    if prefix == "c":
        return MID_TYPE_GROUP
    return MID_TYPE_USER


def _attr(obj, *names, default=None):
    """Read a field from a pydantic model or dict, tolerating alias/int keys."""
    if isinstance(obj, dict):
        for n in names:
            if n in obj:
                return obj[n]
        return default
    for n in names:
        if isinstance(n, str) and hasattr(obj, n):
            return getattr(obj, n)
    return default


def _is_not_found(exc) -> bool:
    """True if an exception looks like a LINE NOT_FOUND error."""
    code = getattr(exc, "code", None)
    if code == "NOT_FOUND":
        return True
    meta = getattr(exc, "metadata", None)
    if isinstance(meta, dict) and meta.get("code") == "NOT_FOUND":
        return True
    return "NOT_FOUND" in str(exc)


def byte2int(t: bytes) -> int:
    """Big-endian byte->int, matching the linejs helper."""
    e = 0
    for b in t:
        e = 256 * e + b
    return e


class E2EE:
    """LINE End-to-End Encryption engine."""

    def __init__(self, client):
        self.client = client

    @property
    def mid(self) -> Optional[str]:
        return getattr(self.client, "mid", None)

    @property
    def token_manager(self):
        return getattr(self.client, "token_manager", None)

    # ==================================================================
    # Pure crypto primitives
    # ==================================================================

    def generate_shared_secret(self, private_key: bytes, public_key: bytes) -> bytes:
        """Raw X25519 shared secret (Curve25519 ``sharedKey``)."""
        return crypto_scalarmult(bytes(private_key), bytes(public_key))

    @staticmethod
    def public_from_private(private_key: bytes) -> bytes:
        """Derive the Curve25519 public key from a private key."""
        return crypto_scalarmult_base(bytes(private_key))

    @staticmethod
    def get_sha256_sum(*args) -> bytes:
        """SHA-256 over the concatenation of the args (str -> utf-8)."""
        h = hashlib.sha256()
        for arg in args:
            if isinstance(arg, str):
                arg = arg.encode("utf-8")
            h.update(bytes(arg))
        return h.digest()

    @staticmethod
    def xor(buf: bytes) -> bytes:
        """Fold a buffer in half by XOR (32B SHA -> 16B IV)."""
        half = len(buf) // 2
        return bytes(buf[i] ^ buf[half + i] for i in range(half))

    @staticmethod
    def get_int_bytes(i: int) -> bytes:
        """Signed 32-bit big-endian encoding (DataView.setInt32)."""
        return struct.pack(">i", int(i) & 0xFFFFFFFF if i >= 0 else int(i))

    def generate_aad(
        self, a: str, b: str, c: int, d: int, e: int = 2, f: int = 0
    ) -> bytes:
        """Build the AAD: senderMid + receiverMid + int32(keyIds/spec/type)."""
        out = bytearray()
        out += a.encode("utf-8") if isinstance(a, str) else bytes(a)
        out += b.encode("utf-8") if isinstance(b, str) else bytes(b)
        out += self.get_int_bytes(c)
        out += self.get_int_bytes(d)
        out += self.get_int_bytes(e)
        out += self.get_int_bytes(f)
        return bytes(out)

    # ---- AES-256-ECB (no padding) -----------------------------------

    @staticmethod
    def encrypt_aes_ecb(aes_key: bytes, plain_data: bytes) -> bytes:
        cipher = AES.new(aes_key, AES.MODE_ECB)
        return cipher.encrypt(plain_data)

    @staticmethod
    def decrypt_aes_ecb(aes_key: bytes, data: bytes) -> bytes:
        cipher = AES.new(aes_key, AES.MODE_ECB)
        return cipher.decrypt(data)

    # ==================================================================
    # Message encryption / decryption
    # ==================================================================

    def encrypt_e2ee_message_v2(
        self, data: bytes, gcm_key: bytes, nonce: bytes, aad: bytes
    ) -> bytes:
        """AES-256-GCM encrypt -> ciphertext || tag(16)."""
        cipher = AES.new(gcm_key, AES.MODE_GCM, nonce=nonce)
        cipher.update(aad)
        ct, tag = cipher.encrypt_and_digest(data)
        return ct + tag

    def decrypt_e2ee_message_v2(
        self,
        to: str,
        _from: str,
        chunks: List[bytes],
        priv_k: bytes,
        pub_k: bytes,
        spec_version: int = 2,
        content_type: int = 0,
    ) -> Dict[str, Any]:
        salt = chunks[0]
        message = chunks[1]
        ciphertext = message[:-16]
        tag = message[-16:]
        nonce = chunks[2]
        sender_key_id = byte2int(chunks[3])
        receiver_key_id = byte2int(chunks[4])
        aes_key = self.generate_shared_secret(priv_k, pub_k)
        gcm_key = self.get_sha256_sum(aes_key, salt, "Key")
        aad = self.generate_aad(
            to, _from, sender_key_id, receiver_key_id, spec_version, content_type
        )
        cipher = AES.new(gcm_key, AES.MODE_GCM, nonce=nonce)
        cipher.update(aad)
        decrypted = cipher.decrypt_and_verify(ciphertext, tag)
        return json.loads(decrypted.decode("utf-8"))

    def decrypt_e2ee_message_v1(
        self, chunks: List[bytes], priv_k: bytes, pub_k: bytes
    ) -> Dict[str, Any]:
        salt = chunks[0]
        message = chunks[1]
        aes_key_raw = self.generate_shared_secret(priv_k, pub_k)
        aes_key = self.get_sha256_sum(aes_key_raw, salt, "Key")
        aes_iv = self.xor(self.get_sha256_sum(aes_key_raw, salt, "IV"))
        cipher = AES.new(aes_key, AES.MODE_CBC, aes_iv)
        decrypted = cipher.decrypt(message)
        # Try PKCS7 unpad; fall back to raw (matches the two-attempt TS logic).
        try:
            pad = decrypted[-1]
            if 0 < pad <= 16 and decrypted[-pad:] == bytes([pad]) * pad:
                decrypted = decrypted[:-pad]
        except Exception:
            pass
        return json.loads(decrypted.decode("utf-8"))

    def encrypt_e2ee_text_message(
        self,
        sender_key_id: int,
        receiver_key_id: int,
        key_data: bytes,
        spec_version: int,
        text,
        to: str,
        _from: str,
    ) -> List[bytes]:
        """Return the 5 chunks: [salt, encData, sign(nonce), sKeyId, rKeyId]."""
        salt = os.urandom(16)
        gcm_key = self.get_sha256_sum(key_data, salt, "Key")
        aad = self.generate_aad(
            to, _from, sender_key_id, receiver_key_id, spec_version, 0
        )
        nonce = os.urandom(12)
        payload = json.dumps({"text": str(text)}, ensure_ascii=False).encode("utf-8")
        enc_data = self.encrypt_e2ee_message_v2(payload, gcm_key, nonce, aad)
        return [
            salt,
            enc_data,
            nonce,
            self.get_int_bytes(sender_key_id),
            self.get_int_bytes(receiver_key_id),
        ]

    def encrypt_e2ee_message_by_data(
        self,
        sender_key_id: int,
        receiver_key_id: int,
        key_data: bytes,
        spec_version: int,
        data: Dict[str, Any],
        to: str,
        _from: str,
        content_type: int = 0,
    ) -> List[bytes]:
        salt = os.urandom(16)
        gcm_key = self.get_sha256_sum(key_data, salt, "Key")
        aad = self.generate_aad(
            to, _from, sender_key_id, receiver_key_id, spec_version, content_type
        )
        nonce = os.urandom(12)
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        enc_data = self.encrypt_e2ee_message_v2(payload, gcm_key, nonce, aad)
        return [
            salt,
            enc_data,
            nonce,
            self.get_int_bytes(sender_key_id),
            self.get_int_bytes(receiver_key_id),
        ]

    # ==================================================================
    # Media key material (OBS "E2EE Next") — HKDF + AES-CTR + HMAC
    # ==================================================================

    @staticmethod
    def derive_key_material(key_material: bytes) -> Tuple[bytes, bytes, bytes]:
        """HKDF-SHA256(info=b"FileEncryption", L=76) -> (encKey, macKey, nonce)."""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=76,
            salt=b"",
            info=b"FileEncryption",
        )
        derived = hkdf.derive(bytes(key_material))
        enc_key = derived[0:32]
        mac_key = derived[32:64]
        nonce = derived[64:76] + b"\x00\x00\x00\x00"  # 16-byte CTR counter
        return enc_key, mac_key, nonce

    @staticmethod
    def _aes_ctr(key: bytes, counter16: bytes, data: bytes) -> bytes:
        initial = int.from_bytes(counter16, "big")
        cipher = AES.new(key, AES.MODE_CTR, nonce=b"", initial_value=initial)
        return cipher.encrypt(data)

    @staticmethod
    def sign_data(data: bytes, key: bytes) -> bytes:
        h = HMAC.new(key, digestmod=SHA256)
        h.update(data)
        return h.digest()

    def encrypt_by_key_material(
        self, raw_data: bytes, key_material: Optional[bytes] = None
    ) -> Dict[str, Any]:
        import base64

        if not key_material:
            key_material = os.urandom(32)
        enc_key, mac_key, nonce = self.derive_key_material(key_material)
        enc_data = self._aes_ctr(enc_key, nonce, raw_data)
        sign = self.sign_data(enc_data, mac_key)
        return {
            "keyMaterial": base64.b64encode(key_material).decode("ascii"),
            "encryptedData": enc_data + sign,
        }

    def decrypt_by_key_material(self, raw_data: bytes, key_material) -> bytes:
        import base64
        import hmac as _hmac

        if isinstance(key_material, str):
            key_material = base64.b64decode(key_material)
        enc_key, mac_key, nonce = self.derive_key_material(key_material)
        if len(raw_data) < 32:
            raise ValueError(
                f"encrypted data too short ({len(raw_data)} bytes) to contain HMAC"
            )
        enc_data = raw_data[:-32]
        sign = raw_data[-32:]
        expected = self.sign_data(enc_data, mac_key)
        if not _hmac.compare_digest(sign, expected):
            raise ValueError(
                "HMAC verification failed: ciphertext tampered or wrong keyMaterial"
            )
        return self._aes_ctr(enc_key, nonce, enc_data)

    # ==================================================================
    # AES-GCM-SIV (secure QR / encrypted identifier)
    # ==================================================================

    def decrypt_aes_gcm_siv(
        self, gcmsiv_key: bytes, nonce: bytes, data: bytes, aad: Optional[bytes] = None
    ) -> bytes:
        if AESGCMSIV is None:
            raise RuntimeError("AES-GCM-SIV requires cryptography>=42")
        return AESGCMSIV(bytes(gcmsiv_key)).decrypt(bytes(nonce), bytes(data), aad)

    def decrypt_encrypted_qr_identifier(
        self, encrypted: bytes, private_key: bytes, public_key: bytes
    ) -> bytes:
        shared = self.generate_shared_secret(private_key, public_key)
        nonce_size = 12
        return self.decrypt_aes_gcm_siv(
            shared, encrypted[:nonce_size], encrypted[nonce_size:]
        )

    # ==================================================================
    # Secure QR / login keychain helpers (Step 4)
    # ==================================================================

    def create_sqr_secret(self, base64_only: bool = False):
        """Create a Curve25519 SQR secret; returns (secretKey, secretPK-or-URL)."""
        import base64
        from urllib.parse import quote

        secret_key = os.urandom(32)
        public_key = self.public_from_private(secret_key)
        pk_b64 = base64.b64encode(public_key).decode("ascii")
        if base64_only:
            return secret_key, pk_b64
        version = 1
        return secret_key, f"?secret={quote(pk_b64, safe='')}&e2eeVersion={version}"

    def decrypt_keychain_raw(
        self, public_key: bytes, private_key: bytes, encrypted_key_chain: bytes
    ) -> bytes:
        """AES-256-CBC(no-pad) decrypt of the login keychain blob -> thrift bytes."""
        shared = self.generate_shared_secret(private_key, public_key)
        aes_key = self.get_sha256_sum(shared, "Key")
        aes_iv = self.xor(self.get_sha256_sum(shared, "IV"))
        cipher = AES.new(aes_key, AES.MODE_CBC, aes_iv)
        return cipher.decrypt(encrypted_key_chain)

    def encrypt_device_secret(
        self, public_key: bytes, private_key: bytes, encrypted_key_chain: bytes
    ) -> bytes:
        """Build the device secret: AES-256-ECB(no-pad) of xor(SHA256(keychain))."""
        shared = self.generate_shared_secret(private_key, public_key)
        aes_key = self.get_sha256_sum(shared, "Key")
        folded = self.xor(self.get_sha256_sum(encrypted_key_chain))
        cipher = AES.new(aes_key, AES.MODE_ECB)
        return cipher.encrypt(folded)

    def decode_e2ee_key_v1(self, data: Dict[str, Any], secret: bytes) -> Optional[Dict[str, Any]]:
        """Decrypt the ``e2eeInfo`` login blob and persist every keychain entry."""
        import base64

        if not data or not data.get("encryptedKeyChain"):
            return None
        encrypted_key_chain = base64.b64decode(data["encryptedKeyChain"])
        key_id = data.get("keyId")
        public_key = base64.b64decode(data["publicKey"])
        e2ee_version = data.get("e2eeVersion")

        entries = self._decrypt_keychain_entries(public_key, secret, encrypted_key_chain)
        selected = next((k for k in entries if str(k["keyId"]) == str(key_id)), None)
        if not selected:
            raise ValueError("Requested keyId is absent from the login keychain")

        for k in entries:
            self.save_self_key_data(
                k["keyId"],
                {
                    "keyId": k["keyId"],
                    "privKey": base64.b64encode(k["privKey"]).decode("ascii"),
                    "pubKey": base64.b64encode(k["pubKey"]).decode("ascii"),
                    "e2eeVersion": e2ee_version,
                },
            )
        return {
            "keyId": key_id,
            "privKey": selected["privKey"],
            "pubKey": selected["pubKey"],
            "e2eeVersion": e2ee_version,
        }

    def _decrypt_keychain_entries(
        self, public_key: bytes, private_key: bytes, encrypted_key_chain: bytes
    ) -> List[Dict[str, Any]]:
        keychain_data = self.decrypt_keychain_raw(
            public_key, private_key, encrypted_key_chain
        )
        entries = self._read_keychain_thrift(keychain_data)
        if not entries:
            raise ValueError("Login keychain is empty or malformed")
        seen = set()
        out: List[Dict[str, Any]] = []
        for entry in entries:
            key_id = entry.get(2)
            if not isinstance(key_id, int) or key_id in seen:
                raise ValueError("Login keychain contains an invalid or duplicate keyId")
            seen.add(key_id)
            pub_key = bytes(entry.get(4))
            priv_key = bytes(entry.get(5))
            if (
                len(priv_key) != 32
                or len(pub_key) != 32
                or not self.verify_e2ee_key_pair(priv_key, pub_key)
            ):
                raise ValueError("Login keychain contains an invalid key pair")
            out.append({"keyId": key_id, "privKey": priv_key, "pubKey": pub_key})
        return out

    @staticmethod
    def _read_keychain_thrift(data: bytes) -> List[Dict[int, Any]]:
        """Parse the decrypted keychain (compact thrift struct) -> entry maps.

        linejs reads this with ``readThriftStruct`` (TCompactProtocol). The
        struct's field 1 holds the list of key entries, each a field map with
        keyId (2), pubKey (4) and privKey (5).
        """
        from .thrift import CompactReader

        parsed = CompactReader(data).read_struct()
        entries = parsed.get(1) if isinstance(parsed, dict) else None
        result: List[Dict[int, Any]] = []
        for entry in entries or []:
            if isinstance(entry, dict):
                result.append(entry)
        return result

    # ==================================================================
    # Self key storage (Step 1.2 backed)
    # ==================================================================

    def save_self_key_data(self, key_id, value: Dict[str, Any]) -> None:
        tm = self.token_manager
        if tm is None:
            return
        tm.save_e2ee_key(int(key_id), value)
        tm.storage.set("e2ee_self_key_id", int(key_id))

    def get_self_key_data_by_key_id(self, key_id) -> Optional[Dict[str, Any]]:
        tm = self.token_manager
        if tm is None:
            return None
        return tm.get_e2ee_key(int(key_id))

    def get_self_key_data(self) -> Optional[Dict[str, Any]]:
        """Return the most recently registered own keypair, if any."""
        tm = self.token_manager
        if tm is None:
            return None
        cur = tm.storage.get("e2ee_self_key_id")
        if cur is not None:
            data = tm.get_e2ee_key(int(cur))
            if data:
                return data
        keys = tm.get_all_e2ee_keys()
        for _, v in keys.items():
            if v and v.get("privKey") and v.get("pubKey"):
                return v
        return None

    # ==================================================================
    # Public-key negotiation & higher-level decryption
    # ==================================================================

    def register_e2ee_key_pair(self) -> Optional[Dict[str, Any]]:
        """Generate a Curve25519 keypair and register the public key."""
        import base64

        priv = os.urandom(32)
        pub = self.public_from_private(priv)
        talk = getattr(self.client, "talk", None)
        key_id = -1
        if talk is not None:
            try:
                from .models.sync_structs import Pb1_C13097n4

                pub_model = Pb1_C13097n4(
                    version=1, key_data=base64.b64encode(pub).decode("ascii")
                )
                seq = 0
                if self.token_manager is not None:
                    seq = self.token_manager.get_next_reqseq("e2ee")
                result = talk.register_e2_ee_public_key(req_seq=seq, public_key=pub_model)
                key_id = getattr(result, "key_id", -1)
            except Exception as exc:  # pragma: no cover - network dependent
                print(f"[E2EE] register_e2ee_public_key failed: {exc}")
        data = {
            "keyId": key_id,
            "privKey": base64.b64encode(priv).decode("ascii"),
            "pubKey": base64.b64encode(pub).decode("ascii"),
        }
        self.save_self_key_data(key_id, data)
        return data

    def encrypt_e2ee_message(self, to: str, data, content_type: int = 0, spec_version: int = 2) -> List[bytes]:
        """High-level: negotiate keys and build E2EE chunks for ``to``.

        Mirrors 本家 ``encryptE2EEMessage``. Returns the 5-chunk list
        [salt, encData, nonce, senderKeyId, receiverKeyId].
        """
        import base64

        _from = self.mid
        self_key = self.get_self_key_data()
        if not self_key:
            self_key = self.register_e2ee_key_pair()
        sender_key_id = self_key["keyId"]

        if get_to_type(to) == MID_TYPE_USER:
            private_key = base64.b64decode(self_key["privKey"])
            receiver_pub = self.get_local_public_key(to, None)
            receiver_key_id = self._last_receiver_key_id
            key_data = self.generate_shared_secret(private_key, receiver_pub)
        else:
            group_priv, receiver_key_id = self._get_group_key(to)
            pub_k = base64.b64decode(self_key["pubKey"])
            key_data = self.generate_shared_secret(group_priv, pub_k)

        if isinstance(data, str):
            return self.encrypt_e2ee_text_message(
                sender_key_id, receiver_key_id, key_data, spec_version, data, to, _from
            )
        return self.encrypt_e2ee_message_by_data(
            sender_key_id, receiver_key_id, key_data, spec_version, data, to, _from, content_type
        )

    _last_receiver_key_id = 0

    def _get_group_key(self, chat_mid: str, requested_key_id=None):
        """Return (group_private_key_bytes, group_key_id) for a group chat.

        Mirrors 本家 ``getE2EELocalPublicKey`` (non-USER branch): checks the
        per-generation cache, otherwise fetches the shared key from the server
        (keyed generation, then last), unwraps it, and — on NOT_FOUND —
        registers a fresh group key.
        """
        import base64

        tm = self.token_manager
        if requested_key_id is not None and tm is not None:
            cached = tm.get_group_key(f"{chat_mid}:{requested_key_id}") or (
                tm.get_group_key(chat_mid)
            )
            if cached and cached.get("privKey") and (
                str(cached.get("keyId")) == str(requested_key_id)
            ):
                return base64.b64decode(cached["privKey"]), cached.get("keyId", 0)

        talk = getattr(self.client, "talk", None)
        if talk is None:
            raise ValueError(
                f"No cached E2EE group key for {chat_mid} and no live session"
            )

        gsk = None
        if requested_key_id is not None:
            try:
                gsk = talk.get_e2_ee_group_shared_key(
                    key_version=2, chat_mid=chat_mid, group_key_id=int(requested_key_id)
                )
            except Exception as exc:
                if not _is_not_found(exc):
                    raise
        if gsk is None:
            try:
                gsk = talk.get_last_e2_ee_group_shared_key(
                    key_version=2, chat_mid=chat_mid
                )
            except Exception as exc:
                if _is_not_found(exc):
                    gsk = self.try_register_e2ee_group_key(chat_mid)
                else:
                    raise
        data = self._unwrap_group_shared_key(chat_mid, gsk)
        return base64.b64decode(data["privKey"]), data["keyId"]

    def _unwrap_group_shared_key(self, chat_mid: str, gsk) -> Dict[str, Any]:
        """ECDH(creatorPub, selfPriv) -> AES-256-CBC decrypt of the wrapped key."""
        import base64

        group_key_id = _attr(gsk, "group_key_id", "groupKeyId", 2)
        creator = _attr(gsk, "creator", 3)
        creator_key_id = _attr(gsk, "creator_key_id", "creatorKeyId", 4)
        receiver_key_id = _attr(gsk, "receiver_key_id", "receiverKeyId", 6)
        encrypted_shared_key = _attr(gsk, "encrypted_shared_key", "encryptedSharedKey", 7)
        if isinstance(encrypted_shared_key, str):
            encrypted_shared_key = base64.b64decode(encrypted_shared_key)
        else:
            encrypted_shared_key = bytes(encrypted_shared_key)

        self_key = self.get_self_key_data_by_key_id(receiver_key_id)
        self_priv = base64.b64decode(self_key["privKey"])
        creator_pub = self.get_local_public_key(creator, creator_key_id)

        aes = self.generate_shared_secret(self_priv, creator_pub)
        aes_key = self.get_sha256_sum(aes, "Key")
        aes_iv = self.xor(self.get_sha256_sum(aes, "IV"))
        plain = AES.new(aes_key, AES.MODE_CBC, aes_iv).decrypt(encrypted_shared_key)
        data = {"privKey": base64.b64encode(plain).decode("ascii"), "keyId": group_key_id}
        tm = self.token_manager
        if tm is not None:
            tm.save_group_key(f"{chat_mid}:{group_key_id}", data)
            tm.save_group_key(chat_mid, data)
        return data

    def try_register_e2ee_group_key(self, chat_mid: str):
        """Register a fresh group shared key encrypted to every member (本家 parity)."""
        import base64

        talk = self.client.talk
        public_keys = talk.get_last_e2_ee_public_keys(chat_mid=chat_mid)
        members: List[str] = []
        key_ids: List[int] = []
        encrypted_shared_keys: List[str] = []

        self_pub_entry = public_keys[self.mid]
        self_key_id = _attr(self_pub_entry, "key_id", "keyId", 2)
        self_key_data = self.get_self_key_data_by_key_id(self_key_id)
        if not self_key_data:
            raise ValueError("E2EE self key not saved; register a key or use E2EE login")
        self_priv = base64.b64decode(self_key_data["privKey"])
        group_priv = os.urandom(32)

        for mid, key in public_keys.items():
            members.append(mid)
            key_id = _attr(key, "key_id", "keyId", 2)
            key_data = _attr(key, "key_data", "keyData", 4)
            key_bytes = base64.b64decode(key_data) if isinstance(key_data, str) else bytes(key_data)
            key_ids.append(key_id)
            aes = self.generate_shared_secret(self_priv, key_bytes)
            aes_key = self.get_sha256_sum(aes, "Key")
            aes_iv = self.xor(self.get_sha256_sum(aes, "IV"))
            enc = AES.new(aes_key, AES.MODE_CBC, aes_iv).encrypt(group_priv)
            encrypted_shared_keys.append(base64.b64encode(enc).decode("ascii"))

        return talk.register_e2_ee_group_key(
            key_version=1,
            chat_mid=chat_mid,
            members=members,
            key_ids=key_ids,
            encrypted_shared_keys=encrypted_shared_keys,
        )

    def get_local_public_key(self, mid: str, key_id=None) -> Optional[bytes]:
        """Fetch (and cache) another user's public key bytes."""
        import base64

        tm = self.token_manager
        cache_key = f"{mid}:{key_id}"
        if tm is not None and key_id is not None:
            cached = tm.get_user_public_key(cache_key)
            if cached and cached.get("key"):
                self._last_receiver_key_id = cached.get("keyId", key_id)
                return base64.b64decode(cached["key"])

        talk = getattr(self.client, "talk", None)
        if talk is None:
            return None
        result = talk.negotiate_e2_ee_public_key(mid=mid)
        if getattr(result, "spec_version", 0) == -1:
            raise ValueError(f"E2EE not supported for {mid}")
        public_key = result.public_key
        recv_key_id = getattr(public_key, "key_id", None)
        key_data = public_key.key_data
        if isinstance(key_data, str):
            key_bytes = base64.b64decode(key_data)
        else:
            key_bytes = bytes(key_data)
        if tm is not None:
            tm.save_user_public_key(
                f"{mid}:{recv_key_id}",
                {"key": base64.b64encode(key_bytes).decode("ascii"), "keyId": recv_key_id},
            )
        self._last_receiver_key_id = recv_key_id if recv_key_id is not None else 0
        return key_bytes

    def verify_e2ee_key_pair(self, priv_key: bytes, registered_pub_key: bytes) -> bool:
        return self.public_from_private(priv_key) == bytes(registered_pub_key)

    def verify_login_key(self) -> bool:
        """Best-effort: verify a stored self key matches a server public key."""
        import base64

        self_key = self.get_self_key_data()
        talk = getattr(self.client, "talk", None)
        if not self_key or talk is None:
            return True
        try:
            priv = base64.b64decode(self_key["privKey"])
            reg_keys = talk.get_e2_ee_public_keys()
            for key in reg_keys or []:
                if str(getattr(key, "key_id", None)) == str(self_key.get("keyId")):
                    kd = key.key_data
                    reg_pub = base64.b64decode(kd) if isinstance(kd, str) else bytes(kd)
                    return self.verify_e2ee_key_pair(priv, reg_pub)
        except Exception as exc:  # pragma: no cover
            print(f"[E2EE] verify_login_key failed: {exc}")
        return True

    def _resolve_and_decrypt(self, message) -> Dict[str, Any]:
        """Shared key-selection + decrypt for text/location/data messages."""
        import base64

        _from = getattr(message, "from_mid", None) or getattr(message, "_from", None) \
            or _msg_attr(message, "from")
        to = _msg_attr(message, "to")
        metadata = _msg_attr(message, "contentMetadata") or {}
        spec_version = str(metadata.get("e2eeVersion", "2"))
        content_type = _content_type_int(_msg_attr(message, "contentType"))
        chunks = _normalize_chunks(_msg_attr(message, "chunks"))

        sender_key_id = byte2int(chunks[3])
        receiver_key_id = byte2int(chunks[4])
        is_self = _from == self.mid

        if get_to_type(to) == MID_TYPE_USER:
            self_key_id = sender_key_id if is_self else receiver_key_id
            self_key = self.get_self_key_data_by_key_id(self_key_id) or self.get_self_key_data()
            priv_k = base64.b64decode(self_key["privKey"])
            pub_k = self.get_local_public_key(
                to if is_self else _from,
                receiver_key_id if is_self else sender_key_id,
            )
        else:
            self_key = self.get_self_key_data()
            group_priv, _gkid = self._get_group_key(to, receiver_key_id)
            priv_k = group_priv
            pub_k = base64.b64decode(self_key["pubKey"])
            if _from != self.mid:
                pub_k = self.get_local_public_key(_from, sender_key_id)

        if spec_version == "2":
            return self.decrypt_e2ee_message_v2(
                to, _from, chunks, priv_k, pub_k, 2, content_type
            )
        return self.decrypt_e2ee_message_v1(chunks, priv_k, pub_k)

    def decrypt_e2ee_text_message(self, message) -> Tuple[str, Dict[str, str]]:
        """Decrypt an incoming E2EE text message object -> (text, metadata)."""
        decrypted = self._resolve_and_decrypt(message)
        text = decrypted.get("text", "") if isinstance(decrypted, dict) else str(decrypted)
        meta: Dict[str, str] = {}
        if isinstance(decrypted, dict):
            for k, v in decrypted.items():
                if k == "text":
                    continue
                meta[k] = v if isinstance(v, str) else json.dumps(v)
        return text, meta

    def decrypt_e2ee_location_message(self, message):
        """Decrypt an incoming E2EE LOCATION message -> the location payload."""
        decrypted = self._resolve_and_decrypt(message)
        return decrypted.get("location") if isinstance(decrypted, dict) else None

    def decrypt_e2ee_data_message(self, message) -> Dict[str, Any]:
        """Decrypt an incoming E2EE media/data message -> {keyMaterial, fileName, ...}."""
        decrypted = self._resolve_and_decrypt(message)
        return decrypted if isinstance(decrypted, dict) else {}

    def decrypt_e2ee_message(self, message):
        """Dispatch decryption based on content type, mutating the message."""
        ctype = _msg_attr(message, "contentType")
        chunks = _msg_attr(message, "chunks")
        if not chunks:
            return message
        if ctype in ("NONE", 0, None):
            text, meta = self.decrypt_e2ee_text_message(message)
            _set_msg_attr(message, "text", text)
            existing = _msg_attr(message, "contentMetadata") or {}
            existing.update(meta)
            _set_msg_attr(message, "contentMetadata", existing)
        return message


# ---------------------------------------------------------------------------
# Message-object helpers (support both pydantic models and dicts)
# ---------------------------------------------------------------------------

def _msg_attr(message, name: str):
    aliases = {
        "from": ("from_mid", "_from", "from_", "from"),
        "to": ("to", "to_mid"),
        "contentMetadata": ("content_metadata", "contentMetadata"),
        "contentType": ("content_type", "contentType"),
        "chunks": ("chunks",),
    }.get(name, (name,))
    if isinstance(message, dict):
        for a in aliases:
            if a in message:
                return message[a]
        return None
    for a in aliases:
        if hasattr(message, a):
            return getattr(message, a)
    return None


def _set_msg_attr(message, name: str, value) -> None:
    target = {
        "text": ("text",),
        "contentMetadata": ("content_metadata", "contentMetadata"),
    }.get(name, (name,))
    if isinstance(message, dict):
        message[target[0]] = value
        return
    for a in target:
        if hasattr(message, a):
            try:
                setattr(message, a, value)
                return
            except Exception:
                pass
    try:
        setattr(message, target[0], value)
    except Exception:
        pass


def _normalize_chunks(chunks) -> List[bytes]:
    out: List[bytes] = []
    for c in chunks or []:
        if isinstance(c, bytes):
            out.append(c)
        elif isinstance(c, str):
            out.append(c.encode("utf-8"))
        else:
            out.append(bytes(c))
    return out


def _content_type_int(ct) -> int:
    if isinstance(ct, int):
        return ct
    names = {
        "NONE": 0, "IMAGE": 1, "VIDEO": 2, "AUDIO": 3, "HTML": 4, "PDF": 5,
        "LOCATION": 15, "STICKER": 7, "FILE": 14,
    }
    return names.get(str(ct), 0)


default = E2EE
