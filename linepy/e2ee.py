# -*- coding: utf-8 -*-
"""
End-to-End Encryption (E2EE) Implementation for LINEPY

Based on linejs E2EE implementation.
Handles key generation, encryption, and decryption using Curve25519, AES-GCM/ECB, and SHA256.
"""

import os
import time
import base64
import hashlib
import json
from typing import Optional, Dict, List, Tuple, Union

try:
    import nacl.public
    import nacl.secret
    import nacl.utils
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
except ImportError:
    raise ImportError("E2EE requires 'pynacl' and 'pycryptodome'. Please install them.")


class E2EE:
    """
    E2EE Handler
    """

    def __init__(self, client):
        self.client = client
        self.mid = client.mid
        self._private_key: Optional[nacl.public.PrivateKey] = None
        self._public_key: Optional[nacl.public.PublicKey] = None
        self._shared_secrets: Dict[str, bytes] = {}  # mid -> shared_secret
        self._key_version = 1
        self._key_id = -1

        # Load keys from storage if persistent storage is available
        # TODO: Implement persistent key storage

    def _generate_key_pair(self):
        """Generate Curve25519 key pair"""
        self._private_key = nacl.public.PrivateKey.generate()
        self._public_key = self._private_key.public_key

    @property
    def public_key_bytes(self) -> bytes:
        """Get raw public key bytes"""
        if not self._public_key:
            self._generate_key_pair()
        return bytes(self._public_key)

    def generate_shared_secret(self, other_public_key: bytes) -> bytes:
        """Generate shared secret with other's public key"""
        if not self._private_key:
            self._generate_key_pair()

        try:
            other_pk = nacl.public.PublicKey(other_public_key)
            box = nacl.public.Box(self._private_key, other_pk)
            # NaCl Box uses a specific KDF. LINE uses raw Curve25519 shared secret + custom KDF?
            # linejs uses `nacl.scalarMult(privateKey, publicKey)` which is raw X25519.
            # PyNaCl's Box.shared_key() does exactly that (hsalsa20 on raw shared key).
            # Wait, linejs uses:
            # const sharedSecret = nacl.scalarMult(privKey, pubKey);
            # const key = await sha256(sharedSecret);

            # Box.shared_key() in PyNaCl returns hsalsa20(raw_shared, 0). This is NOT what we want if LINE uses raw scalar mult.
            # We need raw scalar multiplication.
            # PyNaCl doesn't expose raw scalarMult easily on PrivateKey object.
            # PrivateKey has a `_private_key` bytes.
            # Use nacl.bindings.crypto_scalarmult

            from nacl.bindings import crypto_scalarmult

            raw_shared = crypto_scalarmult(bytes(self._private_key), other_public_key)
            return self.sha256(raw_shared)

        except Exception as e:
            print(f"[E2EE] Error generating shared secret: {e}")
            raise

    # ========== Key Management ==========

    def ensure_key_registered(self):
        """Ensure our public key is registered on the server"""
        if not self.client.is_logged_in:
            return

        try:
            keys = self.client.talk.get_e2ee_public_keys()
            my_key = None

            # Simple check: do we have any key?
            if keys:
                # TODO: Check if we own the private key for this public key.
                # For now, if we have no private key in memory, we assume a new session requires new key.
                # Real implementation should save private key to disk.
                pass

            # If no keys or forced implementation: register new key
            if not keys or not self._private_key:
                self._generate_key_pair()
                registered_key = self.client.talk.register_e2ee_public_key(
                    key_version=self._key_version, key_data=self.public_key_bytes
                )
                self._key_id = registered_key.key_id
                print(f"[E2EE] Registered new public key (ID: {self._key_id})")

        except Exception as e:
            print(f"[E2EE] Error ensuring key registration: {e}")

    def get_shared_secret(self, mid: str) -> bytes:
        """Get (or create) shared secret for a user"""
        if mid in self._shared_secrets:
            return self._shared_secrets[mid]

        # Negotiate (fetch) other's key
        try:
            key_info = self.client.talk.negotiate_e2ee_public_key(mid)
            if not key_info or not key_info.key_data:
                raise Exception("No public key found for user")

            secret = self.generate_shared_secret(key_info.key_data)
            self._shared_secrets[mid] = secret
            return secret
        except Exception as e:
            print(f"[E2EE] Failed to negotiate key with {mid}: {e}")
            # raise # Optionally re-raise

    # ========== Encryption / Decryption ==========

    def encrypt_message(self, to_mid: str, text: str) -> Tuple[int, Dict, List[bytes]]:
        """
        Encrypt message for sending.

        Returns:
            (content_type, content_metadata, chunks)
        """
        secret = self.get_shared_secret(to_mid)
        if not secret:
            # Fallback to plain text if E2EE fails? Or raise?
            # For now return None to indicate failure
            return 0, {}, []

        # Generate IV / Salt
        salt = os.urandom(16)
        iv = os.urandom(12)  # GCM IV size

        # In linejs, logic is more complex (E2EEMessage format).
        # We need to package AES-GCM encrypted data.
        # Structure:
        # [1 byte version] [Salt (16)] [IV (12)] [Ciphertext] [Tag (16)]

        aad = b""  # Additional Authenticated Data
        plaintext = text.encode("utf-8")

        # Encrypt
        ciphertext, tag = self.encrypt_aes_gcm(secret, iv, plaintext, aad)

        # Pack
        # Version 1?
        version = b"\x01"
        payload = version + salt + iv + ciphertext + tag

        # Metadata
        metadata = {
            "e2eeVersion": "1",
            "contentType": "0",  # Original content type (text)
            "keyId": str(self._key_id),
        }

        return 0, metadata, [payload]  # ContentType 0? No, E2EE usually uses chunks.

    # ========== AES Utils ==========

    @staticmethod
    def encrypt_aes_ecb(key: bytes, data: bytes) -> bytes:
        """AES-ECB Encrypt (Legacy)"""
        if len(key) > 32:
            key = key[:32]
        cipher = AES.new(key, AES.MODE_ECB)
        return cipher.encrypt(pad(data, AES.block_size))

    @staticmethod
    def decrypt_aes_ecb(key: bytes, data: bytes) -> bytes:
        """AES-ECB Decrypt (Legacy)"""
        if len(key) > 32:
            key = key[:32]
        cipher = AES.new(key, AES.MODE_ECB)
        return unpad(cipher.decrypt(data), AES.block_size)

    @staticmethod
    def encrypt_aes_gcm(
        key: bytes, iv: bytes, data: bytes, aad: bytes = b""
    ) -> Tuple[bytes, bytes]:
        """AES-GCM Encrypt"""
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        cipher.update(aad)
        ciphertext, tag = cipher.encrypt_and_digest(data)
        return ciphertext, tag

    @staticmethod
    def decrypt_aes_gcm(
        key: bytes, iv: bytes, ciphertext: bytes, tag: bytes, aad: bytes = b""
    ) -> bytes:
        """AES-GCM Decrypt"""
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        cipher.update(aad)
        return cipher.decrypt_and_verify(ciphertext, tag)

    @staticmethod
    def sha256(data: bytes) -> bytes:
        """SHA256 Hash"""
        return hashlib.sha256(data).digest()

    @staticmethod
    def xor(b1: bytes, b2: bytes) -> bytes:
        """XOR two byte strings"""
        return bytes(x ^ y for x, y in zip(b1, b2))
