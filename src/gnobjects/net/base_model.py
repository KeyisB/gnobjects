from __future__ import annotations

import copy as _copy
import types
from dataclasses import MISSING, dataclass as _stdlib_dataclass
from dataclasses import field as _stdlib_field
from dataclasses import fields as _dataclass_fields
from dataclasses import is_dataclass
from functools import lru_cache
from typing import Any, Callable, Mapping, TYPE_CHECKING, TypeAlias, TypeVar, Union, get_args, get_origin, get_type_hints, overload
from typing import Annotated, Literal

from pydantic import BaseModel as _PydanticBaseModel
from pydantic import TypeAdapter

if TYPE_CHECKING:
    from _typeshed import DataclassInstance as _DataclassInstance
else:
    _DataclassInstance = Any


_T = TypeVar("_T")
_DATA_MODEL_ATTR = "__gn_data_model__"
_MODEL_SCHEMA_KIND_ATTR = "__gn_model_schema_kind__"
_MODEL_SCHEMA_NAME_ATTR = "__gn_model_schema_name__"
_FIELD_METADATA_KEY = "gn_data_model_field"

MODEL_SCHEMA_KIND_UNKNOWN = 0
MODEL_SCHEMA_KIND_GN_DATAMODEL = 1
MODEL_SCHEMA_KIND_PYTHON_DATACLASS = 2
MODEL_SCHEMA_KIND_PYDANTIC_BASEMODEL = 3
MODEL_SCHEMA_KIND_PYDANTIC_TYPEADAPTER = 4

MODEL_SCHEMA_KIND_NAMES = {
    MODEL_SCHEMA_KIND_UNKNOWN: "unknown",
    MODEL_SCHEMA_KIND_GN_DATAMODEL: "gn:DataModel",
    MODEL_SCHEMA_KIND_PYTHON_DATACLASS: "python:dataclass",
    MODEL_SCHEMA_KIND_PYDANTIC_BASEMODEL: "pydantic:BaseModel",
    MODEL_SCHEMA_KIND_PYDANTIC_TYPEADAPTER: "pydantic:TypeAdapter",
}


class DataModelError(Exception):
    __slots__ = ("detail",)
    code = "data_model_error"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class DataModelDefinitionError(DataModelError):
    code = "data_model_definition_error"


class DataModelFieldError(DataModelError):
    code = "data_model_field_error"


class DataModelSchemaError(DataModelError):
    code = "data_model_schema_error"


class DataModelUsageError(DataModelError):
    code = "data_model_usage_error"


class DataModelValidationError(DataModelError):
    code = "data_model_validation_error"


@_stdlib_dataclass(frozen=True, slots=True)
class MinLen:
    value: int

    def __post_init__(self) -> None:
        _validate_non_negative_int("MinLen.value", self.value)

    @property
    def min_length(self) -> int:
        return self.value


@_stdlib_dataclass(frozen=True, slots=True)
class MaxLen:
    value: int

    def __post_init__(self) -> None:
        _validate_non_negative_int("MaxLen.value", self.value)

    @property
    def max_length(self) -> int:
        return self.value


@_stdlib_dataclass(frozen=True, slots=True)
class Len:
    min_length: int | None = None
    max_length: int | None = None
    exact: int | None = None

    def __post_init__(self) -> None:
        _validate_length_bounds("Len", self.min_length, self.max_length, self.exact)


@_stdlib_dataclass(frozen=True, slots=True)
class MinBytes:
    value: int

    def __post_init__(self) -> None:
        _validate_non_negative_int("MinBytes.value", self.value)


@_stdlib_dataclass(frozen=True, slots=True)
class MaxBytes:
    value: int

    def __post_init__(self) -> None:
        _validate_non_negative_int("MaxBytes.value", self.value)


@_stdlib_dataclass(frozen=True, slots=True)
class ByteLen:
    min_bytes: int | None = None
    max_bytes: int | None = None
    exact: int | None = None

    def __post_init__(self) -> None:
        _validate_length_bounds("ByteLen", self.min_bytes, self.max_bytes, self.exact)


@_stdlib_dataclass(frozen=True, slots=True)
class Gt:
    value: Any


@_stdlib_dataclass(frozen=True, slots=True)
class Ge:
    value: Any


@_stdlib_dataclass(frozen=True, slots=True)
class Lt:
    value: Any


@_stdlib_dataclass(frozen=True, slots=True)
class Le:
    value: Any


@_stdlib_dataclass(frozen=True, slots=True)
class Range:
    min: Any | None = None
    max: Any | None = None
    min_inclusive: bool = True
    max_inclusive: bool = True

    def __post_init__(self) -> None:
        if self.min is None and self.max is None:
            raise DataModelFieldError("Range requires min or max")
        if not isinstance(self.min_inclusive, bool):
            raise DataModelFieldError(
                f"Range.min_inclusive must be bool, got {type(self.min_inclusive).__name__}"
            )
        if not isinstance(self.max_inclusive, bool):
            raise DataModelFieldError(
                f"Range.max_inclusive must be bool, got {type(self.max_inclusive).__name__}"
            )
        if self.min is not None and self.max is not None:
            try:
                invalid = self.min > self.max or (
                    self.min == self.max and not (self.min_inclusive and self.max_inclusive)
                )
            except TypeError as exc:
                raise DataModelFieldError(
                    f"Range min and max must be comparable, got "
                    f"{type(self.min).__name__} and {type(self.max).__name__}"
                ) from exc
            if invalid:
                raise DataModelFieldError(
                    f"Range min must be <= max, got min={self.min!r}, max={self.max!r}; "
                    "equal bounds must both be inclusive"
                )


@_stdlib_dataclass(frozen=True, slots=True)
class MultipleOf:
    value: Any

    def __post_init__(self) -> None:
        if self.value == 0:
            raise DataModelFieldError("MultipleOf.value must not be 0")


@_stdlib_dataclass(frozen=True, slots=True)
class _FieldInfo:
    constraints: tuple[Any, ...]


def Field(
    default: Any = MISSING,
    *,
    default_factory: Callable[[], Any] | Any = MISSING,
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
    kw_only: bool | Any = MISSING,
) -> Any:
    exact_len = _coalesce_alias("len", len, "length", length)
    exact_bytes = _coalesce_alias("bytes_len", bytes_len, "byte_len", byte_len)
    min_len = _coalesce_alias("min_len", min_len, "min_length", min_length)
    max_len = _coalesce_alias("max_len", max_len, "max_length", max_length)

    constraints: list[Any] = []
    if min is not None or max is not None:
        constraints.append(Range(min, max, min_inclusive, max_inclusive))
    if ge is not None:
        constraints.append(Ge(ge))
    if gt is not None:
        constraints.append(Gt(gt))
    if le is not None:
        constraints.append(Le(le))
    if lt is not None:
        constraints.append(Lt(lt))
    if multiple_of is not None:
        constraints.append(MultipleOf(multiple_of))
    if min_len is not None or max_len is not None or exact_len is not None:
        constraints.append(Len(min_len, max_len, exact_len))
    if min_bytes is not None or max_bytes is not None or exact_bytes is not None:
        constraints.append(ByteLen(min_bytes, max_bytes, exact_bytes))

    field_metadata = dict(metadata or {})
    field_metadata[_FIELD_METADATA_KEY] = _FieldInfo(tuple(constraints))

    kwargs = {
        "default": default,
        "default_factory": default_factory,
        "init": init,
        "repr": repr,
        "hash": hash,
        "compare": compare,
        "metadata": field_metadata,
    }
    if kw_only is not MISSING:
        kwargs["kw_only"] = kw_only
    return _stdlib_field(**kwargs)


class _ModelAccessor:
    __slots__ = ("_inst", "_model_class")

    def __init__(self, inst: Any = None, model_class: type | None = None) -> None:
        self._inst = inst
        self._model_class = model_class if model_class is not None else type(inst)

    def _require_instance(self) -> Any:
        if self._inst is None:
            raise DataModelUsageError("This model operation requires a model instance")
        return self._inst

    def _require_model_class(self) -> type:
        if self._model_class is None:
            raise DataModelUsageError("This model operation requires a model class")
        return self._model_class

    def dump(self) -> dict[str, Any]:
        return model_validate_dump(self._require_instance())

    def toDict(self) -> dict[str, Any]:
        return self.dump()

    def fromDict(self, obj: Any, **kwargs: Any) -> Any:
        return model_validate(self._require_model_class(), obj, **kwargs)

    def copy(self, *, update: dict[str, Any] | None = None, deep: bool = False) -> Any:
        inst = self._require_instance()
        data = model_validate_dump(inst)
        if deep:
            data = _copy.deepcopy(data)
        if update:
            data.update(update)
        return model_validate(type(inst), data)

    @property
    def fields_set(self) -> set[str]:
        inst = self._require_instance()
        if isinstance(inst, _PydanticBaseModel):
            return set(inst.model_fields_set)
        return {f.name for f in _dataclass_fields(inst)}

    @staticmethod
    def validate(model_class: type[_T], obj: Any, **kwargs: Any) -> _T:
        return model_validate(model_class, obj, **kwargs)

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


class _ModelAccessorDescriptor:
    __slots__ = ()

    def __get__(self, inst: Any, owner: type | None = None) -> _ModelAccessor:
        return _ModelAccessor(inst, owner if owner is not None else type(inst))


def _attach_model_accessor(model_class: type[_T]) -> type[_T]:
    if "model" not in getattr(model_class, "__dataclass_fields__", {}):
        setattr(model_class, "model", _ModelAccessorDescriptor())
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


_DATA_MODEL_DATACLASS_KWARGS = frozenset((
    "init",
    "repr",
    "eq",
    "order",
    "unsafe_hash",
    "frozen",
    "match_args",
    "kw_only",
    "slots",
    "weakref_slot",
))


class _DataModelMeta(type):
    def __new__(
        mcls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> type:
        cls = super().__new__(mcls, name, bases, namespace)
        if not any(isinstance(base, _DataModelMeta) for base in bases):
            return cls

        if "__dataclass_fields__" in namespace:
            setattr(cls, _DATA_MODEL_ATTR, True)
            return cls

        _validate_data_model_namespace(name, bases, namespace, kwargs)

        dataclass_kwargs = dict(kwargs)
        dataclass_kwargs["slots"] = True
        try:
            model_class = _stdlib_dataclass(cls, **dataclass_kwargs)
        except (TypeError, ValueError) as exc:
            raise DataModelDefinitionError(
                f"{name} DataModel dataclass(slots=True) build failed: {exc}"
            ) from exc
        setattr(model_class, _DATA_MODEL_ATTR, True)
        _warm_data_model_class(model_class)
        return model_class


class DataModel(metaclass=_DataModelMeta):
    __slots__ = ()
    model = _ModelAccessorDescriptor()


ModelPayload: TypeAlias = _PydanticBaseModel | DataModel | _DataclassInstance


def _validate_data_model_namespace(
    name: str,
    bases: tuple[type, ...],
    namespace: dict[str, Any],
    kwargs: dict[str, Any],
) -> None:
    unknown = tuple(key for key in kwargs if key not in _DATA_MODEL_DATACLASS_KWARGS)
    if unknown:
        raise DataModelDefinitionError(
            f"{name} got unsupported DataModel option(s): {', '.join(unknown)}"
        )
    if kwargs.get("slots", True) is not True:
        raise DataModelDefinitionError(f"{name} must use slots=True")
    if "__slots__" in namespace:
        raise DataModelDefinitionError(
            f"{name} must not define __slots__; DataModel always uses slots=True"
        )
    if len(bases) != 1:
        raise DataModelDefinitionError(f"{name} supports only single DataModel inheritance")
    annotations = namespace.get("__annotations__", {})
    if "model" in namespace or "model" in annotations:
        raise DataModelDefinitionError(f"{name}.model is reserved for DataModel helpers")


def _warm_data_model_class(model_class: type) -> None:
    setattr(model_class, _MODEL_SCHEMA_KIND_ATTR, MODEL_SCHEMA_KIND_GN_DATAMODEL)
    setattr(model_class, _MODEL_SCHEMA_NAME_ATTR, _model_schema_name_for(model_class))
    fields_for = globals().get("_data_model_fields_for")
    if fields_for is not None:
        try:
            fields_for(model_class)
        except Exception:
            # Best-effort warm-up only. At class-creation time the class name is
            # not yet bound in its module, so self/forward references cannot be
            # resolved by get_type_hints yet. lru_cache does not store failures,
            # so the field set (and its validators) is compiled lazily on first
            # use, once the references resolve. Validation must never be silently
            # degraded here.
            pass


def is_data_model_type(value: Any) -> bool:
    return isinstance(value, type) and bool(getattr(value, _DATA_MODEL_ATTR, False))


def is_data_model_instance(value: Any) -> bool:
    return not isinstance(value, type) and bool(getattr(type(value), _DATA_MODEL_ATTR, False))


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
    if is_data_model_type(model_type):
        return "data"
    if is_pydantic_model_type(model_type):
        return "pydantic"
    if is_dataclass_model_type(model_type):
        return "dataclass"
    raise DataModelUsageError(f"Unsupported model type: {model_type!r}")


def model_schema_kind(value: Any) -> int:
    model_type = value if isinstance(value, type) else type(value)
    return _model_schema_kind_for(model_type)


@lru_cache(maxsize=2048)
def _model_schema_kind_for(model_type: type) -> int:
    cached = getattr(model_type, _MODEL_SCHEMA_KIND_ATTR, None)
    if isinstance(cached, int):
        return cached
    if is_data_model_type(model_type):
        return MODEL_SCHEMA_KIND_GN_DATAMODEL
    if is_pydantic_model_type(model_type):
        return MODEL_SCHEMA_KIND_PYDANTIC_BASEMODEL
    if is_dataclass_model_type(model_type):
        return MODEL_SCHEMA_KIND_PYTHON_DATACLASS
    raise DataModelUsageError(f"Unsupported model type: {model_type!r}")


def model_schema_name(value: Any) -> str:
    model_type = value if isinstance(value, type) else type(value)
    return _model_schema_name_for(model_type)


@lru_cache(maxsize=2048)
def _model_schema_name_for(model_type: type) -> str:
    cached = getattr(model_type, _MODEL_SCHEMA_NAME_ATTR, None)
    if isinstance(cached, str):
        return cached
    if not is_model_type(model_type):
        raise DataModelUsageError(f"Unsupported model type: {model_type!r}")
    module = getattr(model_type, "__module__", "")
    qualname = getattr(model_type, "__qualname__", model_type.__name__)
    if module and module != "builtins":
        return f"{module}.{qualname}"
    return qualname


@lru_cache(maxsize=2048)
def _adapter_for(model_class: type) -> TypeAdapter:
    return TypeAdapter(model_class)


@lru_cache(maxsize=2048)
def _data_model_fields_for(model_class: type) -> tuple[tuple[str, Any, Any, Any, Callable[[Any], bool], str], ...]:
    try:
        type_hints = get_type_hints(model_class, include_extras=True)
    except Exception as exc:
        raise DataModelSchemaError(
            f"Cannot resolve type hints for {model_class.__name__}: {exc}. "
            f"Every annotation must be resolvable at validation time. Forward and "
            f"self references declared at module scope resolve automatically; "
            f"names that exist only under 'if TYPE_CHECKING' or that are "
            f"misspelled fail here instead of silently disabling validation."
        ) from exc
    result = []
    for field in _dataclass_fields(model_class):
        annotation = type_hints.get(field.name, field.type)
        checker = _compile_data_checker(annotation)
        constraints = _field_constraints(field)
        if constraints:
            constraint_checkers = tuple(
                checker
                for checker in (_compile_constraint_checker(item) for item in constraints)
                if checker is not None
            )
            if constraint_checkers:
                checker = _combine_checkers(checker, constraint_checkers)
        type_name = _type_name(annotation)
        if constraints:
            type_name = _append_constraint_names(type_name, constraints)
        result.append((
            field.name,
            annotation,
            field.default,
            field.default_factory,
            checker,
            type_name,
        ))
    return tuple(result)


def model_validate(model_class: type[_T], obj: Any, **kwargs: Any) -> _T:
    if is_data_model_type(model_class):
        return _data_model_validate(model_class, obj)
    if is_pydantic_model_type(model_class):
        return model_class.model_validate(obj, **kwargs)
    return _adapter_for(model_class).validate_python(obj, **kwargs)


def model_dump(obj: Any) -> dict[str, Any]:
    if is_pydantic_model_instance(obj):
        return obj.model_dump()
    if is_data_model_instance(obj):
        return _dataclass_shallow_dump(obj)
    if is_dataclass_model_instance(obj):
        return {
            field.name: _to_serializable(getattr(obj, field.name))
            for field in _dataclass_fields(obj)
        }
    raise DataModelUsageError(f"Expected model instance, got {type(obj).__name__}")


def model_validate_instance(obj: Any) -> None:
    if is_data_model_instance(obj):
        _data_model_validate_instance(obj)


def model_validate_dump(obj: Any) -> dict[str, Any]:
    if is_pydantic_model_instance(obj):
        return obj.model_dump()
    if is_data_model_instance(obj):
        return _data_model_dump_checked(obj)
    if is_dataclass_model_instance(obj):
        return {
            field.name: _to_serializable(getattr(obj, field.name))
            for field in _dataclass_fields(obj)
        }
    raise DataModelUsageError(f"Expected model instance, got {type(obj).__name__}")


def _dataclass_shallow_dump(obj: Any) -> dict[str, Any]:
    data = {}
    for field in _dataclass_fields(obj):
        value = getattr(obj, field.name)
        _raise_if_nested_model(field.name, value)
        data[field.name] = value
    return data


def _data_model_validate(model_class: type[_T], obj: Any) -> _T:
    if not isinstance(obj, dict):
        raise DataModelValidationError(
            f"{model_class.__name__} expects dict payload, got {type(obj).__name__}"
        )

    values: dict[str, Any] = {}
    for name, annotation, default, default_factory, checker, type_name in _data_model_fields_for(model_class):
        if name in obj:
            value = obj[name]
        elif default is not MISSING:
            value = default
        elif default_factory is not MISSING:
            value = default_factory()
        else:
            raise DataModelValidationError(
                f"{model_class.__name__}.{name} is required and missing from payload"
            )

        _raise_if_nested_model(name, value)
        if not checker(value):
            raise DataModelValidationError(
                f"{model_class.__name__}.{name} expected {type_name}, "
                f"got {type(value).__name__}"
            )
        values[name] = value

    return model_class(**values)


def _data_model_validate_instance(obj: Any) -> None:
    for name, annotation, _default, _default_factory, checker, type_name in _data_model_fields_for(type(obj)):
        value = getattr(obj, name)
        _raise_if_nested_model(name, value)
        if not checker(value):
            raise DataModelValidationError(
                f"{type(obj).__name__}.{name} expected {type_name}, "
                f"got {type(value).__name__}"
            )


def _data_model_dump_checked(obj: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for name, annotation, _default, _default_factory, checker, type_name in _data_model_fields_for(type(obj)):
        value = getattr(obj, name)
        _raise_if_nested_model(name, value)
        if not checker(value):
            raise DataModelValidationError(
                f"{type(obj).__name__}.{name} expected {type_name}, "
                f"got {type(value).__name__}"
            )
        data[name] = value
    return data


def _compile_data_checker(annotation: Any) -> Callable[[Any], bool]:
    if annotation is Any:
        return _always_true
    if isinstance(annotation, str):
        return _always_true
    if annotation is None or annotation is type(None):
        return lambda value: value is None

    origin = get_origin(annotation)
    if origin is Annotated:
        args = get_args(annotation)
        if not args:
            return _always_true
        base_checker = _compile_data_checker(args[0])
        constraint_checkers = tuple(
            checker
            for checker in (_compile_constraint_checker(item) for item in _iter_constraint_metadata(args[1:]))
            if checker is not None
        )
        if not constraint_checkers:
            return base_checker
        return _combine_checkers(base_checker, constraint_checkers)
    if origin is Literal:
        args = get_args(annotation)
        return lambda value: value in args
    if origin in (Union, types.UnionType):
        checkers = tuple(_compile_data_checker(arg) for arg in get_args(annotation))
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


def _combine_checkers(
    base_checker: Callable[[Any], bool],
    constraint_checkers: tuple[Callable[[Any], bool], ...],
) -> Callable[[Any], bool]:
    def check(value: Any) -> bool:
        if not base_checker(value):
            return False
        for checker in constraint_checkers:
            if not checker(value):
                return False
        return True
    return check


def _origin_checker(origin: Any) -> Callable[[Any], bool]:
    try:
        isinstance(None, origin)
    except TypeError:
        return _always_true
    return lambda value: isinstance(value, origin)


def _data_model_type_ok(value: Any, annotation: Any) -> bool:
    return _compile_data_checker(annotation)(value)


def _type_name(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin is Annotated:
        args = get_args(annotation)
        if not args:
            return "Annotated"
        base_name = _type_name(args[0])
        constraints = tuple(
            name
            for name in (_constraint_name(item) for item in _iter_constraint_metadata(args[1:]))
            if name is not None
        )
        if constraints:
            return f"{base_name}[{', '.join(constraints)}]"
        return base_name
    name = getattr(annotation, "__name__", None)
    return name if name is not None else str(annotation)


def _compile_constraint_checker(item: Any) -> Callable[[Any], bool] | None:
    if isinstance(item, ByteLen):
        return _byte_len_checker(item.min_bytes, item.max_bytes, item.exact)
    if isinstance(item, MinBytes):
        return _byte_len_checker(item.value, None, None)
    if isinstance(item, MaxBytes):
        return _byte_len_checker(None, item.value, None)
    if isinstance(item, Len):
        return _len_checker(item.min_length, item.max_length, item.exact)
    if isinstance(item, MinLen):
        return _len_checker(item.value, None, None)
    if isinstance(item, MaxLen):
        return _len_checker(None, item.value, None)
    if isinstance(item, Range):
        return _range_checker(item.min, item.max, item.min_inclusive, item.max_inclusive)
    if isinstance(item, Ge):
        return _ge_checker(item.value)
    if isinstance(item, Gt):
        return _gt_checker(item.value)
    if isinstance(item, Le):
        return _le_checker(item.value)
    if isinstance(item, Lt):
        return _lt_checker(item.value)
    if isinstance(item, MultipleOf):
        return _multiple_of_checker(item.value)

    exact_length = getattr(item, "length", None)
    min_length = getattr(item, "min_length", None)
    max_length = getattr(item, "max_length", None)
    if exact_length is not None or min_length is not None or max_length is not None:
        return _len_checker(min_length, max_length, exact_length)

    ge = getattr(item, "ge", None)
    gt = getattr(item, "gt", None)
    le = getattr(item, "le", None)
    lt = getattr(item, "lt", None)
    multiple_of = getattr(item, "multiple_of", None)
    checkers = []
    if ge is not None:
        checkers.append(_ge_checker(ge))
    if gt is not None:
        checkers.append(_gt_checker(gt))
    if le is not None:
        checkers.append(_le_checker(le))
    if lt is not None:
        checkers.append(_lt_checker(lt))
    if multiple_of is not None:
        checkers.append(_multiple_of_checker(multiple_of))
    if not checkers:
        return None
    return _combine_checkers(_always_true, tuple(checkers))


def _iter_constraint_metadata(metadata: tuple[Any, ...] | list[Any]) -> tuple[Any, ...]:
    items: list[Any] = []
    for item in metadata:
        nested = getattr(item, "metadata", None)
        if nested:
            items.extend(_iter_constraint_metadata(tuple(nested)))
            continue
        items.append(item)
    return tuple(items)


def _len_checker(
    min_length: int | None,
    max_length: int | None,
    exact: int | None,
) -> Callable[[Any], bool]:
    _validate_length_bounds("Len", min_length, max_length, exact)

    def check(value: Any) -> bool:
        try:
            size = len(value)
        except TypeError:
            return False
        return _length_ok(size, min_length, max_length, exact)
    return check


def _byte_len_checker(
    min_bytes: int | None,
    max_bytes: int | None,
    exact: int | None,
) -> Callable[[Any], bool]:
    _validate_length_bounds("ByteLen", min_bytes, max_bytes, exact)

    def check(value: Any) -> bool:
        size = _byte_length(value)
        return size is not None and _length_ok(size, min_bytes, max_bytes, exact)
    return check


def _length_ok(
    size: int,
    min_value: int | None,
    max_value: int | None,
    exact: int | None,
) -> bool:
    if exact is not None:
        return size == exact
    if min_value is not None and size < min_value:
        return False
    if max_value is not None and size > max_value:
        return False
    return True


def _byte_length(value: Any) -> int | None:
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, (bytes, bytearray)):
        return len(value)
    if isinstance(value, memoryview):
        return value.nbytes
    return None


def _range_checker(
    min_value: Any | None,
    max_value: Any | None,
    min_inclusive: bool,
    max_inclusive: bool,
) -> Callable[[Any], bool]:
    return _combine_checkers(
        _always_true,
        tuple(
            checker
            for checker in (
                _ge_checker(min_value) if min_value is not None and min_inclusive else None,
                _gt_checker(min_value) if min_value is not None and not min_inclusive else None,
                _le_checker(max_value) if max_value is not None and max_inclusive else None,
                _lt_checker(max_value) if max_value is not None and not max_inclusive else None,
            )
            if checker is not None
        ),
    )


def _ge_checker(bound: Any) -> Callable[[Any], bool]:
    def check(value: Any) -> bool:
        try:
            return value >= bound
        except TypeError:
            return False
    return check


def _gt_checker(bound: Any) -> Callable[[Any], bool]:
    def check(value: Any) -> bool:
        try:
            return value > bound
        except TypeError:
            return False
    return check


def _le_checker(bound: Any) -> Callable[[Any], bool]:
    def check(value: Any) -> bool:
        try:
            return value <= bound
        except TypeError:
            return False
    return check


def _lt_checker(bound: Any) -> Callable[[Any], bool]:
    def check(value: Any) -> bool:
        try:
            return value < bound
        except TypeError:
            return False
    return check


def _multiple_of_checker(divisor: Any) -> Callable[[Any], bool]:
    if divisor == 0:
        raise DataModelFieldError("MultipleOf.value must not be 0")

    def check(value: Any) -> bool:
        try:
            return value % divisor == 0
        except (TypeError, ZeroDivisionError):
            return False
    return check


def _constraint_name(item: Any) -> str | None:
    if isinstance(item, (MinLen, MaxLen, Len, MinBytes, MaxBytes, ByteLen, Gt, Ge, Lt, Le, Range, MultipleOf)):
        return repr(item)

    exact_length = getattr(item, "length", None)
    min_length = getattr(item, "min_length", None)
    max_length = getattr(item, "max_length", None)
    if exact_length is not None or min_length is not None or max_length is not None:
        parts = []
        if exact_length is not None:
            parts.append(f"length={exact_length!r}")
        if min_length is not None:
            parts.append(f"min_length={min_length!r}")
        if max_length is not None:
            parts.append(f"max_length={max_length!r}")
        return "Len(" + ", ".join(parts) + ")"

    parts = []
    for attr in ("ge", "gt", "le", "lt", "multiple_of"):
        value = getattr(item, attr, None)
        if value is not None:
            parts.append(f"{attr}={value!r}")
    if parts:
        return "Range(" + ", ".join(parts) + ")"
    return None


def _append_constraint_names(type_name: str, constraints: tuple[Any, ...]) -> str:
    names = tuple(
        name
        for name in (_constraint_name(item) for item in _iter_constraint_metadata(constraints))
        if name is not None
    )
    if not names:
        return type_name
    return f"{type_name}[{', '.join(names)}]"


def _field_constraints(field: Any) -> tuple[Any, ...]:
    metadata = getattr(field, "metadata", None)
    if not metadata:
        return ()
    info = metadata.get(_FIELD_METADATA_KEY)
    if isinstance(info, _FieldInfo):
        return info.constraints
    if isinstance(info, tuple):
        return info
    return ()


def _coalesce_alias(primary_name: str, primary: Any, alias_name: str, alias: Any) -> Any:
    if primary is not None and alias is not None and primary != alias:
        raise DataModelFieldError(
            f"{primary_name} and {alias_name} cannot differ, "
            f"got {primary_name}={primary!r}, {alias_name}={alias!r}"
        )
    return primary if primary is not None else alias


def _validate_non_negative_int(name: str, value: Any) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DataModelFieldError(
            f"{name} must be a non-negative int, got {type(value).__name__} value={value!r}"
        )


def _validate_length_bounds(
    label: str,
    min_value: int | None,
    max_value: int | None,
    exact: int | None,
) -> None:
    if min_value is None and max_value is None and exact is None:
        raise DataModelFieldError(f"{label} requires at least one bound")
    if exact is not None:
        _validate_non_negative_int(f"{label}.exact", exact)
        if min_value is not None or max_value is not None:
            raise DataModelFieldError(f"{label}.exact cannot be combined with min/max")
        return
    if min_value is not None:
        _validate_non_negative_int(f"{label}.min", min_value)
    if max_value is not None:
        _validate_non_negative_int(f"{label}.max", max_value)
    if min_value is not None and max_value is not None and min_value > max_value:
        raise DataModelFieldError(
            f"{label}.min must be <= max, got min={min_value!r}, max={max_value!r}"
        )


def _raise_if_nested_model(field_name: str, value: Any) -> None:
    if is_model_instance(value):
        raise DataModelValidationError(
            f"Field '{field_name}' nested model payload is not supported, "
            f"got {type(value).__name__}"
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
