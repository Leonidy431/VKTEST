"""ESP32-S3 Watchdog module for Raspberry Pi 3 power management."""

from .esp32_watchdog import (
    ESP32Watchdog,
    MockESP32Watchdog,
    WatchdogState,
    WatchdogConfig,
)

__all__ = [
    "ESP32Watchdog",
    "MockESP32Watchdog",
    "WatchdogState",
    "WatchdogConfig",
]
