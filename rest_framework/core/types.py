import typing


Scope = typing.Mapping[str, typing.Any]
Message = typing.Mapping[str, typing.Any]

Receive = typing.Callable[[], typing.Awaitable[Message]]
Send = typing.Callable[[Message], typing.Awaitable[None]]
