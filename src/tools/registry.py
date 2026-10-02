from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from src.tools.ticket_tool import TicketCategory, TicketPriority, create_support_ticket
from src.tools.timetable_tool import get_course_schedule


class ToolRegistryError(Exception):
    pass


class UnknownToolError(ToolRegistryError):
    pass


class ToolParameterError(ToolRegistryError):
    pass


class ToolMutationGuardError(ToolRegistryError):
    pass


@dataclass(frozen=True)
class ParamSpec:
    types: tuple[type, ...]
    required: bool = True
    allow_none: bool = False


@dataclass(frozen=True)
class ToolSpec:
    name: str
    handler: Callable[..., Any]
    params: Mapping[str, ParamSpec]
    mutates_database: bool = False
    confirmation_param: str | None = None


def _validate_params(spec: ToolSpec, params: Mapping[str, Any]) -> dict[str, Any]:
    unknown = set(params) - set(spec.params)
    if unknown:
        raise ToolParameterError(f"{spec.name}: unexpected parameter(s) {sorted(unknown)}")

    validated: dict[str, Any] = {}
    for param_name, param_spec in spec.params.items():
        if param_name not in params:
            if param_spec.required:
                raise ToolParameterError(f"{spec.name}: missing required parameter {param_name!r}")
            continue

        value = params[param_name]

        if value is None:
            if not param_spec.allow_none:
                raise ToolParameterError(f"{spec.name}: parameter {param_name!r} cannot be None")
            validated[param_name] = value
            continue

        if not isinstance(value, param_spec.types):
            raise ToolParameterError(
                f"{spec.name}: parameter {param_name!r} must be {param_spec.types}, "
                f"got {type(value).__name__}"
            )

        validated[param_name] = value

    return validated


def _enforce_mutation_guard(spec: ToolSpec, params: Mapping[str, Any]) -> None:
    if not spec.mutates_database or spec.confirmation_param is None:
        return

    if params.get(spec.confirmation_param) is not True:
        raise ToolMutationGuardError(
            f"{spec.name}: database mutation requires {spec.confirmation_param}=True"
        )


_REGISTRY: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> None:
    if spec.name in _REGISTRY:
        raise ToolRegistryError(f"Tool '{spec.name}' is already registered.")
    _REGISTRY[spec.name] = spec


def is_registered(tool_name: str) -> bool:
    return tool_name in _REGISTRY


def list_tools() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def tool_spec(tool_name: str) -> ToolSpec:
    spec = _REGISTRY.get(tool_name)
    if spec is None:
        raise UnknownToolError(f"Tool '{tool_name}' is not on the execution whitelist.")
    return spec


def execute(tool_name: str, params: Mapping[str, Any]) -> Any:
    spec = tool_spec(tool_name)
    validated = _validate_params(spec, params)
    _enforce_mutation_guard(spec, validated)
    return spec.handler(**validated)


register(
    ToolSpec(
        name="get_course_schedule",
        handler=get_course_schedule,
        params={
            "student_id": ParamSpec(types=(str,), required=True),
            "course_code": ParamSpec(types=(str,), required=False, allow_none=True),
            "day": ParamSpec(types=(str,), required=False, allow_none=True),
        },
        mutates_database=False,
    )
)

register(
    ToolSpec(
        name="create_support_ticket",
        handler=create_support_ticket,
        params={
            "student_id": ParamSpec(types=(str,), required=True),
            "summary": ParamSpec(types=(str,), required=True),
            "original_message": ParamSpec(types=(str,), required=True),
            "category": ParamSpec(types=(str, TicketCategory), required=True),
            "priority": ParamSpec(types=(str, TicketPriority), required=True),
            "student_confirmed": ParamSpec(types=(bool,), required=True),
            "case_id": ParamSpec(types=(str,), required=False, allow_none=True),
        },
        mutates_database=True,
        confirmation_param="student_confirmed",
    )
)
