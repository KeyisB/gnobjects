from __future__ import annotations

import copy as _copy
import types
from dataclasses import MISSING, dataclass as _stdlib_dataclass
from dataclasses import fields as _dataclass_fields
from dataclasses import is_dataclass
from functools import lru_cache
from typing import Any, Callable, TYPE_CHECKING, TypeAlias, TypeVar, Union, get_args, get_origin, get_type_hints, overload
from typing import Annotated, Literal

from pydantic import BaseModel as _PydanticBaseModel
from pydantic import TypeAdapter

if TYPE_CHECKING:
    from _typeshed import DataclassInstance as _DataclassInstance
else:
    _DataclassInstance = Any


_T = TypeVar("_T")
_FAST_MODEL_ATTR = "__gn_fast_data_model__"

MODEL_SCHEMA_KIND_UNKNOWN = 0
MODEL_SCHEMA_KIND_GN_FAST_DATAMODEL = 1
MODEL_SCHEMA_KIND_PYTHON_DATACLASS = 2
MODEL_SCHEMA_KIND_PYDANTIC_BASEMODEL = 3
MODEL_SCHEMA_KIND_PYDANTIC_TYPEADAPTER = 4

MODEL_SCHEMA_KIND_NAMES = {
    MODEL_SCHEMA_KIND_UNKNOWN: "unknown",
    MODEL_SCHEMA_KIND_GN_FAST_DATAMODEL: "gn:FastDataModel",
    MODEL_SCHEMA_KIND_PYTHON_DATACLASS: "python:dataclass",
    MODEL_SCHEMA_KIND_PYDANTIC_BASEMODEL: "pydantic:BaseModel",
    MODEL_SCHEMA_KIND_PYDANTIC_TYPEADAPTER: "pydantic:TypeAdapter",
}


class FastDataModelValidationError(ValueError):
    pass


class _ModelAccessor:
    __slots__ = ("_inst",)

    def __init__(self, inst: Any) -> None:
        self._inst = inst

    def dump(self) -> dict[str, Any]:
        return model_dump(self._inst)

    def dump_json(self, **kwargs: Any) -> str:
        data = _adapter_for(type(self._inst)).dump_json(self._inst, **kwargs)
        return data.decode("utf-8")

    def copy(self, *, update: dict[str, Any] | None = None, deep: bool = False) -> Any:
        data = model_dump(self._inst)
        if deep:
            data = _copy.deepcopy(data)
        if update:
            data.update(update)
        return type(self._inst)(**data)

    @property
    def fields_set(self) -> set[str]:
        if isinstance(self._inst, _PydanticBaseModel):
            return set(self._inst.model_fields_set)
        return {f.name for f in _dataclass_fields(self._inst)}

    @staticmethod
    def validate(model_class: type[_T], obj: Any, **kwargs: Any) -> _T:
        return model_validate(model_class, obj, **kwargs)

    @staticmethod
    def validate_json(model_class: type[_T], json_data: str | bytes | bytearray, **kwargs: Any) -> _T:
        return _adapter_for(model_class).validate_json(json_data, **kwargs)

    @staticmethod
    def validate_strings(model_class: type[_T], obj: Any, **kwargs: Any) -> _T:
        return _adapter_for(model_class).validate_strings(obj, **kwargs)

    @staticmethod
    def schema(model_class: type, **kwargs: Any) -> dict[str, Any]:
        return _adapter_for(model_class).json_schema(**kwargs)

    @staticmethod
    def rebuild(model_class: type, **kwargs: Any) -> bool | None:
        rebuild = getattr(_adapter_for(model_class), "rebuild", None)
        return rebuild(**kwargs) if callable(rebuild) else None

    @staticmethod
    def fields(model_class: type) -> Any:
        if is_pydantic_model_type(model_class):
            return model_class.model_fields
        return _dataclass_fields(model_class)

    @staticmethod
    def computed_fields(model_class: type) -> dict[str, Any]:
        if is_pydantic_model_type(model_class):
            return model_class.model_computed_fields
        return {}

    @staticmethod
    def config(model_class: type) -> dict[str, Any]:
        if is_pydantic_model_type(model_class):
            return model_class.model_config
        return {}


ModelPayload: TypeAlias = _PydanticBaseModel | _DataclassInstance


def _attach_model_accessor(model_class: type[_T]) -> type[_T]:
    if "model" not in getattr(model_class, "__dataclass_fields__", {}):
        setattr(model_class, "model", property(lambda self: _ModelAccessor(self)))
    return model_class


@overload
def dataclass(_cls: type[_T], **kwargs: Any) -> type[_T]: ...


@overload
def dataclass(_cls: None = None, **kwargs: Any) -> Callable[[type[_T]], type[_T]]: ...


def dataclass(_cls: type[_T] | None = None, **kwargs: Any):
    kwargs.setdefault("slots", True)

    def wrap(cls: type[_T]) -> type[_T]:
        return _attach_model_accessor(_stdlib_dataclass(cls, **kwargs))

    if _cls is None:
        return wrap
    return wrap(_cls)


@overload
def FastDataModel(_cls: type[_T], **kwargs: Any) -> type[_T]: ...


@overload
def FastDataModel(_cls: None = None, **kwargs: Any) -> Callable[[type[_T]], type[_T]]: ...


def FastDataModel(_cls: type[_T] | None = None, **kwargs: Any):
    kwargs.setdefault("slots", True)

    def wrap(cls: type[_T]) -> type[_T]:
        model_class = _attach_model_accessor(_stdlib_dataclass(cls, **kwargs))
        setattr(model_class, _FAST_MODEL_ATTR, True)
        return model_class

    if _cls is None:
        return wrap
    return wrap(_cls)


BaseModel = dataclass


def is_fast_model_type(value: Any) -> bool:
    return isinstance(value, type) and bool(getattr(value, _FAST_MODEL_ATTR, False))


def is_fast_model_instance(value: Any) -> bool:
    return not isinstance(value, type) and bool(getattr(type(value), _FAST_MODEL_ATTR, False))


def is_pydantic_model_type(value: Any) -> bool:
    try:
        return isinstance(value, type) and issubclass(value, _PydanticBaseModel)
    except TypeError:
        return False


def is_pydantic_model_instance(value: Any) -> bool:
    return isinstance(value, _PydanticBaseModel)


def is_dataclass_model_type(value: Any) -> bool:
    return isinstance(value, type) and is_dataclass(value)


def is_dataclass_model_instance(value: Any) -> bool:
    return not isinstance(value, type) and is_dataclass(value)


def is_model_type(value: Any) -> bool:
    return is_pydantic_model_type(value) or is_dataclass_model_type(value)


def is_model_instance(value: Any) -> bool:
    return is_pydantic_model_instance(value) or is_dataclass_model_instance(value)


def model_kind(value: Any) -> str:
    model_type = value if isinstance(value, type) else type(value)
    if is_fast_model_type(model_type):
        return "fast"
    if is_pydantic_model_type(model_type):
        return "pydantic"
    if is_dataclass_model_type(model_type):
        return "dataclass"
    raise TypeError(f"Unsupported model type: {model_type!r}")


def model_schema_kind(value: Any) -> int:
    model_type = value if isinstance(value, type) else type(value)
    if is_fast_model_type(model_type):
        return MODEL_SCHEMA_KIND_GN_FAST_DATAMODEL
    if is_pydantic_model_type(model_type):
        return MODEL_SCHEMA_KIND_PYDANTIC_BASEMODEL
    if is_dataclass_model_type(model_type):
        return MODEL_SCHEMA_KIND_PYTHON_DATACLASS
    raise TypeError(f"Unsupported model type: {model_type!r}")


def model_schema_name(value: Any) -> str:
    model_type = value if isinstance(value, type) else type(value)
    if not is_model_type(model_type):
        raise TypeError(f"Unsupported model type: {model_type!r}")
    module = getattr(model_type, "__module__", "")
    qualname = getattr(model_type, "__qualname__", model_type.__name__)
    if module and module != "builtins":
        return f"{module}.{qualname}"
    return qualname


@lru_cache(maxsize=2048)
def _adapter_for(model_class: type) -> TypeAdapter:
    return TypeAdapter(model_class)


@lru_cache(maxsize=2048)
def _fast_fields_for(model_class: type) -> tuple[tuple[str, Any, Any, Any, Callable[[Any], bool], str], ...]:
    try:
        type_hints = get_type_hints(model_class)
    except Exception:
        type_hints = getattr(model_class, "__annotations__", {})
    result = []
    for field in _dataclass_fields(model_class):
        annotation = type_hints.get(field.name, field.type)
        checker = _compile_fast_checker(annotation)
        result.append((
            field.name,
            annotation,
            field.default,
            field.default_factory,
            checker,
            _type_name(annotation),
        ))
    return tuple(result)


def model_validate(model_class: type[_T], obj: Any, **kwargs: Any) -> _T:
    if is_fast_model_type(model_class):
        return _fast_model_validate(model_class, obj)
    if is_pydantic_model_type(model_class):
        return model_class.model_validate(obj, **kwargs)
    return _adapter_for(model_class).validate_python(obj, **kwargs)


def model_dump(obj: Any) -> dict[str, Any]:
    if is_pydantic_model_instance(obj):
        return obj.model_dump()
    if is_fast_model_instance(obj):
        return _dataclass_shallow_dump(obj)
    if is_dataclass_model_instance(obj):
        return {
            field.name: _to_serializable(getattr(obj, field.name))
            for field in _dataclass_fields(obj)
        }
    raise TypeError(f"Expected model instance, got {type(obj).__name__}")


def model_validate_instance(obj: Any) -> None:
    if is_fast_model_instance(obj):
        _fast_model_validate_instance(obj)


def model_validate_dump(obj: Any) -> dict[str, Any]:
    if is_pydantic_model_instance(obj):
        return obj.model_dump()
    if is_fast_model_instance(obj):
        return _fast_model_dump_checked(obj)
    if is_dataclass_model_instance(obj):
        return {
            field.name: _to_serializable(getattr(obj, field.name))
            for field in _dataclass_fields(obj)
        }
    raise TypeError(f"Expected model instance, got {type(obj).__name__}")


def _dataclass_shallow_dump(obj: Any) -> dict[str, Any]:
    data = {}
    for field in _dataclass_fields(obj):
        value = getattr(obj, field.name)
        _raise_if_nested_model(field.name, value)
        data[field.name] = value
    return data


def _fast_model_validate(model_class: type[_T], obj: Any) -> _T:
    if not isinstance(obj, dict):
        raise FastDataModelValidationError(f"{model_class.__name__} expects dict payload")

    values: dict[str, Any] = {}
    for name, annotation, default, default_factory, checker, type_name in _fast_fields_for(model_class):
        if name in obj:
            value = obj[name]
        elif default is not MISSING:
            value = default
        elif default_factory is not MISSING:
            value = default_factory()
        else:
            raise FastDataModelValidationError(f"Missing required field '{name}'")

        _raise_if_nested_model(name, value)
        if not checker(value):
            raise FastDataModelValidationError(
                f"Field '{name}' expected {type_name}, got {type(value).__name__}"
            )
        values[name] = value

    return model_class(**values)


def _fast_model_validate_instance(obj: Any) -> None:
    for name, annotation, _default, _default_factory, checker, type_name in _fast_fields_for(type(obj)):
        value = getattr(obj, name)
        _raise_if_nested_model(name, value)
        if not checker(value):
            raise FastDataModelValidationError(
                f"Field '{name}' expected {type_name}, got {type(value).__name__}"
            )


def _fast_model_dump_checked(obj: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for name, annotation, _default, _default_factory, checker, type_name in _fast_fields_for(type(obj)):
        value = getattr(obj, name)
        _raise_if_nested_model(name, value)
        if not checker(value):
            raise FastDataModelValidationError(
                f"Field '{name}' expected {type_name}, got {type(value).__name__}"
            )
        data[name] = value
    return data


def _compile_fast_checker(annotation: Any) -> Callable[[Any], bool]:
    if annotation is Any:
        return _always_true
    if isinstance(annotation, str):
        return _always_true
    if annotation is None or annotation is type(None):
        return lambda value: value is None

    origin = get_origin(annotation)
    if origin is Annotated:
        args = get_args(annotation)
        return _compile_fast_checker(args[0]) if args else _always_true
    if origin is Literal:
        args = get_args(annotation)
        return lambda value: value in args
    if origin in (Union, types.UnionType):
        checkers = tuple(_compile_fast_checker(arg) for arg in get_args(annotation))
        return lambda value: any(checker(value) for checker in checkers)

    if origin is not None:
        return _origin_checker(origin)

    if annotation is int:
        return lambda value: isinstance(value, int) and not isinstance(value, bool)
    if annotation is float:
        return lambda value: isinstance(value, float)
    if annotation is bool:
        return lambda value: isinstance(value, bool)
    if isinstance(annotation, type):
        return lambda value: isinstance(value, annotation)
    return _always_true


def _always_true(_value: Any) -> bool:
    return True


def _origin_checker(origin: Any) -> Callable[[Any], bool]:
    try:
        isinstance(None, origin)
    except TypeError:
        return _always_true
    return lambda value: isinstance(value, origin)


def _fast_type_ok(value: Any, annotation: Any) -> bool:
    return _compile_fast_checker(annotation)(value)


def _type_name(annotation: Any) -> str:
    name = getattr(annotation, "__name__", None)
    return name if name is not None else str(annotation)


def _raise_if_nested_model(field_name: str, value: Any) -> None:
    if is_model_instance(value):
        raise FastDataModelValidationError(
            f"Field '{field_name}' nested model payload is not supported"
        )


def _to_serializable(value: Any) -> Any:
    if is_model_instance(value):
        return model_dump(value)
    if isinstance(value, list):
        return [_to_serializable(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_to_serializable(v) for v in value)
    if isinstance(value, set):
        return {_to_serializable(v) for v in value}
    if isinstance(value, dict):
        return {k: _to_serializable(v) for k, v in value.items()}
    return value
