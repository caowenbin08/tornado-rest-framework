
from ..datastructures import MutableHeaders
from ..types import Receive, Send
import json
import typing


class Response:
    media_type = None
    charset = "utf-8"

    def __init__(
        self,
        content: typing.Any,
        status_code: int = 200,
        headers: dict = None,
        media_type: str = None,
    ) -> None:
        self.body = self.render(content)
        self.status_code = status_code
        if media_type is not None:
            self.media_type = media_type
        self.init_headers(headers)

    def render(self, content: typing.Any) -> bytes:
        if isinstance(content, bytes):
            return content
        return content.encode(self.charset)

    def init_headers(self, headers):
        if headers is None:
            raw_headers = []
            populate_content_length = True
            populate_content_type = True
        else:
            raw_headers = [
                (k.lower().encode("latin-1"), v.encode("latin-1"))
                for k, v in headers.items()
            ]
            keys = [h[0] for h in raw_headers]
            populate_content_length = b"content-length" in keys
            populate_content_type = b"content-type" in keys

        body = getattr(self, "body", None)
        if body is not None and populate_content_length:
            content_length = str(len(body))
            raw_headers.append((b"content-length", content_length.encode("latin-1")))

        content_type = self.media_type
        if content_type is not None and populate_content_type:
            if content_type.startswith("text/"):
                content_type += "; charset=" + self.charset
            raw_headers.append((b"content-type", content_type.encode("latin-1")))

        self.raw_headers = raw_headers

    @property
    def headers(self):
        if not hasattr(self, "_headers"):
            self._headers = MutableHeaders(self.raw_headers)
        return self._headers

    async def __call__(self, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self.raw_headers,
            }
        )
        await send({"type": "http.response.body", "body": self.body})


class HTMLResponse(Response):
    media_type = "text/html"


class PlainTextResponse(Response):
    media_type = "text/plain"


class JsonResponse(Response):
    media_type = "application/json"
    options = {
        "ensure_ascii": False,
        "allow_nan": False,
        "indent": None,
        "separators": (",", ":"),
    }  # type: typing.Dict[str, typing.Any]

    def render(self, content: typing.Any) -> bytes:
        return json.dumps(content, **self.options).encode("utf-8")
