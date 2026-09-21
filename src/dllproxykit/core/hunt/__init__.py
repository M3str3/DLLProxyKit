from __future__ import annotations

from .finding import Finding
from .services import hunt_services
from .tasks import hunt_tasks


def run_hunt(*, unsafe: bool = False) -> list[Finding]:
    return hunt_services(unsafe=unsafe) + hunt_tasks(unsafe=unsafe)
