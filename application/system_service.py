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
        return self.controller.start(config)

    def status(self) -> dict[str, object]:
        return self.controller.status()

    def stop(self) -> dict[str, object]:
        return self.controller.stop()
