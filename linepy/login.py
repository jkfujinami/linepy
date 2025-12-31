"""
Login Module for LINEPY

Based on linejs implementation.
Handles various login methods:
- Email/Password login (v1 and v2)
- QR code login
- Token login
"""

import binascii
import hashlib
import os
import base64
import re
from typing import Optional, Tuple, Dict, Any, List

from .thrift import TType
from .config import Device, is_v3_support


# Regex patterns (from linejs)
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PASSWORD_REGEX = re.compile(r"^.{6,}$")  # At least 6 characters


class LoginError(Exception):
    """Login specific error"""
    pass


class Login:
    """
    Login handler for LINE authentication.

    Based on linejs implementation.
    Supports:
    - Email/Password login (with E2EE)
    - QR code login
    - Certificate management
    """

    # Endpoints (from linejs)
    TALK_ENDPOINT = "/api/v3/TalkService.do"
    AUTH_ENDPOINT = "/api/v3p/rs"
    SECONDARY_QR_ENDPOINT = "/acct/lgn/sq/v1"
    SECONDARY_QR_LP_ENDPOINT = "/acct/lp/lgn/sq/v1"
    E2EE_VERIFY_ENDPOINT = "/LF1"
    LEGACY_VERIFY_ENDPOINT = "/Q"

    def __init__(self, client: "BaseClient"):
        self.client = client
        self._cert_cache: Dict[str, str] = {}
        self._qr_cert: Optional[str] = None

    # ========== Certificate Management ==========

    def register_cert(self, email: str, cert: str):
        """Save certificate for future logins"""
        self._cert_cache[f"cert:{email}"] = cert

    def get_cert(self, email: str) -> Optional[str]:
        """Get saved certificate"""
        return self._cert_cache.get(f"cert:{email}")

    def register_qr_cert(self, cert: str):
        """Save QR login certificate"""
        self._qr_cert = cert

    def get_qr_cert(self) -> Optional[str]:
        """Get saved QR certificate"""
        return self._qr_cert

    # ========== RSA Encryption ==========

    def get_rsa_key_info(self, provider: int = 0) -> Dict:
        """
        Get RSA public key for credential encryption.

        Args:
            provider: Identity provider (0=LINE)

        Returns:
            RSA key info with keynm, nvalue, evalue, sessionKey
        """
        # Build request using nested array format (like linejs)
        params = [[12, 1, [[8, 2, provider]]]]

        response = self._request(
            path=self.TALK_ENDPOINT,
            method="getRSAKeyInfo",
            params=params,
            protocol=3,  # Binary
        )

        # Parse response: {1: keynm, 2: nvalue, 3: evalue, 4: sessionKey}
        return {
            "keynm": response.get(1, ""),
            "nvalue": response.get(2, ""),
            "evalue": response.get(3, ""),
            "sessionKey": response.get(4, ""),
        }

    def _encrypt_rsa(self, message: str, nvalue: str, evalue: str) -> str:
        """
        Encrypt message with RSA public key.

        Uses pycryptodome for RSA encryption.
        """
        try:
            from Crypto.PublicKey import RSA
            from Crypto.Cipher import PKCS1_v1_5
        except ImportError:
            raise ImportError("pycryptodome is required for RSA encryption")

        # Convert hex values to integers
        n = int(nvalue, 16)
        e = int(evalue, 16)

        # Create RSA key
        key = RSA.construct((n, e))
        cipher = PKCS1_v1_5.new(key)

        # Encrypt
        encrypted = cipher.encrypt(message.encode("utf-8"))
        return binascii.hexlify(encrypted).decode()

    # ========== E2EE Helpers ==========

    def _create_secret(self) -> Tuple[bytes, str]:
        """
        Create E2EE secret key pair using NaCl box.

        Based on linejs createSqrSecret:
        - Uses nacl.box.keyPair() to generate Curve25519 keys
        - Returns (secretKey, "?secret=<base64_pubkey>&e2eeVersion=1")

        Returns:
            Tuple of (secret_key_bytes, url_params_string)
        """
        try:
            from nacl.public import PrivateKey
        except ImportError:
            raise ImportError("pynacl is required for E2EE. Install with: pip install pynacl")

        # Generate Curve25519 key pair (matching linejs nacl.box.keyPair())
        private_key = PrivateKey.generate()
        public_key = private_key.public_key

        # Encode public key to base64 and URL-encode it
        import urllib.parse
        public_key_b64 = base64.b64encode(bytes(public_key)).decode()
        secret_param = urllib.parse.quote(public_key_b64)
        version = 1

        # Return (secretKey, URL params string)
        return bytes(private_key), f"?secret={secret_param}&e2eeVersion={version}"

    def _sha256(self, *args) -> bytes:
        """Calculate SHA256 hash of concatenated inputs"""
        h = hashlib.sha256()
        for arg in args:
            if isinstance(arg, str):
                arg = arg.encode()
            h.update(arg)
        return h.digest()

    def _encrypt_aes_ecb(self, key: bytes, data: bytes) -> bytes:
        """Encrypt with AES-ECB"""
        try:
            from Crypto.Cipher import AES
        except ImportError:
            raise ImportError("pycryptodome is required")

        cipher = AES.new(key, AES.MODE_ECB)
        return cipher.encrypt(data)

    # ========== Login Methods ==========

    def login_with_token(self, auth_token: str):
        """Login with existing auth token"""
        self.client.set_auth_token(auth_token)

    def login_with_email(
        self,
        email: str,
        password: str,
        pincode: str = "114514",
        e2ee: bool = True,
    ) -> str:
        """
        Login with email and password.

        Based on linejs requestEmailLogin / requestEmailLoginV2.

        Args:
            email: LINE account email
            password: Account password
            pincode: 6-digit PIN code for E2EE verification
            e2ee: Enable E2EE login

        Returns:
            Auth token
        """
        # Validate inputs
        if not EMAIL_REGEX.match(email):
            raise LoginError("Invalid email format")
        if not PASSWORD_REGEX.match(password):
            raise LoginError("Password must be at least 6 characters")
        if len(pincode) != 6:
            raise LoginError("PIN code must be 6 digits")

        print(f"[Login] Email login: {email}")

        # Get RSA key
        rsa_key = self.get_rsa_key_info()
        keynm = rsa_key["keynm"]
        session_key = rsa_key["sessionKey"]

        # Build message: chr(len) + data for each field
        message = (
            chr(len(session_key)) + session_key +
            chr(len(email)) + email +
            chr(len(password)) + password
        )

        # Encrypt with RSA
        encrypted = self._encrypt_rsa(
            message,
            rsa_key["nvalue"],
            rsa_key["evalue"],
        )

        # Prepare E2EE secret if enabled
        secret = None
        secret_data = None
        if e2ee:
            secret, secret_pk = self._create_secret()
            # Encrypt secret with PIN
            pin_hash = self._sha256(pincode)
            secret_data = self._encrypt_aes_ecb(
                pin_hash,
                base64.b64decode(secret_pk),
            )

        # Get saved certificate
        cert = self.get_cert(email)

        # Determine login method based on device
        if is_v3_support(self.client.device):
            return self._request_email_login_v2(
                keynm, encrypted, secret_data, cert, email, secret, pincode
            )
        else:
            return self._request_email_login(
                keynm, encrypted, secret_data, cert, email, secret, e2ee, pincode
            )

    def _request_email_login(
        self,
        keynm: str,
        encrypted: str,
        secret: Optional[bytes],
        cert: Optional[str],
        email: str,
        secret_key: Optional[bytes],
        e2ee: bool,
        pincode: str,
    ) -> str:
        """
        Legacy email login (loginZ).

        Based on linejs requestEmailLogin.
        """
        # Determine login type
        login_type = 2 if secret else 0

        # Build loginV2/loginZ request
        response = self._login_v2(
            keynm=keynm,
            encrypted=encrypted,
            device_name=self.client.system_name,
            verifier=None,
            secret=secret,
            cert=cert,
            method="loginZ",
        )

        # Check if verification needed
        auth_token = response.get(1)  # authToken
        if not auth_token:
            verifier = response.get(3)  # verifier
            pin = response.get(4) or pincode

            print(f"[Login] Enter PIN code: {pin}")
            self.client.emit("pincall", pin)

            if e2ee and secret_key:
                # E2EE verification
                e2ee_info = self._check_e2ee_verification(verifier)
                # TODO: Decrypt E2EE key and create device secret
                e2ee_login = verifier  # Simplified
            else:
                # Legacy verification
                verify_result = self._check_legacy_verification(verifier)
                e2ee_login = verify_result.get("result", {}).get("verifier", verifier)

            # Retry with verifier
            response = self._login_v2(
                keynm=keynm,
                encrypted=encrypted,
                device_name=self.client.system_name,
                verifier=e2ee_login,
                secret=secret,
                cert=cert,
                method="loginZ",
            )
            auth_token = response.get(1)

        # Save certificate
        new_cert = response.get(2)
        if new_cert:
            self.register_cert(email, new_cert)
            print("[Login] Certificate saved")

        if not auth_token:
            raise LoginError("Login failed: no auth token received")

        return auth_token

    def _request_email_login_v2(
        self,
        keynm: str,
        encrypted: str,
        secret: Optional[bytes],
        cert: Optional[str],
        email: str,
        secret_key: Optional[bytes],
        pincode: str,
    ) -> str:
        """
        V2 email login for newer devices.

        Based on linejs requestEmailLoginV2.
        """
        # Build loginV2 request
        response = self._login_v2(
            keynm=keynm,
            encrypted=encrypted,
            device_name=self.client.system_name,
            verifier=None,
            secret=secret,
            cert=cert,
            method="loginV2",
        )

        # Check for v3 token response
        token_info = response.get(9)
        if not token_info:
            verifier = response.get(3)

            print(f"[Login] Enter PIN code: {pincode}")
            self.client.emit("pincall", pincode)

            # E2EE verification (required for v2)
            e2ee_info = self._check_e2ee_verification(verifier)
            # TODO: Full E2EE key exchange
            e2ee_login = verifier  # Simplified

            # Retry with verifier
            response = self._login_v2(
                keynm=keynm,
                encrypted=encrypted,
                device_name=self.client.system_name,
                verifier=e2ee_login,
                secret=secret,
                cert=cert,
                method="loginV2",
            )
            token_info = response.get(9)

        # Save certificate
        new_cert = response.get(2)
        if new_cert:
            self.register_cert(email, new_cert)

        if not token_info:
            raise LoginError("Login failed: no token info")

        auth_token = token_info.get(1)
        # refresh_token = token_info.get(2)

        return auth_token

    def _login_v2(
        self,
        keynm: str,
        encrypted: str,
        device_name: str,
        verifier: Optional[str],
        secret: Optional[bytes],
        cert: Optional[str],
        method: str = "loginV2",
    ) -> Dict:
        """
        Send login request.

        Based on linejs loginV2 implementation.
        """
        # Determine login type
        login_type = 2  # E2EE
        if not secret:
            login_type = 0  # Normal
        if verifier:
            login_type = 1  # Verifier

        # Build params in linejs format: [[type, id, value], ...]
        params = [
            [12, 2, [  # Struct at field 2
                [8, 1, login_type],          # loginType
                [8, 2, 1],                   # identityProvider = LINE
                [11, 3, keynm],              # keynm
                [11, 4, encrypted],          # encryptedMessage
                [2, 5, False],               # keepLoggedIn
                [11, 6, ""],                 # accessLocation
                [11, 7, device_name],        # systemName
                [11, 8, cert or ""],         # certificate
                [11, 9, verifier or ""],     # verifier
                [11, 10, secret or b""],     # secret
                [8, 11, 1],                  # ?
                [11, 12, "System Product Name"],  # modelName
            ]]
        ]

        return self._request(
            path=self.AUTH_ENDPOINT,
            method=method,
            params=params,
            protocol=3,
        )

    def _check_e2ee_verification(self, verifier: str) -> Dict:
        """Check E2EE PIN verification via /LF1 endpoint"""
        import httpx

        headers = {
            "x-line-access": verifier,
            "x-lal": "ja_JP",
            "x-lpv": "1",
            "x-lhm": "GET",
        }

        url = f"https://{self.client.request.HOST}{self.E2EE_VERIFY_ENDPOINT}"
        response = httpx.get(url, headers=headers, timeout=120)
        return response.json().get("result", {})

    def _check_legacy_verification(self, verifier: str) -> Dict:
        """Check legacy PIN verification via /Q endpoint"""
        import httpx

        headers = {
            "x-line-access": verifier,
            "x-lal": "ja_JP",
            "x-lpv": "1",
            "x-lhm": "GET",
        }

        url = f"https://{self.client.request.HOST}{self.LEGACY_VERIFY_ENDPOINT}"
        response = httpx.get(url, headers=headers, timeout=120)
        return response.json()

    # ========== QR Code Login ==========

    def login_with_qr(self, v3: Optional[bool] = None) -> str:
        """
        Login with QR code.

        Args:
            v3: Use v3 login (auto-detected if None)

        Returns:
            Auth token
        """
        if v3 is None:
            v3 = is_v3_support(self.client.device)

        if v3:
            return self._request_sqr2()
        else:
            return self._request_sqr()

    def _request_sqr(self) -> str:
        """QR code login (legacy)"""
        # Create session
        session = self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="createSession",
            params=[],
            protocol=4,
        )
        sqr = session.get(1)

        # Create QR code
        qr_response = self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="createQrCode",
            params=[[12, 1, [[11, 1, sqr]]]],
            protocol=4,
        )
        url = qr_response.get(1)

        # Create secret and append to URL
        secret, secret_url = self._create_secret()
        url = f"{url}{secret_url}"

        print(f"[Login] QR Code URL: {url}")
        self.client.emit("qrcall", url)

        # Wait for QR code verification
        if self._check_qr_verified(sqr):
            # Try certificate verification
            try:
                self._verify_certificate(sqr, self.get_qr_cert())
            except:
                # Need PIN code
                pin_response = self._request(
                    path=self.SECONDARY_QR_ENDPOINT,
                    method="createPinCode",
                    params=[[12, 1, [[11, 1, sqr]]]],
                    protocol=4,
                )
                pincode = pin_response.get(1)
                print(f"[Login] Enter PIN code: {pincode}")
                self.client.emit("pincall", pincode)
                self._check_pin_verified(sqr)

            # QR code login
            response = self._qr_code_login(sqr)

            pem = response.get(1)
            auth_token = response.get(2)

            if pem:
                self.register_qr_cert(pem)

            return auth_token

        raise LoginError("QR code verification timeout")

    def _request_sqr2(self) -> str:
        """QR code login V2"""
        # Similar to _request_sqr but uses qrCodeLoginV2
        # Create session
        session = self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="createSession",
            params=[],
            protocol=4,
        )
        sqr = session.get(1)

        # Create QR code
        qr_response = self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="createQrCode",
            params=[[12, 1, [[11, 1, sqr]]]],
            protocol=4,
        )
        url = qr_response.get(1)

        secret, secret_url = self._create_secret()
        url = f"{url}{secret_url}"

        print(f"[Login] QR Code URL: {url}")
        self.client.emit("qrcall", url)

        if self._check_qr_verified(sqr):
            try:
                self._verify_certificate(sqr, self.get_qr_cert())
            except:
                pin_response = self._request(
                    path=self.SECONDARY_QR_ENDPOINT,
                    method="createPinCode",
                    params=[[12, 1, [[11, 1, sqr]]]],
                    protocol=4,
                )
                pincode = pin_response.get(1)
                print(f"[Login] Enter PIN code: {pincode}")
                self.client.emit("pincall", pincode)
                self._check_pin_verified(sqr)

            # V2 login
            response = self._qr_code_login_v2(sqr)

            # Save response for storage
            self._last_login_response = response

            print(f"[DEBUG] qrCodeLoginV2 response: {response}")

            pem = response.get(1)
            token_info = response.get(3)

            if pem:
                self.register_qr_cert(pem)

            if not token_info:
                raise LoginError("No token info in response")

            auth_token = token_info.get(1)
            if not auth_token:
                raise LoginError("No auth token in token info")

            return auth_token

        raise LoginError("QR code verification timeout")

    def _check_qr_verified(self, sqr: str) -> bool:
        """Wait for QR code verification"""
        import time
        start_time = time.time()

        while time.time() - start_time < 180:
            try:
                self._request(
                    path=self.SECONDARY_QR_LP_ENDPOINT,
                    method="checkQrCodeVerified",
                    params=[[12, 1, [[11, 1, sqr]]]],
                    protocol=4,
                    timeout=30,  # Short timeout for polling loop
                    extra_headers={
                        "x-lst": "180000",
                        "x-line-access": sqr,
                    },
                )
                return True
            except Exception as e:
                # If timeout, retry. If other error, stop.
                if "timed out" in str(e):
                    continue
                print(f"[Login] QR verification failed: {e}")

                # Check for specific thrift errors?
                # For now, just retry on timeout
                time.sleep(1)

        return False

    def _check_pin_verified(self, sqr: str) -> bool:
        """Wait for PIN code verification"""
        import time
        start_time = time.time()

        while time.time() - start_time < 180:
            try:
                self._request(
                    path=self.SECONDARY_QR_LP_ENDPOINT,
                    method="checkPinCodeVerified",
                    params=[[12, 1, [[11, 1, sqr]]]],
                    protocol=4,
                    timeout=30,
                    extra_headers={
                        "x-lst": "180000",
                        "x-line-access": sqr,
                    },
                )
                return True
            except Exception as e:
                if "timed out" in str(e):
                    continue
                print(f"[Login] PIN verification failed: {e}")
                time.sleep(1)

        return False

    def _verify_certificate(self, sqr: str, cert: Optional[str]):
        """Verify certificate for QR login"""
        return self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="verifyCertificate",
            params=[[12, 1, [[11, 1, sqr], [11, 2, cert or ""]]]],
            protocol=4,
        )

    def _qr_code_login(self, sqr: str) -> Dict:
        """Execute QR code login"""
        return self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="qrCodeLogin",
            params=[[12, 1, [
                [11, 1, sqr],
                [11, 2, self.client.device],
                [2, 3, True],  # autoLoginIsRequired
            ]]],
            protocol=4,
        )

    def _qr_code_login_v2(self, sqr: str) -> Dict:
        """Execute QR code login V2"""
        return self._request(
            path=self.SECONDARY_QR_ENDPOINT,
            method="qrCodeLoginV2",
            params=[[12, 1, [
                [11, 1, sqr],
                [11, 2, self.client.system_name],
                [11, 3, "linepy-device"],
                [2, 4, True],  # autoLoginIsRequired
            ]]],
            protocol=4,
        )

    # ========== Request Helper ==========

    def _request(
        self,
        path: str,
        method: str,
        params: List,
        protocol: int = 4,
        timeout: Optional[float] = None,
        extra_headers: Optional[Dict] = None,
    ) -> Dict:
        """
        Send Thrift request using linejs-style params format.

        Args:
            path: API endpoint
            method: Method name
            params: Parameters in [[type, id, value], ...] format
            protocol: 3=binary, 4=compact
            timeout: Request timeout
            extra_headers: Additional headers
        """
        from .thrift import write_thrift

        # Generate Thrift data using new high-level writer
        data = write_thrift(params, method, protocol)


        response = self.client.request.request(
            path=path,
            data=data,
            protocol=protocol,
            timeout=timeout,
            extra_headers=extra_headers,
        )

        # Check for error response
        if isinstance(response, dict) and "error" in response:
            error = response["error"]
            error_code = error.get("code") or error.get("_data", {}).get(1)
            error_msg = error.get("message") or error.get("_data", {}).get(2, "Unknown error")
            raise LoginError(f"[{error_code}] {error_msg}")

        return response

