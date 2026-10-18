import datetime

from common.v1 import common_pb2 as _common_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ItemStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ITEM_STATUS_UNSPECIFIED: _ClassVar[ItemStatus]
    ITEM_STATUS_OPEN: _ClassVar[ItemStatus]
    ITEM_STATUS_DONE: _ClassVar[ItemStatus]
ITEM_STATUS_UNSPECIFIED: ItemStatus
ITEM_STATUS_OPEN: ItemStatus
ITEM_STATUS_DONE: ItemStatus

class Item(_message.Message):
    __slots__ = ("id", "owner_id", "owner_name", "title", "description", "status", "created_at", "updated_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    OWNER_ID_FIELD_NUMBER: _ClassVar[int]
    OWNER_NAME_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    owner_id: str
    owner_name: str
    title: str
    description: str
    status: ItemStatus
    created_at: _timestamp_pb2.Timestamp
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., owner_id: _Optional[str] = ..., owner_name: _Optional[str] = ..., title: _Optional[str] = ..., description: _Optional[str] = ..., status: _Optional[_Union[ItemStatus, str]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CreateItemRequest(_message.Message):
    __slots__ = ("context", "title", "description")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    title: str
    description: str
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., title: _Optional[str] = ..., description: _Optional[str] = ...) -> None: ...

class CreateItemResponse(_message.Message):
    __slots__ = ("item",)
    ITEM_FIELD_NUMBER: _ClassVar[int]
    item: Item
    def __init__(self, item: _Optional[_Union[Item, _Mapping]] = ...) -> None: ...

class GetItemRequest(_message.Message):
    __slots__ = ("context", "item_id")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    item_id: str
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., item_id: _Optional[str] = ...) -> None: ...

class GetItemResponse(_message.Message):
    __slots__ = ("item",)
    ITEM_FIELD_NUMBER: _ClassVar[int]
    item: Item
    def __init__(self, item: _Optional[_Union[Item, _Mapping]] = ...) -> None: ...

class ListItemsRequest(_message.Message):
    __slots__ = ("context", "limit", "offset")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    limit: int
    offset: int
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ListItemsResponse(_message.Message):
    __slots__ = ("items", "has_more")
    ITEMS_FIELD_NUMBER: _ClassVar[int]
    HAS_MORE_FIELD_NUMBER: _ClassVar[int]
    items: _containers.RepeatedCompositeFieldContainer[Item]
    has_more: bool
    def __init__(self, items: _Optional[_Iterable[_Union[Item, _Mapping]]] = ..., has_more: _Optional[bool] = ...) -> None: ...

class UpdateItemRequest(_message.Message):
    __slots__ = ("context", "item_id", "title", "description", "status")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    item_id: str
    title: str
    description: str
    status: ItemStatus
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., item_id: _Optional[str] = ..., title: _Optional[str] = ..., description: _Optional[str] = ..., status: _Optional[_Union[ItemStatus, str]] = ...) -> None: ...

class UpdateItemResponse(_message.Message):
    __slots__ = ("item",)
    ITEM_FIELD_NUMBER: _ClassVar[int]
    item: Item
    def __init__(self, item: _Optional[_Union[Item, _Mapping]] = ...) -> None: ...

class DeleteItemRequest(_message.Message):
    __slots__ = ("context", "item_id")
    CONTEXT_FIELD_NUMBER: _ClassVar[int]
    ITEM_ID_FIELD_NUMBER: _ClassVar[int]
    context: _common_pb2.RequestContext
    item_id: str
    def __init__(self, context: _Optional[_Union[_common_pb2.RequestContext, _Mapping]] = ..., item_id: _Optional[str] = ...) -> None: ...

class DeleteItemResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
