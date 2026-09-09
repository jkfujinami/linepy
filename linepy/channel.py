"""
Channel Service for LINEPY

Handles channel token issuance and other channel-related operations.
"""

from typing import Any, Dict, List

from .exceptions import LineException


class ChannelService:
    """
    Channel Service

    Endpoint: /CH4
    Protocol: Compact (4)
    """

    ENDPOINT = "/CH4"
    PROTOCOL = 4

    def __init__(self, client):
        self.client = client

    def _call(self, method: str, params: List = None) -> Any:
        from .thrift import write_thrift

        if params is None:
            params = []

        data = write_thrift(params, method, self.PROTOCOL)

        response = self.client.request.request(
            path=self.ENDPOINT,
            data=data,
            protocol=self.PROTOCOL,
        )

        if isinstance(response, dict) and "error" in response:
            err = response["error"]
            raise LineException(
                code=err.get("code", -1),
                message=err.get("message", "Unknown error"),
                metadata=err.get("metadata"),
            )

        return response

    def approve_channel_and_issue_channel_token(self, channel_id: str) -> Dict:
        """
        Approve channel and issue channel token.

        Args:
            channel_id: Channel ID string (e.g. "1341209850" for Timeline)

        Returns:
            Channel token info (typically contains 'channelAccessToken')
        """
        # approveChannelAndIssueChannelToken_args: [[11, 1, channelId]]
        return self._call("approveChannelAndIssueChannelToken", [[11, 1, channel_id]])

    def issue_channel_token(self, channel_id: str) -> Any:
        """Issue a channel token for a channel id (issueChannelToken_args)."""
        return self._call("issueChannelToken", [[11, 1, channel_id]])
