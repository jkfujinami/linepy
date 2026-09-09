# -*- coding: utf-8 -*-
"""Base Service module for LINEPY."""

from typing import Any, List, Optional, Type, TypeVar, Union

from .._model_base import ModelBase
from .._model_base import validate_python as _validate_python

T = TypeVar("T", bound=ModelBase)


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


def validate_response_model(data: Any, response_model: Any) -> Any:
    """Validate thrift-decoded ``data`` against ``response_model``.

    ``response_model`` may be a plain :class:`~linepy._model_base.ModelBase`
    dataclass *or* a typing generic such as ``List[SomeModel]`` /
    ``Dict[str, Model]`` -- ``linepy._model_base.validate_python`` (the
    ``TypeAdapter.validate_python`` equivalent) handles both shapes
    uniformly, structurally recursing into ``List``/``Dict``/dataclass as
    needed (used by ~40 methods such as ``getE2EEPublicKeys``, which returns
    ``List[Pb1_C13097n4]``).

    Int-keyed thrift field dicts are recursively normalized to string keys
    (matching each model's ``model_field(alias="<id>")``) regardless of
    whether ``data`` itself is a dict, a list of dicts, or a bare scalar --
    converting only when the *top-level* value is a dict would silently
    leave a ``List[...]`` response's items (which carry the actual
    int-keyed dicts) unconverted.
    """
    data = _convert_int_keys_to_str(data)
    return _validate_python(response_model, data)


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
        import httpx

        from ..thrift import write_thrift

        if params is None:
            params = []

        target_endpoint = endpoint if endpoint is not None else self.ENDPOINT

        data = write_thrift(params, method, self.PROTOCOL)

        try:
            response = self.client.request.request(
                path=target_endpoint,
                data=data,
                protocol=self.PROTOCOL,
            )
        except httpx.HTTPStatusError as e:
            # HTTP error (4xx, 5xx)
            from ..base import LineException

            # Try to parse response body for more info
            body = ""
            try:
                body = e.response.text[:500]  # First 500 chars
            except Exception:
                pass

            raise LineException(
                code=e.response.status_code,
                message=f"HTTP {e.response.status_code}: {e.response.reason_phrase}",
                metadata={"body": body, "url": str(e.request.url)},
            )

        # Check for Thrift-level error
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
        """Validate and parse response data into a Pydantic model (or a
        generic such as ``List[Model]``/``Dict[str, Model]``)."""
        if response_model and data is not None:
            return validate_response_model(data, response_model)

        return data
