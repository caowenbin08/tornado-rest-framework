import asyncio
import uuid
from asyncio import BaseEventLoop
from typing import Union, List
from urllib.parse import urlencode
from rest_framework.core.parsers.parser import parse_url
from rest_framework.core.client.retries import RetryStrategy
from rest_framework.core.client.request import Request
from rest_framework.core.client.response import Response
from rest_framework.core.client.pool import ConnectionPool
from rest_framework.core.client.limits import RequestRate
from rest_framework.core.client.defaults import ClientDefaults
from rest_framework.core.client.exceptions import TooManyRedirects, MissingSchema
from rest_framework.core.multipart import MultipartEncoder
from rest_framework.core.client.cookies import SessionCookiesJar
from rest_framework.utils import json as json_module

URL_ENCODING = 'utf-8'
HTTP_GET = 'GET'
HTTP_DELETE = 'DELETE'
HTTP_PATCH = 'PATCH'
HTTP_POST = 'POST'
HTTP_PUT = 'PUT'


class HTTPEngine:

    __slots__ = ('loop', 'session', 'pools', 'limits')

    def __init__(self, session: 'Session', loop: BaseEventLoop, limits: List[RequestRate] = None):
        self.loop = loop
        self.session = session
        self.pools = {}
        self.limits = limits or []

    def get_pool(self, protocol: str, host: str, port: int) -> ConnectionPool:
        """

        :param protocol:
        :param host:
        :param port:
        :return:
        """
        key = (protocol, host, port)
        if port in (0, None):
            if protocol == b'https':
                port = 443
            else:
                port = 80
        try:
            return self.pools[key]
        except KeyError:
            self.pools[key] = ConnectionPool(loop=self.loop, host=host, port=port, protocol=protocol,
                                             keep_alive=self.session.keep_alive)
        return self.pools[key]

    async def handle_redirect(self, request: Request, response: Response, stream: bool, follow_redirects: bool,
                              max_redirects: int, decode: bool, validate_ssl, headers: dict) -> Response:
        """

        :param headers:
        :param validate_ssl:
        :param decode:
        :param max_redirects:
        :param follow_redirects:
        :param stream:
        :param response:
        :param request:
        :return:
        """
        if max_redirects == 0:
            raise TooManyRedirects
        try:
            location = response.headers['location']
        except KeyError:
            raise Exception('HTTP redirect response missing location header.')
        if not location.startswith('http'):
            if not location.startswith('/'):
                location = '/' + location
            location = request.url.netloc + location

        redirect_url = parse_url(location.encode())
        headers['Host'] = redirect_url.host
        return await self.request(
            url=redirect_url, method='GET', stream=stream, follow_redirects=follow_redirects,
            max_redirects=(max_redirects - 1), decode=decode, validate_ssl=validate_ssl, headers=headers,
            origin=response
        )

    async def throttle(self, url: str):
        """

        :param:
        :return:
        """
        for limit in self.limits:
            if not limit.pattern or limit.pattern.fullmatch(url):
                await limit.notify()

    async def request(self, url, method: str, stream: bool, follow_redirects: bool,
                      max_redirects: int, decode: bool, validate_ssl, headers: dict,
                      origin: Response = None, data=None) -> Response:
        """

        :param url:
        :param method:
        :param stream:
        :param follow_redirects:
        :param data:
        :param max_redirects:
        :param decode:
        :param validate_ssl:
        :param headers:
        :param origin:
        :return:
        """
        if self.limits:
            await self.throttle(url.raw)
        pool = self.get_pool(url.schema, url.host, url.port)
        connection = await pool.get_connection(validate_ssl)
        request = Request(method, url, headers, data, self.session.cookies.get(domain=url.host),
                          origin=origin)
        await request.encode(connection)
        response = Response(request.url, connection, request=request, decode=decode)
        await response.receive_headers()
        self.session.cookies.merge(await response.cookies, domain=request.url.host)
        if follow_redirects:
            if response.is_redirect():
                await response.read_content()
                return await self.handle_redirect(request, response, stream, follow_redirects,
                                                  max_redirects, decode, validate_ssl, headers)
        if not stream:
            await response.read_content()
        return response

    def close(self):
        for pool in self.pools.values():
            pool.close()


class Session:

    __slots__ = ('_loop', '_engine', '_headers', 'follow_redirects', 'max_redirects',
                 'stream', 'decode', 'ssl', 'prefix', 'keep_alive', 'retries_policy',
                 'timeout', 'cookies', 'limits')

    def __init__(self, loop: BaseEventLoop = None, headers: dict = None,
                 follow_redirects: bool = True, max_redirects: int = 30,
                 stream: bool = False, decode: bin = True, ssl=None, keep_alive: bool = True,
                 prefix: str = '', timeout: Union[int, float] = ClientDefaults.TIMEOUT,
                 retries: RetryStrategy = None, limits: List[RequestRate] = None):
        self._loop = loop or asyncio.get_event_loop()
        self._engine = HTTPEngine(self, self._loop, limits=limits)
        self._headers = ClientDefaults.HEADERS
        if headers:
            self._headers.update({k.title(): v for k, v in headers.items()})
        self.follow_redirects = follow_redirects
        self.max_redirects = max_redirects
        self.stream = stream
        self.decode = decode
        self.ssl = ssl
        self.prefix = prefix.encode(URL_ENCODING) or b''
        self.keep_alive = keep_alive
        self.retries_policy = retries or ClientDefaults.RETRY_STRATEGY
        self.timeout = timeout
        self.cookies = SessionCookiesJar()
        self.limits = limits

    @staticmethod
    def build_url(prefix: bytes, url: bytes, query: dict):
        if not url:
            raise ValueError('Url parameter must not be empty.')
        if prefix and prefix.endswith(b'/'):
            if url.startswith(b'/'):
                url = url[1:]
            url = prefix + url
        elif prefix:
            if url.startswith(b'/'):
                url = prefix + url
            else:
                url = prefix + b'/' + url

        if not url.startswith(b'http'):
            raise MissingSchema(f'Missing schema in {url.decode(URL_ENCODING)}. '
                                f'Perhaps you meant http://{url.decode(URL_ENCODING)} ?.')
        if query:
            url = url + b'?' + urlencode(query).encode(URL_ENCODING)

        return url

    async def request(self, url: str = '/', stream: bool = None, follow_redirects: bool = None,
                      max_redirects: int = 30, decode: bool = True, ssl=None,
                      timeout=ClientDefaults.TIMEOUT, retries: Union[RetryStrategy, int] = None,
                      headers: dict = None, method: str = HTTP_GET, query: dict = None,
                      json: dict = None, ignore_prefix: bool = False, body=None,
                      form: dict = None) -> Response:

        # Asserting the user is not using conflicting params.
        if sum([body is not None, json is not None, form is not None]) > 1:
            raise ValueError('You cannot set body, json or form together. You must pick one and only one.')

        # Handling default parameters.
        stream = stream if stream is not None else self.stream
        follow_redirects = follow_redirects if follow_redirects is not None else self.follow_redirects
        max_redirects = max_redirects if max_redirects is not None else self.max_redirects
        decode = decode if decode else self.decode
        ssl = ssl if ssl is not None else self.ssl
        retries = retries.clone() if retries is not None else RetryStrategy()

        request_headers = self._headers.copy()
        if headers:
            request_headers.update({k.title(): v for k, v in headers.items()})

        # Constructing the URL.
        url = self.build_url(prefix=self.prefix if not ignore_prefix else b'',
                             url=url.encode(URL_ENCODING), query=query)
        parsed_url = parse_url(url)
        if json is not None:
            body = json_module.dumps(json).encode('utf-8')
            request_headers['Content-Type'] = 'application/json'

        if form is not None:
            boundary = str(uuid.uuid4()).replace('-', '').encode()
            body = MultipartEncoder(delimiter=boundary, params=form)
            request_headers['Content-Type'] = f'multipart/form-data; boundary={boundary.decode()}'

        while True:
            try:
                task = self._engine.request(
                    url=parsed_url, data=body, method=method, stream=stream,
                    follow_redirects=follow_redirects, max_redirects=max_redirects, decode=decode,
                    validate_ssl=ssl, headers=request_headers)
                if timeout:
                    response = await asyncio.wait_for(task, timeout)
                else:
                    response = await task
                if retries.responses.get(response.status_code, 0) > 0:
                    retries.responses[response.status_code] -= 1
                    continue
                return response
            except (ConnectionError, TimeoutError) as error:
                if retries.network_failures.get(method, 0) > 0:
                    retries.network_failures[method] -= 1
                    continue
                raise error

    async def get(self, url: str, query: dict = None, **kwargs) -> Response:
        return await self.request(url=url, query=query, **kwargs)

    async def post(self, url: str, query: dict = None, body=None, form=None,
                   json=None, **kwargs) -> Response:
        return await self.request(url=url, method=HTTP_POST, query=query, body=body,
                                  form=form, json=json, **kwargs)

    async def put(self, url: str, query: dict = None, body=None, form=None,
                  json=None, **kwargs) -> Response:
        return await self.request(url=url, method=HTTP_PUT, query=query, body=body,
                                  form=form, json=json, **kwargs)

    async def patch(self, url: str, query: dict = None, body=None, form=None,
                    json=None, **kwargs) -> Response:
        return await self.request(url=url, method=HTTP_PATCH, query=query, body=body,
                                  form=form, json=json, **kwargs)

    async def delete(self, url: str, query: dict = None, body=None, form=None,
                     json=None, **kwargs) -> Response:
        return await self.request(url=url, method=HTTP_DELETE, query=query, body=body,
                                  form=form, json=json, **kwargs)

    def close(self):
        """

        :return:
        """
        self._engine.close()

    async def __aenter__(self):
        """

        :return:
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """

        :param exc_type:
        :param exc_val:
        :param exc_tb:
        :return:
        """
        self.close()
        await asyncio.sleep(0)
        if exc_val:
            raise exc_val
