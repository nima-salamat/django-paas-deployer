from pathlib import Path


SHELL = Path(__file__).with_name("shell.py").read_text()
API = Path(__file__).with_name("api").joinpath("shell.py").read_text()


def test_risk_based_policy_present():
    assert "class Risk" in SHELL
    assert "classify_command_risk" in SHELL
    assert "ShellPolicyError" in SHELL
    assert "NORMAL_MUTATION" in SHELL
    assert "DESTRUCTIVE" in SHELL


def test_php_artisan_migrate_is_normal_mutation_not_destructive():
    assert "ARTISAN_DESTRUCTIVE" in SHELL
    assert '"migrate:fresh"' in SHELL
    destructive_block = SHELL.split("ARTISAN_DESTRUCTIVE", 1)[1].split("}", 1)[0]
    assert "migrate:fresh" in destructive_block
    cleaned = (
        destructive_block.replace("migrate:fresh", "")
        .replace("migrate:refresh", "")
        .replace("migrate:reset", "")
    )
    assert '"migrate"' not in cleaned


def test_runtime_commands_available_across_platforms():
    assert "RUNTIME_COMMANDS" in SHELL
    assert '"git"' in SHELL
    assert '"make"' in SHELL


def test_api_returns_structured_error_codes():
    assert "_shell_error_response" in API
    assert "POLICY_REJECTED" in API
    assert "CONFIRMATION_REQUIRED" in API
    assert "AUTHORIZATION_FAILED" in API


def test_php_inline_eval_still_blocked():
    assert "Direct PHP script or inline execution is not allowed" in SHELL
    assert "Arbitrary Python script/inline execution is not allowed" in SHELL
