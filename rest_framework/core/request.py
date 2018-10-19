import typing
from collections.abc import Mapping
from rest_framework.core.types import Scope, Receive
from rest_framework.utils.escape import json_decode
from rest_framework.core.datastructures import URL, Headers, QueryParams


class ClientDisconnect(Exception):
    pass


class Request(Mapping):
    def __init__(self, scope: Scope, receive: Receive = None) -> None:
        assert scope["type"] == "http"
        self._scope = scope
        self._receive = receive
        self.context = {}
        self._stream_consumed = False

    def __getitem__(self, key: str) -> str:
        return self._scope[key]

    def __iter__(self) -> typing.Iterator[str]:
        return iter(self._scope)

    def __len__(self) -> int:
        return len(self._scope)

    @property
    def method(self) -> bytes:
        return self._scope["method"].encode()

    @property
    def url(self) -> URL:
        if not hasattr(self, "_url"):
            setattr(self, "_url", URL(scope=self._scope))

        return self._url

    @property
    def headers(self) -> Headers:
        if not hasattr(self, "_headers"):
            setattr(self, "_headers", Headers(self._scope["headers"]))

        return self._headers

    @property
    def query_params(self) -> QueryParams:
        if not hasattr(self, "_query_params"):
            query_string = self._scope["query_string"].decode()
            setattr(self, "_query_params", QueryParams(query_string))

        return self._query_params

    async def stream(self) -> typing.AsyncGenerator[bytes, None]:
        if hasattr(self, "_body"):
            yield self._body
            return

        if self._stream_consumed:
            raise RuntimeError("Stream consumed")

        if self._receive is None:
            raise RuntimeError("Receive channel has not been made available")

        self._stream_consumed = True
        while 1:
            message = await self._receive()
            message_type = message["type"]

            if message_type == "http.request":
                yield message.get("body", b"")
                if not message.get("more_body", False):
                    break
            elif message_type == "http.disconnect":
                raise ClientDisconnect()

    async def body(self) -> bytes:
        if not hasattr(self, "_body"):
            body = b""

            async for chunk in self.stream():
                body += chunk

            setattr(self, "_body", body)

        return self._body

    async def json(self) -> typing.Any:
        if not hasattr(self, "_json"):
            body = await self.body()
            json_data = json_decode(body) if body else {}
            setattr(self, "_json", json_data)

        return self._json

    def client_ip(self):
        return self._scope["client"][0]



