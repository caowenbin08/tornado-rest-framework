"""
|===== Warning ================================================================================|
| This is a stub file to provide type hints because this module is fully implemented in Cython |
|==============================================================================================|
"""
from rest_framework.core.headers import Headers
from rest_framework.core.multipart import UploadedFile
from typing import List, Callable


class Request:

    def __init__(self, url: bytes, headers: Headers, method: bytes, stream, protocol):
        self.url = url
        self.headers = headers
        self.method = method
        self.stream = stream
        self.protocol = protocol
        self.cookies: dict = {}
        self.args: dict = {}
        self.context: dict = {}

    def client_ip(self) -> str:
        """

        :return:
        """
        pass

    async def form(self) -> dict:
        """

        :return:
        """
        pass

    async def files(self) -> List[UploadedFile]:
        """

        :return:
        """
        pass

    async def _load_form(self) -> None:
        """

        :return:
        """
        pass

    async def json(self, loads: Callable=None, strict: bool = False) -> dict:
        """

        :param loads:
        :param strict:
        :return:
        """
        pass
