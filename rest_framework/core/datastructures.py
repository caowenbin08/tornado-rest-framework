import typing
from rest_framework.core.types import Scope, StrDict, BytesPairs, StrPairs
from urllib.parse import parse_qsl, unquote, urlparse, ParseResult


class URL:
    def __init__(self, url: str = "", scope: Scope = None):
        if scope is not None:
            scheme = scope["scheme"]
            host, port = scope["server"]
            path = scope.get("root_path", "") + scope["path"]
            query_string = scope["query_string"]

            default_port = {"http": 80, "https": 443, "ws": 80, "wss": 443}[scheme]
            if port == default_port:
                url = f"{scheme}://{host}{path}"
            else:
                url = f"{scheme}://{host}:{port}{path}"

            if query_string:
                url += "?" + unquote(query_string.decode())

        self._url = url

    @property
    def components(self) -> ParseResult:
        if not hasattr(self, "_components"):
            setattr(self, "_components", urlparse(self._url))

        return self._components

    @property
    def scheme(self) -> str:
        return self.components.scheme

    @property
    def netloc(self) -> str:
        return self.components.netloc

    @property
    def path(self) -> bytes:
        return self.components.path.encode()

    @property
    def params(self) -> str:
        return self.components.params

    @property
    def query(self) -> str:
        return self.components.query

    @property
    def fragment(self) -> str:
        return self.components.fragment

    @property
    def username(self) -> typing.Union[None, str]:
        return self.components.username

    @property
    def password(self) -> typing.Union[None, str]:
        return self.components.password

    @property
    def hostname(self) -> typing.Union[None, str]:
        return self.components.hostname

    @property
    def port(self) -> typing.Optional[int]:
        return self.components.port

    def replace(self, **kwargs: typing.Any) -> "URL":
        if "hostname" in kwargs or "port" in kwargs:
            hostname = kwargs.pop("hostname", self.hostname)
            port = kwargs.pop("port", self.port)

            netloc = hostname if port is None else f"{hostname}:{port}"
            kwargs["netloc"] = netloc

        replace_fun = hasattr(self.components, "_replace")
        components = replace_fun(**kwargs)

        return URL(components.geturl())

    def __eq__(self, other):
        return str(self) == str(other)

    def __str__(self):
        return self._url


class QueryParams(StrDict):
    def __init__(self, value: typing.Union[str, typing.Union[StrDict, StrPairs]] = None) -> None:
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

    def getlist(self, key: typing.Any) -> typing.List[str]:
        return [v for k, v in self._list if k == key]

    def keys(self) -> typing.List[str]:
        return [k for k, _ in self._list]

    def values(self) -> typing.List[str]:
        return [v for _, v in self._list]

    def items(self) -> StrPairs:
        return list(self._list)

    def get(self, key: typing.Any, default: typing.Any = None) -> typing.Any:
        return self._dict.get(key, default)

    def __getitem__(self, key: typing.Any) -> str:
        return self._dict[key]

    def __contains__(self, key: typing.Any) -> bool:
        return key in self._dict

    def __iter__(self) -> typing.Iterator[typing.Any]:
        return iter(self._list)

    def __len__(self) -> int:
        return len(self._list)

    def __eq__(self, other: typing.Any) -> bool:
        if not isinstance(other, QueryParams):
            other = QueryParams(other)

        return sorted(self._list) == sorted(other._list)

    def __repr__(self) -> str:
        return f"QueryParams({repr(self._list)})"


class Headers(StrDict):
    def __init__(self, raw_headers: typing.Optional[BytesPairs] = None) -> None:
        self._list = [] if raw_headers is None else raw_headers

    def keys(self) -> typing.List[str]:
        return [k.decode("latin-1") for k, _ in self._list]

    def values(self) -> typing.List[str]:
        return [v.decode("latin-1") for _, v in self._list]

    def items(self) -> StrPairs:
        return [(k.decode("latin-1"), v.decode("latin-1")) for k, v in self._list]

    def get(self, key: str, default: typing.Any = None) -> typing.Any:
        try:
            return self[key]
        except KeyError:
            return default

    def getlist(self, key: str) -> typing.List[str]:
        temp_key = key.lower().encode("latin-1")
        return [v.decode("latin-1") for k, v in self._list if k == temp_key]

    def mutable_headers(self) -> "MutableHeaders":
        return MutableHeaders(self._list[:])

    def __getitem__(self, key: str) -> str:
        temp_key = key.lower().encode("latin-1")
        for k, v in self._list:
            if k == temp_key:
                return v.decode("latin-1")
        raise KeyError(key)

    def __contains__(self, key: typing.Any) -> bool:
        temp_key = key.lower().encode("latin-1")
        for k, v in self._list:
            if k == temp_key:
                return True
        return False

    def __iter__(self) -> typing.Iterator[typing.Any]:
        return iter(self.items())

    def __len__(self) -> int:
        return len(self._list)

    def __eq__(self, other: typing.Any) -> bool:
        if not isinstance(other, Headers):
            other = Headers(other)

        return sorted(self._list) == sorted(other._list)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({repr(self.items())})"


class MutableHeaders(Headers):
    def __setitem__(self, key: str, value: str):
        set_key = key.lower().encode("latin-1")
        set_value = value.encode("latin-1")

        found_indexes = []
        for idx, (k, v) in enumerate(self._list):
            if k == set_key:
                found_indexes.append(idx)

        for idx in reversed(found_indexes[1:]):
            del self._list[idx]

        if found_indexes:
            idx = found_indexes[0]
            self._list[idx] = (set_key, set_value)
        else:
            self._list.append((set_key, set_value))

    def __delattr__(self, key: str) -> None:
        del_key = key.lower().encode("latin-1")

        pop_indexes = []
        for idx, (k, v) in enumerate(self._list):
            if k == del_key:
                pop_indexes.append(idx)

        for idx in reversed(pop_indexes):
            del (self._list[idx])

    def setdefault(self, key: str, value: str) -> str:
        set_key = key.lower().encode("latin-1")
        set_value = value.encode("latin-1")

        for idx, (k, v) in enumerate(self._list):
            if k == set_key:
                return v.decode("latin-1")

        self._list.append((set_key, set_value))
        return value

    def update(self, other: dict) -> None:
        for k, v in other.items():
            self[k] = v



