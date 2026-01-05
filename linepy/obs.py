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

class ObsBase:
    OBS_DOMAIN = "obs.line-apps.com"

    def __init__(self, client):
        self.client = client

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
    ) -> Dict[str, str]:
        """
        Upload profile image to Square Member OBS.
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

            return obj_id, obj_hash
        except Exception as e:
            raise Exception(f"OBS Member Image Upload Failed: {e}")
