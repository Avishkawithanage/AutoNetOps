from app.config import settings
from app.network.base_driver import BaseDriver, DeviceTarget


def get_driver(target: DeviceTarget) -> BaseDriver:
    if settings.driver_mode == "mock":
        from app.network.mock_driver import MockDriver
        return MockDriver(target)
    from app.network.cisco_ios import CiscoIOSDriver
    return CiscoIOSDriver(target)
