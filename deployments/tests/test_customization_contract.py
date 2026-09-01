from deployments.common.config import validate_platform_config


def test_laravel_custom_document_root_is_scoped():
    report = validate_platform_config(
        {"document_root": "web", "url_handling": {"mode": "auto"}},
        "laravel",
        project_paths={"web/index.php", "resources/css/app.css"},
    )
    assert report["normalized"]["document_root"] == "web"
    assert report["normalized"]["url_handling"]["mode"] == "auto"


def test_laravel_url_automation_can_be_disabled():
    report = validate_platform_config(
        {"url_handling": {"mode": "disabled"}}, "laravel"
    )
    assert report["normalized"]["url_handling"]["mode"] == "disabled"


def test_unsupported_path_only_warns_and_keeps_automation():
    report = validate_platform_config({"static_dir": "static"}, "laravel")
    assert any("static_dir" in w for w in report["warnings"])


def test_custom_urls_are_validated():
    report = validate_platform_config(
        {"url_handling": {"mode": "custom", "asset_url": "https://cdn.example.com/app"}},
        "react",
    )
    assert report["normalized"]["url_handling"]["mode"] == "custom"
