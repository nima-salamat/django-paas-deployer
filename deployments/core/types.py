from dataclasses import dataclass, field
from typing import Any, Callable, Optional


EventSink = Callable[["DeploymentEvent"], None]


@dataclass(frozen=True)
class NetworkSpec:
    name: str
    driver: str = "bridge"
    internal: bool = True
    attachable: bool = True


@dataclass(frozen=True)
class VolumeSpec:
    source: str
    target: str
    mode: str = "rw"
    mount_type: str = "volume"
    driver: str = "local"
    driver_opts: dict[str, Any] = field(default_factory=dict)
    create: bool = True
    size_mb: Optional[int] = None


@dataclass(frozen=True)
class DeploymentConfig:
    name: str
    tag: str
    zip_path: str
    dockerfile_template: str
    max_cpu: float
    max_ram: int
    networks: list[NetworkSpec]
    volumes: list[VolumeSpec]
    port: Optional[int]
    read_only: bool
    platform: str
    platform_type: str
    stop_timeout: int = 10
    start_timeout: int = 30
    health_timeout: int = 45
    health_interval: float = 1.0

    @property
    def image_ref(self) -> str:
        return f"{self.name}:{self.tag}"


@dataclass
class DeploymentEvent:
    stage: str
    message: str
    level: str = "info"
    progress: Optional[int] = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeploymentResult:
    success: bool
    status: str
    message: str
    image_ref: Optional[str] = None
    container_name: Optional[str] = None
    previous_image_ref: Optional[str] = None
    rollback_performed: bool = False
    error: Optional[str] = None
    stage: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
