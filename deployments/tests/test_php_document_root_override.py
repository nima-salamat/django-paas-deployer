import io
import tarfile

from deployments.core.dockerfile import _detect_php_document_root


def _tar(files):
    s = io.BytesIO()
    with tarfile.open(fileobj=s, mode="w") as tf:
        for name in files:
            info = tarfile.TarInfo(name=name)
            data = b""
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    s.seek(0)
    return s


def test_php_document_root_dot_is_root():
    assert _detect_php_document_root(_tar(["public/index.php", "composer.json"]), user_override=".") == ""
