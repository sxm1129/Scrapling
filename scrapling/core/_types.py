"""
Type definitions for type checking purposes.
"""

import sys

if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:
    from typing_extensions import TypeAlias

from typing import (
    TYPE_CHECKING,
    cast,
    overload,
    Any,
    Callable,
    Dict,
    Generator,
    AsyncGenerator,
    Generic,
    Iterable,
    List,
    Set,
    Literal,
    Optional,
    Iterator,
    Pattern,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    Match,
    Mapping,
    Awaitable,
    Protocol,
    Coroutine,
    SupportsIndex,
)
from typing_extensions import Self, Unpack, TypedDict

# Proxy can be a string URL or a dict (Playwright format: {"server": "...", "username": "...", "password": "..."})
ProxyType = Union[str, Dict[str, str]]
SUPPORTED_HTTP_METHODS = Literal["GET", "POST", "PUT", "DELETE"]
SelectorWaitStates = Literal["attached", "detached", "hidden", "visible"]
PageLoadStates = Literal["commit", "domcontentloaded", "load", "networkidle"]
extraction_types = Literal["text", "html", "markdown"]
StrOrBytes = Union[str, bytes]


# Copied from `playwright._impl._api_structures.SetCookieParam`
class SetCookieParam(TypedDict, total=False):
    name: str
    value: str
    url: Optional[str]
    domain: Optional[str]
    path: Optional[str]
    expires: Optional[float]
    httpOnly: Optional[bool]
    secure: Optional[bool]
    sameSite: Optional[Literal["Lax", "None", "Strict"]]
    partitionKey: Optional[str]
