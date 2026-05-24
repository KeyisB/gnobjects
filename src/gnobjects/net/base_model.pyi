from typing import Any, Callable, ClassVar, Generic, Mapping, TypeAlias, TypeVar, overload
from typing_extensions import Self
from typing_extensions import dataclass_transform
from _typeshed import DataclassInstance as _DataclassInstance
from pydantic import BaseModel as _PydanticBaseModel


_T = TypeVar("_T")
_ModelT = TypeVar("_ModelT")

MODEL_SCHEMA_KIND_UNKNOWN: int
MODEL_SCHEMA_KIND_GN_DATAMODEL: int
MODEL_SCHEMA_KIND_PYTHON_DATACLASS: int
MODEL_SCHEMA_KIND_PYDANTIC_BASEMODEL: int
MODEL_SCHEMA_KIND_PYDANTIC_TYPEADAPTER: int
MODEL_SCHEMA_KIND_NAMES: dict[int, str]


class _ModelAccessor(Generic[_ModelT]):
    def dump(self) -> dict[str, Any]: ...
    def toDict(self) -> dict[str, Any]: ...
    def fromDict(self, obj: Any, **kwargs: Any) -> _ModelT: ...
    def copy(self, *, update: dict[str, Any] | None = None, deep: bool = False) -> _ModelT: ...

    @property
    def fields_set(self) -> set[str]: ...

    @staticmethod
    def validate(model_class: type[_T], obj: Any, **kwargs: Any) -> _T: ...

    @staticmethod
    def fields(model_class: type) -> Any: ...

    @staticmethod
    def computed_fields(model_class: type) -> dict[str, Any]: ...

    @staticmethod
    def config(model_class: type) -> dict[str, Any]: ...


class DataModelError(Exception):
    detail: str
    code: str
    def __init__(self, detail: str) -> None: ...


class DataModelDefinitionError(DataModelError): ...
class DataModelFieldError(DataModelError): ...
class DataModelSchemaError(DataModelError): ...
class DataModelUsageError(DataModelError): ...
class DataModelValidationError(DataModelError): ...


class MinLen:
    value: int
    def __init__(self, value: int) -> None: ...
    @property
    def min_length(self) -> int: ...


class MaxLen:
    value: int
    def __init__(self, value: int) -> None: ...
    @property
    def max_length(self) -> int: ...


class Len:
    min_length: int | None
    max_length: int | None
    exact: int | None
    def __init__(self, min_length: int | None = None, max_length: int | None = None, exact: int | None = None) -> None: ...


class MinBytes:
    value: int
    def __init__(self, value: int) -> None: ...


class MaxBytes:
    value: int
    def __init__(self, value: int) -> None: ...


class ByteLen:
    min_bytes: int | None
    max_bytes: int | None
    exact: int | None
    def __init__(self, min_bytes: int | None = None, max_bytes: int | None = None, exact: int | None = None) -> None: ...


class Gt:
    value: Any
    def __init__(self, value: Any) -> None: ...


class Ge:
    value: Any
    def __init__(self, value: Any) -> None: ...


class Lt:
    value: Any
    def __init__(self, value: Any) -> None: ...


class Le:
    value: Any
    def __init__(self, value: Any) -> None: ...


class Range:
    min: Any | None
    max: Any | None
    min_inclusive: bool
    max_inclusive: bool
    def __init__(
        self,
        min: Any | None = None,
        max: Any | None = None,
        min_inclusive: bool = True,
        max_inclusive: bool = True,
    ) -> None: ...


class MultipleOf:
    value: Any
    def __init__(self, value: Any) -> None: ...


def Field(
    default: Any = ...,
    *,
    default_factory: Callable[[], Any] | Any = ...,
    min: Any | None = None,
    max: Any | None = None,
    min_inclusive: bool = True,
    max_inclusive: bool = True,
    ge: Any | None = None,
    gt: Any | None = None,
    le: Any | None = None,
    lt: Any | None = None,
    multiple_of: Any | None = None,
    min_len: int | None = None,
    max_len: int | None = None,
    len: int | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    length: int | None = None,
    min_bytes: int | None = None,
    max_bytes: int | None = None,
    bytes_len: int | None = None,
    byte_len: int | None = None,
    init: bool = True,
    repr: bool = True,
    hash: bool | None = None,
    compare: bool = True,
    metadata: Mapping[str, Any] | None = None,
    kw_only: bool = False,
) -> Any: ...


@overload
@dataclass_transform(kw_only_default=False, field_specifiers=(Field,))
def dataclass(_cls: type[_T], **kwargs: Any) -> type[_T]: ...


@overload
@dataclass_transform(kw_only_default=False, field_specifiers=(Field,))
def dataclass(_cls: None = None, **kwargs: Any) -> Callable[[type[_T]], type[_T]]: ...


@dataclass_transform(kw_only_default=False, field_specifiers=(Field,))
class DataModel:
    model: ClassVar[_ModelAccessor[Self]]


ModelPayload: TypeAlias = _PydanticBaseModel | DataModel | _DataclassInstance


def is_data_model_type(value: Any) -> bool: ...
def is_data_model_instance(value: Any) -> bool: ...
def is_pydantic_model_type(value: Any) -> bool: ...
def is_pydantic_model_instance(value: Any) -> bool: ...
def is_dataclass_model_type(value: Any) -> bool: ...
def is_dataclass_model_instance(value: Any) -> bool: ...
def is_model_type(value: Any) -> bool: ...
def is_model_instance(value: Any) -> bool: ...
def model_kind(value: Any) -> str: ...
def model_schema_kind(value: Any) -> int: ...
def model_schema_name(value: Any) -> str: ...
def model_validate(model_class: type[_T], obj: Any, **kwargs: Any) -> _T: ...
def model_validate_instance(obj: Any) -> None: ...
def model_validate_dump(obj: Any) -> dict[str, Any]: ...
def model_dump(obj: Any) -> dict[str, Any]: ...
