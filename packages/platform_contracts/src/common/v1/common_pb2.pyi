from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class RequestContext(_message.Message):
    __slots__ = ("request_id", "actor_user_id", "actor_role")
    REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    ACTOR_USER_ID_FIELD_NUMBER: _ClassVar[int]
    ACTOR_ROLE_FIELD_NUMBER: _ClassVar[int]
    request_id: str
    actor_user_id: str
    actor_role: str
    def __init__(self, request_id: _Optional[str] = ..., actor_user_id: _Optional[str] = ..., actor_role: _Optional[str] = ...) -> None: ...
