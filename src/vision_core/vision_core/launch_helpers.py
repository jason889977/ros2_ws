"""Shared helpers for ROS 2 launch files."""

from __future__ import annotations

import math
import re

ROS_ID_PATTERN = re.compile(r'[A-Za-z][A-Za-z0-9_]*')


def validate_ros_identifier(value: str, name: str = 'identifier') -> None:
    """Raise ``ValueError`` if *value* is not a ROS-safe name."""
    if not ROS_ID_PATTERN.fullmatch(str(value)):
        raise ValueError(f'{name} {value!r} is not a valid ROS identifier')


def parse_bool(value, name: str) -> bool:
    """Parse a strict boolean launch value."""
    normalized = str(value).strip().lower()
    if normalized not in ('true', 'false'):
        raise RuntimeError(f'Invalid {name}={value!r}; expected true or false.')
    return normalized == 'true'


def parse_nonnegative_float(value, name: str) -> float:
    """Parse a non-negative float launch value."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise RuntimeError(f'Invalid {name}={value!r}; expected a non-negative number.')
    if not math.isfinite(result) or result < 0.0:
        raise RuntimeError(f'Invalid {name}={value!r}; expected a non-negative number.')
    return result


def declare_and_get(node, name: str, default):
    """Declare a parameter and return its value."""
    node.declare_parameter(name, default)
    return node.get_parameter(name).value


def parse_positive_float(value, name: str) -> float:
    """Parse a positive float launch value."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise RuntimeError(f'Invalid {name}={value!r}; expected a positive number.')
    if not math.isfinite(result) or result <= 0.0:
        raise RuntimeError(f'Invalid {name}={value!r}; expected a positive number.')
    return result
