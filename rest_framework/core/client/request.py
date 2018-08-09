from rest_framework.core.parsers.typing import URL
from rest_framework.core.client.cookies import CookiesJar
from rest_framework.core.client.connection import Connection


class Request:

    __slots__ = ('method', 'url', 'headers', 'data', 'cookies', 'streaming', 'chunked',
                 'encoding', 'origin')

    def __init__(self, method: str, url: URL, headers: dict, data, cookies: CookiesJar, origin=None):
        self.method = method.upper() if method else 'GET'
        self.url = url
        self.headers = headers or {}
        if 'Host' not in headers:
            self.headers.update({'Host': url.host.decode()})
        self.data = data or b''
        self.cookies = cookies
        self.streaming = True if data and not isinstance(data, (bytes, bytearray)) else False
        self.chunked = self.streaming
        self.origin = origin

    async def encode(self, connection: Connection):

        # Headers
        http_request = f'{self.method} {self.url.path.decode()} HTTP/1.1\r\n'
        for header, value in self.headers.items():
            http_request += f'{header}: {str(value)}\r\n'
        if self.cookies:
            cookies = ';'.join([c.name + '=' + c.value for c in self.cookies])
            http_request += f'Cookie: {cookies}'

        if not self.streaming:
            http_request += f'Content-Length: {str(len(self.data))}\r\n'
            await connection.sendall((http_request + '\r\n').encode() + self.data)

        elif self.chunked:
            http_request += f'Transfer-Encoding: chunked\r\n'
            await connection.sendall((http_request + '\r\n').encode())
            for chunk in self.data:
                size = hex(len(chunk))[2:].encode('utf-8')
                await connection.sendall(size + b'\r\n' + chunk + b'\r\n')
            await connection.sendall(b'0\r\n\r\n')

        elif not self.chunked:
            body = bytearray()
            for chunk in self.data:
                body.extend(chunk)
            http_request += f'Content-Length: {str(len(body))}\r\n\r\n'
            body.extend(http_request.encode())
            await connection.sendall(body)
