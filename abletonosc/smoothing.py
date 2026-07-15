"""Interpolate continuous Live parameters between OSC ticks."""

from __future__ import annotations

from typing import Callable, Dict, Hashable, Optional, Tuple, Union

from .constants import (
    CONTINUOUS_OBJECT_PROPERTIES,
    DISCRETE_OBJECT_PROPERTIES,
    SMOOTHING_ENABLED,
    SMOOTH_EPSILON,
    SMOOTH_STEP_FACTOR,
    SMOOTH_STEPS_PER_TICK,
)

LiveParameter = object
Key = Hashable


class _SmoothChannel:
    __slots__ = ("target", "apply_fn", "read_fn")

    def __init__(
        self,
        target: float,
        apply_fn: Callable[[float], None],
        read_fn: Callable[[], float],
    ) -> None:
        self.target = float(target)
        self.apply_fn = apply_fn
        self.read_fn = read_fn

    def step(self, steps: int, factor: float, epsilon: float) -> bool:
        current = float(self.read_fn())
        for _ in range(steps):
            delta = self.target - current
            if abs(delta) <= epsilon:
                self.apply_fn(self.target)
                return True
            current += delta * factor
            self.apply_fn(current)
        return abs(self.target - float(self.read_fn())) <= epsilon * 10.0


class ParameterSmoother:
    def __init__(
        self,
        *,
        enabled: bool = SMOOTHING_ENABLED,
        steps_per_tick: int = SMOOTH_STEPS_PER_TICK,
        step_factor: float = SMOOTH_STEP_FACTOR,
        epsilon: float = SMOOTH_EPSILON,
    ) -> None:
        self.enabled = enabled
        self.steps_per_tick = max(1, int(steps_per_tick))
        self.step_factor = step_factor
        self.epsilon = epsilon
        self._channels: Dict[Key, _SmoothChannel] = {}

    @staticmethod
    def should_smooth_object_property(class_identifier: str, prop: str) -> bool:
        if prop in DISCRETE_OBJECT_PROPERTIES.get(class_identifier, ()):
            return False
        if prop in CONTINUOUS_OBJECT_PROPERTIES.get(class_identifier, ()):
            return True
        return False

    @staticmethod
    def should_smooth_live_parameter(parameter: LiveParameter) -> bool:
        if parameter is None:
            return False
        if getattr(parameter, "is_quantized", False):
            return False
        name = getattr(parameter, "name", "") or ""
        lowered = name.lower()
        if lowered in ("device on", "mute", "solo", "arm", "on/off"):
            return False
        return True

    def set_float(
        self,
        key: Key,
        target: float,
        apply_fn: Callable[[float], None],
        read_fn: Callable[[], float],
        *,
        immediate: bool = False,
    ) -> None:
        target = float(target)
        if immediate or not self.enabled:
            apply_fn(target)
            self._channels.pop(key, None)
            return

        if key in self._channels:
            self._channels[key].target = target
            return

        current = float(read_fn())
        if abs(target - current) <= self.epsilon:
            apply_fn(target)
            return

        self._channels[key] = _SmoothChannel(target, apply_fn, read_fn)

    def set_live_parameter(
        self,
        key: Key,
        parameter: LiveParameter,
        target: float,
        *,
        immediate: bool = False,
    ) -> None:
        if immediate or not self.enabled or not self.should_smooth_live_parameter(parameter):
            parameter.value = target
            self._channels.pop(key, None)
            return

        self.set_float(
            key,
            target,
            apply_fn=lambda value, param=parameter: setattr(param, "value", value),
            read_fn=lambda param=parameter: float(param.value),
        )

    def advance(self) -> None:
        if not self.enabled or not self._channels:
            return
        finished: Tuple[Key, ...] = tuple(
            key
            for key, channel in list(self._channels.items())
            if channel.step(self.steps_per_tick, self.step_factor, self.epsilon)
        )
        for key in finished:
            self._channels.pop(key, None)
