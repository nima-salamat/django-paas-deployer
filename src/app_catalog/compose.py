from __future__ import annotations

from pathlib import Path
from .compose_catalog import load_compose_yaml
import yaml

from .catalog import CatalogValidationError
from .compose_catalog import validate_compose_security
from .plan import ApplicationPlan, ApplicationPlanError, plan_from_compose


def load_compose(text_or_path: str | Path, *, app_id: str, version: str = "1.0.0", variant: str = "default") -> ApplicationPlan:
    if isinstance(text_or_path, Path):
        text = text_or_path.read_text("utf-8")
    else:
        candidate = Path(text_or_path)
        text = candidate.read_text("utf-8") if candidate.exists() and candidate.is_file() else text_or_path
    try:
        document = load_compose_yaml(text) or {}
    except yaml.YAMLError as exc:
        raise ApplicationPlanError(f"Invalid Compose YAML: {exc}") from exc
    try:
        validate_compose_security(document)
        return plan_from_compose(document, app_id=app_id, version=version, variant=variant)
    except ApplicationPlanError as exc:
        raise CatalogValidationError(str(exc)) from exc
