from typing import List
from urllib.parse import parse_qs, ParseResult
from asyncio import Event
from queue import deque
from rest_framework.core.multipart import DiskFile, MemoryFile, UploadedFile
from rest_framework.core.exceptions import InvalidJSON, StreamAlreadyConsumed
from rest_framework.core.parsers import parse_url
from rest_framework.utils import json as jsonlib

# noinspection PyUnresolvedReferences
from rest_framework.core.headers.headers cimport Headers
# noinspection PyUnresolvedReferences
from rest_framework.core.protocol.cprotocol cimport Connection
# noinspection PyUnresolvedReferences
from rest_framework.core.multipart.parser cimport MultipartParser

class RequestParams:
    def __init__(self, values: dict):
        self.values = values

    def get(self, item):
        v = self.values.get(item)
        return v[0] if v else None

    def get_list(self, item, default=None):
        return self.values.get(item, default or [])

    def __getitem__(self, item):
        return self.values[item]

    def __getattr__(self, item):
        return getattr(self.values, item)


cdef class StreamQueue:

    def __init__(self):
        self.items = deque()
        self.event = Event()
        self.waiting = False
        self.dirty = False
        self.finished = False

    async def get(self) -> bytes:
        try:
            return self.items.popleft()
        except IndexError:
            if self.finished is True:
                return b''
            else:
                self.event.clear()
                self.waiting = True
                await self.event.wait()
                self.event.clear()
                self.waiting = False
                return self.items.popleft()

    cdef void put(self, bytes item):
        self.dirty = True
        self.items.append(item)
        if self.waiting is True:
            self.event.set()

    cdef void clear(self):
        if self.dirty:
            self.items.clear()
            self.event.clear()
            self.dirty = False
        self.finished = False

    cdef void end(self):
        if self.waiting:
            self.put(None)
        self.finished = True


cdef class Stream:

    def __init__(self, connection):
        self.consumed = False
        self.queue = StreamQueue()
        self.connection = connection

    async def read(self) -> bytearray:
        if self.consumed:
            raise StreamAlreadyConsumed()
        data = bytearray()
        async for chunk in self:
            data.extend(chunk)
        return data

    async def __aiter__(self):
        if self.consumed:
            raise StreamAlreadyConsumed()
        while True:
            self.connection.resume_reading()
            data = await self.queue.get()
            if not data:
                self.consumed = True
                break
            self.connection.pause_reading()
            yield data

    cdef void clear(self):
        """
        Resets the stream status.
        :return: None
        """
        self.queue.clear()
        self.consumed = False


cdef class Request:

    def __init__(self, bytes url, Headers headers, bytes method, Stream stream, Connection protocol):
        """

        :param url:
        :param headers:
        :param method:
        :param stream:
        :param protocol:
        """
        self.url = url
        self.protocol = protocol
        self.method = method
        self.headers = headers
        self.context = {}
        self.stream = stream
        self._cookies = None
        self._args = None
        self._parsed_url = None
        self._form = None
        self._body = None

    @property
    def app(self):
        return self.protocol.app

    cpdef str client_ip(self):
        return self.protocol.client_ip()

    @property
    def parsed_url(self) -> ParseResult:
        """

        :return:
        """
        if not self._parsed_url:
            self._parsed_url = parse_url(self.url)
        return self._parsed_url

    @property
    def args(self) -> RequestParams:
        """

        :return:
        """
        if not self._args:
            self._args = RequestParams(parse_qs(self.parsed_url.query))
        return self._args

    @property
    def cookies(self) -> dict:
        """

        :return:
        """
        if self._cookies is None:
            self._cookies = self.headers.parse_cookies()
        return self._cookies

    @property
    async def json(self) -> dict:
        try:
            return jsonlib.loads(await self.body)
        except ValueError:
            raise InvalidJSON('HTTP request body is not a valid JSON.', 400)

    async def _load_form(self):
        """

        :return:
        """
        cdef str content_type
        content_type = self.headers.get('Content-Type')
        if 'multipart/form-data' in content_type:
            boundary = content_type[content_type.find('boundary=') + 9:]
            parser = MultipartParser(boundary.encode())
            async for chunk in self.stream:
                await parser.feed(chunk)
            self._form = parser.consume()
        elif "application/x-www-form-urlencoded" in content_type:
            self._form = parse_qs(await self.body)
        else:
            self._form = {}

    @property
    async def files(self) -> List[UploadedFile]:
        """

        :return:
        """
        cdef list files = []
        if self._form is None:
            await self._load_form()
        for value in self._form.values():
            if isinstance(value, (DiskFile, MemoryFile)):
                files.append(value)
        return files

    @property
    async def form(self) -> dict:
        """

        :return:
        """
        if self._form is None:
            await self._load_form()
        return self._form

    @property
    async def body(self):
        if self._body is None:
            self._body = (await self.stream.read()).decode()
        return self._body
