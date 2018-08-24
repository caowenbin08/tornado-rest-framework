import typing
from urllib.parse import parse_qsl
from rest_framework.utils.escape import json_decode


class ClientDisconnect(Exception):
    pass


class URL:
    def __init__(self, schema: bytes, host: bytes, port, path: bytes, query: bytes):
        self.schema = schema
        self.host = host
        self.port = port
        self.path = path
        self.query = query


class Headers(typing.Mapping[str, str]):
    def __init__(self, raw_headers=None) -> None:
        self._list = [] if raw_headers is None else raw_headers

    def keys(self):
        return [key.decode("latin-1") for key, value in self._list]

    def values(self):
        return [value.decode("latin-1") for key, value in self._list]

    def items(self):
        return [
            (key.decode("latin-1"), value.decode("latin-1"))
            for key, value in self._list
        ]

    def get(self, key: str, default: str = None):
        try:
            return self[key]
        except KeyError:
            return default

    def getlist(self, key: str) -> typing.List[str]:
        get_header_key = key.lower().encode("latin-1")
        return [
            item_value.decode("latin-1")
            for item_key, item_value in self._list
            if item_key == get_header_key
        ]

    def mutablecopy(self):
        return MutableHeaders(self._list[:])

    def __getitem__(self, key: str):
        get_header_key = key.lower().encode("latin-1")
        for header_key, header_value in self._list:
            if header_key == get_header_key:
                return header_value.decode("latin-1")
        raise KeyError(key)

    def __contains__(self, key: str):
        get_header_key = key.lower().encode("latin-1")
        for header_key, header_value in self._list:
            if header_key == get_header_key:
                return True
        return False

    def __iter__(self):
        return iter(self.items())

    def __len__(self):
        return len(self._list)

    def __eq__(self, other):
        if not isinstance(other, Headers):
            return False
        return sorted(self._list) == sorted(other._list)

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, repr(self.items()))


class MutableHeaders(Headers):
    def __setitem__(self, key: str, value: str):
        """
        Set the header `key` to `value`, removing any duplicate entries.
        Retains insertion order.
        """
        set_key = key.lower().encode("latin-1")
        set_value = value.encode("latin-1")

        found_indexes = []
        for idx, (item_key, item_value) in enumerate(self._list):
            if item_key == set_key:
                found_indexes.append(idx)

        for idx in reversed(found_indexes[1:]):
            del self._list[idx]

        if found_indexes:
            idx = found_indexes[0]
            self._list[idx] = (set_key, set_value)
        else:
            self._list.append((set_key, set_value))

    def __delitem__(self, key: str):
        """
        Remove the header `key`.
        """
        del_key = key.lower().encode("latin-1")

        pop_indexes = []
        for idx, (item_key, item_value) in enumerate(self._list):
            if item_key == del_key:
                pop_indexes.append(idx)

        for idx in reversed(pop_indexes):
            del (self._list[idx])

    def setdefault(self, key: str, value: str):
        """
        If the header `key` does not exist, then set it to `value`.
        Returns the header value.
        """
        set_key = key.lower().encode("latin-1")
        set_value = value.encode("latin-1")

        for idx, (item_key, item_value) in enumerate(self._list):
            if item_key == set_key:
                return item_value.decode("latin-1")
        self._list.append((set_key, set_value))
        return value

StrPairs = typing.Sequence[typing.Tuple[str, str]]
StrDict = typing.Mapping[str, str]


class QueryParams(typing.Mapping[str, str]):
    def __init__(
        self, value: typing.Union[str, typing.Union[StrDict, StrPairs]] = None
    ) -> None:
        if value is None:
            value = []
        elif isinstance(value, str):
            value = parse_qsl(value)

        if hasattr(value, "items"):
            items = list(typing.cast(StrDict, value).items())
        else:
            items = list(typing.cast(StrPairs, value))
        self._dict = {k: v for k, v in reversed(items)}
        self._list = items

    def getlist(self, key: str) -> typing.List[str]:
        return [item_value for item_key, item_value in self._list if item_key == key]

    def keys(self):
        return [key for key, value in self._list]

    def values(self):
        return [value for key, value in self._list]

    def items(self):
        return list(self._list)

    def get(self, key, default=None):
        if key in self._dict:
            return self._dict[key]
        else:
            return default

    def __getitem__(self, key):
        return self._dict[key]

    def __contains__(self, key):
        return key in self._dict

    def __iter__(self):
        return iter(self._list)

    def __len__(self):
        return len(self._list)

    def __eq__(self, other):
        if not isinstance(other, QueryParams):
            other = QueryParams(other)
        return sorted(self._list) == sorted(other._list)

    def __repr__(self):
        return "QueryParams(%s)" % repr(self._list)


class Request:
    def __init__(self, scope, receive=None):
        assert scope["type"] == "http"
        self._scope = scope
        self._receive = receive
        self._stream_consumed = False
        self.context = {}
        self._url = None
        self._headers = None
        self._query_params = None
        self._body = None
        self._json = None

    @property
    def method(self) -> bytes:
        return self._scope["method"].encode()

    @property
    def url(self) -> URL:
        if self._url is None:
            scheme = self._scope["scheme"].encode()
            host, port = self._scope["server"]
            path = self._scope.get("root_path", "") + self._scope["path"]
            query_string = self._scope["query_string"]
            self._url = URL(
                schema=scheme,
                host=host.encode(),
                port=port,
                path=path.encode(),
                query=query_string
            )

        return self._url

    @property
    def headers(self) -> Headers:
        if self._headers is None:
            self._headers = Headers(self._scope["headers"])
        return self._headers

    @property
    def query_params(self) -> QueryParams:
        if self._query_params is None:
            query_string = self._scope["query_string"].decode()
            self._query_params = QueryParams(query_string)
        return self._query_params

    async def stream(self):
        if self._body is not None:
            yield self._body
            return

        if self._stream_consumed:
            raise RuntimeError("Stream consumed")

        if self._receive is None:
            raise RuntimeError("Receive channel has not been made available")

        self._stream_consumed = True
        while True:
            message = await self._receive()
            if message["type"] == "http.request":
                yield message.get("body", b"")
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                raise ClientDisconnect()

    async def body(self):
        if self._body is None:
            body = b""
            async for chunk in self.stream():
                body += chunk
            self._body = body

        return self._body

    async def json(self):
        if self._json is None:
            body = await self.body()
            self._json = json_decode(body)
        return self._json

    def client_ip(self):
        return self._scope["client"][0]


