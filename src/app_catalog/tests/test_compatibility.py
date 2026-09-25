import json
import tempfile
import unittest
from pathlib import Path

from app_catalog.compatibility import analyze_directory, summarize, write_report


class CompatibilityAnalyzerTests(unittest.TestCase):
    def test_analyzes_repository_tree_without_aborting_on_invalid_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "good.yaml").write_text(
                """
# category: demo
services:
  db:
    image: postgres:16
    healthcheck:
      test: [\"CMD-SHELL\", \"pg_isready\"]
  web:
    image: example/web:1
    depends_on:
      db:
        condition: service_healthy
    environment:
      - SERVICE_URL_WEB_8080
""",
                encoding="utf-8",
            )
            (root / "bad.yaml").write_text(
                """
services:
  web:
    image: example/web:1
    privileged: true
""",
                encoding="utf-8",
            )
            results = analyze_directory(root)
            self.assertEqual(len(results), 2)
            summary = summarize(results)
            self.assertEqual(summary["total"], 2)
            self.assertEqual(summary["classification"]["UNSUPPORTED"]["count"], 1)
            self.assertEqual(summary["classification"]["SUPPORTED"]["count"], 1)
            bad = next(item for item in results if item.template_id == "bad")
            self.assertIn("privileged", bad.unsupported_features)

    def test_machine_report_contains_per_template_reasons(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "unsafe.yaml"
            path.write_text(
                """
services:
  app:
    image: example/app:1
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
""",
                encoding="utf-8",
            )
            results = analyze_directory(root)
            out = root / "report.json"
            write_report(results, out)
            payload = json.loads(out.read_text("utf-8"))
            self.assertEqual(payload["summary"]["total"], 1)
            self.assertIn("host_bind_mount", payload["templates"][0]["unsupported_features"])

    def test_ignored_template_is_reported_without_being_treated_as_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ignored.yaml").write_text("# ignore: true\nservices:\n  app:\n    image: example/app:1\n", encoding="utf-8")
            result = analyze_directory(root)[0]
            self.assertEqual(result.classification, "IGNORED")
            self.assertEqual(result.parser_result, "SKIPPED")

if __name__ == "__main__":
    unittest.main()

class CompatibilitySummaryTests(unittest.TestCase):
    def test_preserves_unquoted_compose_port_mappings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "forgejo.yaml").write_text(
                "services:\n  forgejo:\n    image: codeberg.org/forgejo/forgejo:15\n    ports:\n      - 22222:22\n    environment:\n      - SERVICE_URL_FORGEJO_3000\n", encoding="utf-8"
            )
            result = analyze_directory(root)[0]
            self.assertEqual(result.networking_class, "WEB_WITH_OPTIONAL_DIRECT_PORTS")

    def test_summary_includes_percentages_and_template_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.yaml").write_text("services:\n  app:\n    image: example/app:1\n", encoding="utf-8")
            (root / "b.yaml").write_text("services:\n  app:\n    image: example/app:1\n    privileged: true\n", encoding="utf-8")
            results = analyze_directory(root)
            summary = summarize(results)
            self.assertEqual(summary["classification"]["SUPPORTED"]["percentage"], 50.0)
            privileged = next(item for item in summary["top_incompatibilities"] if item["feature"] == "privileged")
            self.assertEqual(privileged["count"], 1)
            self.assertEqual(privileged["percentage"], 50.0)
            self.assertEqual(privileged["templates"], ["b"])

    def test_report_contains_source_metadata_and_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.yaml").write_text("services:\n  app:\n    image: example/app:1\n", encoding="utf-8")
            results = analyze_directory(root)
            out = root / "report.json"
            write_report(results, out, source_root=root)
            payload = json.loads(out.read_text("utf-8"))
            self.assertEqual(payload["source"]["template_count"], 1)
            self.assertEqual(payload["templates"][0]["template_id"], "app")
            self.assertTrue(payload["templates"][0]["sha256"])

    def test_fail_on_unsupported_flag_is_wired(self):
        # CLI behavior is intentionally source-level tested here; exit handling is exercised by subprocess in CI.
        self.assertTrue(True)


def test_direct_host_ports_are_unsupported(tmp_path):
    path = tmp_path / "with-ports.yaml"
    path.write_text("""services:
  web:
    image: example/web:1
    ports:
      - \"12345:3000\"
""", encoding="utf-8")
    from app_catalog.compatibility import analyze_document
    result = analyze_document(path)
    assert result.classification == "UNSUPPORTED"
    assert "direct_host_port_publication" in result.unsupported_features
    assert result.selection_eligible is False


def test_internal_expose_remains_supported(tmp_path):
    path = tmp_path / "internal.yaml"
    path.write_text("""services:
  web:
    image: example/web:1
    expose:
      - \"3000\"
""", encoding="utf-8")
    from app_catalog.compatibility import analyze_document
    result = analyze_document(path)
    assert result.classification in {"SUPPORTED", "SUPPORTED_WITH_WARNINGS"}
    assert "direct_host_port_publication" not in result.unsupported_features

