from pathlib import Path
import re

def _source():
    root = Path(__file__).resolve().parents[2]
    return (root / "core" / "manager" / "image_manager.py").read_text()

def test_repository_component_pattern_accepts_namespaced_repositories():
    text = _source()
    m = re.search(r'_VALID_NAME_COMPONENT_RE = re\.compile\(r"(.+?)"\)', text)
    assert m, "component validation regex missing"
    pattern = re.compile(m.group(1))
    assert pattern.fullmatch("paas-base")
    assert pattern.fullmatch("php-apache")
    assert not pattern.fullmatch("PHP")

def test_repository_validation_splits_namespace_components():
    text = _source()
    assert 'parts = value.split("/")' in text
    assert 'any(not part or not _VALID_NAME_COMPONENT_RE.fullmatch(part) for part in parts)' in text

def test_namespaced_repository_is_supported_by_runtime_validator():
    text = _source()
    assert '_VALID_NAME_COMPONENT_RE' in text
    assert 'return value' in text
