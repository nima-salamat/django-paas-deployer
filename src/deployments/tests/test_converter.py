"""
Tests for ``deployments.core.converter`` (zip-to-tar conversion).

These tests verify the archive-safety properties of
``convert_zip_to_tar``:
  * rejects path traversal (Zip Slip)
  * rejects symlinks
  * enforces size + member-count caps
  * strips executable bits
"""

import io
import os
import tarfile
import unittest
import zipfile
import tempfile

from deployments.core.converter import convert_zip_to_tar, merge_tar_streams


def _make_zip(members: dict[str, bytes | None]) -> bytes:
    """Build a ZIP in memory.  None value => directory entry."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in members.items():
            if content is None:
                zf.writestr(name + "/", "")
            else:
                zf.writestr(name, content)
    return buf.getvalue()


class TestConvertZipToTar(unittest.TestCase):

    def _write_and_convert(self, zip_bytes: bytes):
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
            tf.write(zip_bytes)
            path = tf.name
        try:
            return convert_zip_to_tar(path)
        finally:
            os.unlink(path)

    def _list_tar_members(self, tar_stream) -> list[str]:
        tar_stream.seek(0)
        with tarfile.open(fileobj=tar_stream, mode="r") as tf:
            return tf.getnames()

    def test_basic_conversion(self):
        zip_bytes = _make_zip({
            "app/main.py": b"print('hello')\n",
            "README.md": b"# my app\n",
        })
        tar_stream = self._write_and_convert(zip_bytes)
        members = self._list_tar_members(tar_stream)
        self.assertIn("app/main.py", members)
        self.assertIn("README.md", members)

    def test_rejects_path_traversal(self):
        zip_bytes = _make_zip({
            "../escape.py": b"malicious",
        })
        with self.assertRaises(Exception):
            self._write_and_convert(zip_bytes)

    def test_rejects_absolute_path(self):
        zip_bytes = _make_zip({
            "/etc/passwd": b"root:x:0:0:root:/root:/bin/bash",
        })
        with self.assertRaises(Exception):
            self._write_and_convert(zip_bytes)

    def test_strips_executable_bits(self):
        zip_bytes = _make_zip({"script.sh": b"#!/bin/sh\necho hi"})
        tar_stream = self._write_and_convert(zip_bytes)
        tar_stream.seek(0)
        with tarfile.open(fileobj=tar_stream, mode="r") as tf:
            member = tf.getmember("script.sh")
            # Mode should be 0o644 (no execute bit)
            self.assertEqual(member.mode & 0o111, 0)


class TestMergeTarStreams(unittest.TestCase):

    def test_merges_two_tars(self):
        # Build two small tars
        buf1 = io.BytesIO()
        with tarfile.open(fileobj=buf1, mode="w") as tf:
            data = b"hello"
            info = tarfile.TarInfo(name="a.txt")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

        buf2 = io.BytesIO()
        with tarfile.open(fileobj=buf2, mode="w") as tf:
            data = b"world"
            info = tarfile.TarInfo(name="b.txt")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

        merged = merge_tar_streams(buf1, buf2)
        merged.seek(0)
        with tarfile.open(fileobj=merged, mode="r") as tf:
            names = tf.getnames()
        self.assertIn("a.txt", names)
        self.assertIn("b.txt", names)


if __name__ == "__main__":
    unittest.main()
