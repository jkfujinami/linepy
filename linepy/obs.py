"""
OBS (Object Storage) Client for LINEPY

Handles file uploads (images, videos, audio) to LINE OBS servers.
Specifically optimized for Square (OpenChat).
"""

import base64
import json
import os
import time
from typing import Optional, Union, Dict, Any

def _write_binary_struct(fields) -> bytes:
    """Serialize a bare Thrift struct with TBinaryProtocol.

    Only the field types needed for X-Talk-Meta are supported: STRING(11) and
    an (empty) LIST(15) of STRUCT(12). Layout per field:
    ``type(1B) id(2B BE)`` then the value; struct terminated by STOP(0).
    """
    import struct as _struct

    out = bytearray()
    for ftype, fid, value in fields:
        out.append(ftype & 0xFF)
        out += _struct.pack(">h", fid)
        if ftype == 11:  # STRING / binary
            b = value.encode("utf-8") if isinstance(value, str) else bytes(value)
            out += _struct.pack(">i", len(b))
            out += b
        elif ftype == 15:  # LIST
            elem_type, items = value[0], value[1]
            out.append(elem_type & 0xFF)
            out += _struct.pack(">i", len(items))
            # X-Talk-Meta only ever passes an empty list here.
            if items:
                raise NotImplementedError("non-empty binary list not supported")
        else:
            raise NotImplementedError(f"binary struct field type {ftype}")
    out.append(0)  # STOP
    return bytes(out)


def build_talk_meta(message_id: str) -> str:
    """Build the ``X-Talk-Meta`` header value for an E2EE media download.

    Mirrors 本家: ``base64(JSON({message: base64(binaryStruct([[11,4,id],
    [15,27,[12,[]]]]))}))``.
    """
    inner = _write_binary_struct([[11, 4, message_id], [15, 27, [12, []]]])
    payload = {"message": base64.b64encode(inner).decode("ascii")}
    # JSON.stringify emits no spaces after ':'/','.
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(body).decode("ascii")


# E2EE media namespaces / content types (本家 obs mod.ts typeSet)
E2EE_MEDIA_TYPESET = {
    "image": ("emi", 1),
    "video": ("emv", 2),
    "audio": ("ema", 3),
    "file": ("emf", 14),
    "gif": ("emi", 1),
}


class ObsBase:
    OBS_DOMAIN = "obs.line-apps.com"

    def __init__(self, client):
        self.client = client

    # ================= Plain message media download (audit gap #4) ======

    OBS_PREFIX = "https://obs.line-apps.com/"

    def get_message_data_url(self, message_id: str, is_preview: bool = False,
                             is_square: bool = False) -> str:
        root = "g2" if is_square else "talk"
        suffix = "/preview" if is_preview else ""
        return f"{self.OBS_PREFIX}r/{root}/m/{message_id}{suffix}"

    def get_message_metadata_url(self, message_id: str, is_square: bool = False) -> str:
        root = "g2" if is_square else "talk"
        return f"{self.OBS_PREFIX}r/{root}/m/{message_id}/object_info.obs"

    def download_message_data(self, message_id: str, is_preview: bool = False,
                              is_square: bool = False) -> Dict[str, Any]:
        """Download plain (non-E2EE) message media by message id.

        Talk plain media and all Square media are served in the clear from OBS;
        E2EE Talk media must go through :meth:`download_media_by_e2ee` instead.
        Returns ``{"data": <bytes>, "fileName": <str|None>}``.
        """
        if not self.client.auth_token:
            raise RuntimeError("Not logged in")
        headers = {
            "accept": "application/json, text/plain, */*",
            "x-line-application": self.client.app_name,
            "x-Line-access": self.client.auth_token,
        }
        resp = self.client.request._http.get(
            self.get_message_data_url(message_id, is_preview, is_square), headers=headers
        )
        resp.raise_for_status()
        data = resp.content
        file_name = None
        try:
            meta = self.get_message_obs_metadata(message_id, is_square)
            file_name = meta.get("name") or meta.get("fileName")
        except Exception:
            pass
        return {"data": data, "fileName": file_name}

    def get_message_obs_metadata(self, message_id: str, is_square: bool = False) -> Dict[str, Any]:
        if not self.client.auth_token:
            raise RuntimeError("Not logged in")
        headers = {
            "accept": "application/json, text/plain, */*",
            "x-line-application": self.client.app_name,
            "x-Line-access": self.client.auth_token,
        }
        resp = self.client.request._http.get(
            self.get_message_metadata_url(message_id, is_square), headers=headers
        )
        resp.raise_for_status()
        return resp.json()

    # ================= E2EE Talk media (Phase 2 Step 6) =================

    def _upload_object_for_service(self, obs_path: str, data: bytes, params: dict) -> dict:
        headers = {
            "X-Line-Access": self.client.auth_token,
            "X-Line-Application": self.client.app_name,
            "Content-Type": "application/octet-stream",
            "X-Obs-Params": self._gen_obs_params(params),
            "User-Agent": self.client.request.user_agent,
        }
        url = f"https://{self.OBS_DOMAIN}/{obs_path}"
        response = self.client.request._http.post(url, content=data, headers=headers)
        response.raise_for_status()
        return {
            "objId": response.headers.get("x-obs-oid", ""),
            "objHash": response.headers.get("x-obs-hash", ""),
            "headers": response.headers,
        }

    def upload_media_by_e2ee(
        self,
        data: bytes,
        o_type: str,
        to: str,
        filename: Optional[str] = None,
        preview: Optional[bytes] = None,
        duration_ms: Optional[int] = None,
    ):
        """Encrypt and upload Talk media (image/video/audio/file/gif), then send.

        Faithful port of 本家 ``uploadMediaByE2EE``.
        """
        import uuid

        if to[:1] not in ("u", "c"):
            raise ValueError("Invalid mid for E2EE media")
        if o_type not in E2EE_MEDIA_TYPESET:
            raise ValueError(f"unsupported media type {o_type}")

        obs_namespace, content_type = E2EE_MEDIA_TYPESET[o_type]
        ext = (filename.rsplit(".", 1)[-1] if filename and "." in filename else "bin")
        params = {"type": "file"}
        if o_type == "gif":
            params["cat"] = "original"

        enc = self.client.e2ee.encrypt_by_key_material(data)
        key_material = enc["keyMaterial"]
        edata = enc["encryptedData"]

        temp_id = "reqid-" + str(uuid.uuid4())
        up = self._upload_object_for_service(
            f"talk/{obs_namespace}/{temp_id}", edata, params
        )
        obj_id = up["objId"]

        if o_type in ("image", "gif", "video"):
            if preview is not None:
                penc = self.client.e2ee.encrypt_by_key_material(
                    preview, base64.b64decode(key_material)
                )
                preview_edata = penc["encryptedData"]
            else:
                preview_edata = edata
            up2 = self._upload_object_for_service(
                f"talk/{obs_namespace}/{obj_id}__ud-preview", preview_edata, params
            )
            if obj_id != up2["objId"]:
                raise ValueError("objId mismatch on preview upload")

        chunks = self.client.e2ee.encrypt_e2ee_message(
            to, {"keyMaterial": key_material, "fileName": filename or ("line." + ext)},
            content_type,
        )

        content_metadata = {
            "SID": obs_namespace,
            "OID": obj_id,
            "FILE_SIZE": str(len(edata)),
            "e2eeVersion": "2",
        }
        if o_type in ("image", "gif", "video"):
            content_metadata["MEDIA_CONTENT_INFO"] = json.dumps({
                "category": "original",
                "fileSize": len(edata),
                "extension": ext,
                "animated": o_type == "gif",
            })
        if o_type == "video" and isinstance(duration_ms, (int, float)):
            rd = round(duration_ms)
            if rd > 0:
                content_metadata["DURATION"] = str(rd)

        return self.client.send_message(
            to=to,
            content_type=content_type,
            content_metadata=content_metadata,
            chunks=chunks,
        )

    def download_media_by_e2ee(self, message) -> Dict[str, Any]:
        """Download and decrypt a received E2EE media message.

        Returns ``{"data": <bytes>, "fileName": <str>}``. Faithful port of
        本家 ``downloadMediaByE2EE``.
        """
        to = self._msg_field(message, "to")
        if not to or to[:1] not in ("u", "c"):
            raise ValueError("Invalid mid for E2EE media")
        chunks = self._msg_field(message, "chunks")
        if not chunks:
            return None

        info = self.client.e2ee.decrypt_e2ee_data_message(message)
        key_material = info.get("keyMaterial")
        file_name = info.get("fileName")

        msg_id = self._msg_field(message, "id")
        metadata = self._msg_field(message, "contentMetadata") or {}
        talk_meta = build_talk_meta(msg_id)

        headers = {
            "X-Line-Access": self.client.auth_token,
            "X-Line-Application": self.client.app_name,
            "User-Agent": self.client.request.user_agent,
            "X-Talk-Meta": talk_meta,
        }
        url = f"https://{self.OBS_DOMAIN}/talk/{metadata.get('SID')}"
        response = self.client.request._http.get(url, headers=headers)
        response.raise_for_status()
        plain = self.client.e2ee.decrypt_by_key_material(response.content, key_material)
        return {"data": plain, "fileName": file_name}

    @staticmethod
    def _msg_field(message, name):
        aliases = {
            "to": ("to",),
            "chunks": ("chunks",),
            "id": ("id_", "id"),
            "contentMetadata": ("content_metadata", "contentMetadata"),
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

    def _gen_obs_params(self, params: Dict[str, Any]) -> str:
        """Generate X-Obs-Params header value (Base64 encoded JSON)"""
        json_str = json.dumps(params)
        return base64.b64encode(json_str.encode("utf-8")).decode("utf-8")

    def _get_duration(self, path: str) -> int:
        """
        Attempt to get media duration.
        Currently returns dummy value. To be implemented properly if needed.
        """
        return 0

    def upload_obj_square_chat(
        self,
        square_chat_mid: str,
        path_or_bytes: Union[str, bytes],
        content_type: str = "image", # image, video, audio, file, gif
        duration: Optional[int] = None,
        filename: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Upload object to Square Chat OBS.

        Args:
            square_chat_mid: Target Square Chat MID
            path_or_bytes: File path or bytes data
            content_type: Content type (image, video, audio, file, gif)
            duration: Duration in milliseconds (for video/audio)
            filename: Filename

        Returns:
            Dictionary with Object ID (objId) and Object Hash (objHash)
        """

        # 1. Get Reqseq
        reqseq = self.client.token_manager.get_next_reqseq("obs")

        # 2. Read Data
        if isinstance(path_or_bytes, str):
            if not filename:
                filename = os.path.basename(path_or_bytes)
            with open(path_or_bytes, "rb") as f:
                data = f.read()
        else:
            data = path_or_bytes
            if not filename:
                filename = f"file_{int(time.time())}"

        # 3. Prepare Params
        params = {
            "ver": "2.0",
            "type": content_type,
            "oid": "reqseq",
            "reqseq": str(reqseq),
            "tomid": square_chat_mid,
            "name": filename
        }

        # Content Type specific params
        if content_type in ["image", "gif"]:
            params["cat"] = "original"

        if content_type in ["video", "audio"]:
            if duration:
                params["duration"] = str(duration)
            else:
                # Fallback duration if not provided
                params["duration"] = "1000"

        # 4. Headers
        headers = {
            "X-Line-Access": self.client.auth_token,
            "X-Line-Application": self.client.app_name,
            "X-Line-Mid": self.client.mid,
            "Content-Type": "application/octet-stream",
            "X-Obs-Params": self._gen_obs_params(params),
            "User-Agent": self.client.request.user_agent
        }

        # 5. Send Request
        # Use underlying httpx client directly to get response headers
        url = f"https://{self.OBS_DOMAIN}/r/g2/m/reqseq"

        try:
            response = self.client.request._http.post(
                url,
                content=data,
                headers=headers
            )
            response.raise_for_status()

            # 6. Extract Object ID and Hash
            obj_id = response.headers.get("x-obs-oid", "reqseq")
            obj_hash = response.headers.get("x-obs-hash", "")

            return {
                "objId": obj_id,
                "objHash": obj_hash
            }

        except Exception as e:
            raise Exception(f"OBS Upload Failed: {e}")

    def upload_obj_square_member_image(
        self,
        member_mid: str,
        path_or_bytes: Union[str, bytes],
        filename: Optional[str] = None
    ) -> list[str, str]:
        """
        Upload profile image to Square Member OBS.
        Returns obj_id and obj_hash
        path: /r/g2/member/{member_mid}
        """

        # 1. Read Data
        if isinstance(path_or_bytes, str):
            if not filename:
                filename = os.path.basename(path_or_bytes)
            with open(path_or_bytes, "rb") as f:
                data = f.read()
        else:
            data = path_or_bytes
            if not filename:
                filename = f"image_{int(time.time())}.jpg"

        # 2. Prepare Params
        params = {
            "ver": "2.0",
            "type": "image",
            "name": filename,
            # For profile image, oid/reqseq might not be strictly required in params
            # if the path itself determines the resource, but let's keep it minimal.
        }

        # 3. Headers
        headers = {
            "X-Line-Access": self.client.auth_token,
            "X-Line-Application": self.client.app_name,
            "X-Line-Mid": self.client.mid,
            "Content-Type": "application/octet-stream",
            "X-Obs-Params": self._gen_obs_params(params),
            "User-Agent": self.client.request.user_agent
        }

        # 4. URL
        url = f"https://{self.OBS_DOMAIN}/r/g2/member/{member_mid}"

        try:
            response = self.client.request._http.post(
                url,
                content=data,
                headers=headers
            )
            response.raise_for_status()

            obj_id = response.headers.get("x-obs-oid", "")
            obj_hash = response.headers.get("x-obs-hash", "")

            return [obj_id, obj_hash]
        except Exception as e:
            raise Exception(f"OBS Member Image Upload Failed: {e}")
