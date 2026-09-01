from pathlib import Path


def test_laravel_artisan_commands_are_allowlisted():
    source = Path(__file__).with_name("shell.py").read_text()
    assert '"migrate"' in source
    assert '"migrate:status"' in source
    assert '"createsuperuser"' not in source.split('if base == "php":', 1)[1].split('if base in {"python"', 1)[0]
    assert "arbitrary_php_scripts" in Path(__file__).with_name("api").joinpath("shell.py").read_text()


def test_command_api_passes_explicit_confirmation():
    source = Path(__file__).with_name("api").joinpath("shell.py").read_text()
    assert 'confirm=request.data.get("confirm", False)' in source
