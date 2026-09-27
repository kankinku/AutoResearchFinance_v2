from __future__ import annotations

from pathlib import Path

from runtime.system_controller import SystemController, SystemLaunchConfig


class SystemService:
    """Application boundary around managed paper-research runtime control."""

    def __init__(
        self,
        *,
        state_dir: Path,
        project_root: Path,
        controller: SystemController | None = None,
    ) -> None:
        self.controller = controller or SystemController(
            state_dir=state_dir,
            project_root=project_root,
        )

    def preflight(self, config: SystemLaunchConfig) -> dict[str, object]:
        return self.controller.preflight(config).as_payload()

    def start(self, config: SystemLaunchConfig) -> dict[str, object]:
        return _public_system_payload(self.controller.start(config))

    def status(self) -> dict[str, object]:
        return _public_system_payload(self.controller.status())

    def stop(self) -> dict[str, object]:
        return _public_system_payload(self.controller.stop())


def _public_system_payload(payload: dict[str, object]) -> dict[str, object]:
    """Remove process-local identity details from application-facing system state."""

    sanitized = {
        key: value
        for key, value in payload.items()
        if key not in {"project_root", "container_name"}
    }
    components = payload.get("components")
    if isinstance(components, list):
        sanitized["components"] = [
            {
                key: value
                for key, value in component.items()
                if key not in {"identity_markers", "command", "cwd", "env_file"}
            }
            if isinstance(component, dict)
            else component
            for component in components
        ]
    return sanitized
