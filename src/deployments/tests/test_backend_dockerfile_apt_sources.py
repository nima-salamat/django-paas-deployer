from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_backend_dockerfile_includes_matching_debian_security_repository():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert 'security_mirror="${mirror%/debian}/debian-security";' in dockerfile
    assert '"deb $security_mirror $codename-security main"' in dockerfile
    assert '"deb $mirror $codename main"' in dockerfile
    assert '"deb $mirror $codename-updates main"' in dockerfile
