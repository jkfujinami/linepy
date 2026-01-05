# -*- coding: utf-8 -*-
"""Base Service module for LINEPY."""

from typing import List, Type, TypeVar, Optional, Dict, Any, Union
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def _convert_int_keys_to_str(data: Any) -> Any:
    """
    Recursively convert integer keys in a dict to string keys.

    This is needed because Thrift responses use integer field IDs as keys,
    but Pydantic's Field(alias=...) expects string keys.
    """
    if isinstance(data, dict):
        return {str(k): _convert_int_keys_to_str(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_convert_int_keys_to_str(item) for item in data]
    else:
        return data


class ServiceBase:
    """Base class for all services."""

    ENDPOINT: str = ""
    PROTOCOL: int = 4

    def __init__(self, client):
        self.client = client

    def _call(
        self,
        method: str,
        params: Optional[List] = None,
        response_model: Optional[Type[T]] = None,
        endpoint: Optional[str] = None
    ) -> Any:
        """Make an API call"""
        from ..thrift import write_thrift

        if params is None:
            params = []

        target_endpoint = endpoint if endpoint is not None else self.ENDPOINT

        data = write_thrift(params, method, self.PROTOCOL)

        response = self.client.request.request(
            path=target_endpoint,
            data=data,
            protocol=self.PROTOCOL,
        )

        # Check for error
        if isinstance(response, dict) and "error" in response:
            err = response["error"]
            from ..base import LineException

            raise LineException(
                code=err.get("code", -1),
                message=err.get("message", "Unknown error"),
                metadata=err.get("metadata"),
            )

        return self._validate_response(response, response_model)

    def _validate_response(
        self, data: Any, response_model: Optional[Type[T]] = None
    ) -> Union[T, Any]:
        """Validate and parse response data into Pydantic model."""
        if response_model and data is not None:
            # Convert integer keys to string keys for Pydantic alias compatibility

            # Convert integer keys to string keys for Pydantic alias compatibility
            if isinstance(data, dict):
                data = _convert_int_keys_to_str(data)

            return response_model.model_validate(data)

        return data
