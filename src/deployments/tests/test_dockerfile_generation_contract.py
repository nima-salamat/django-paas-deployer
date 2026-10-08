from deployments.core.dockerfile import _normalize_dockerfile_healthcheck_syntax


def test_normalize_compose_cmd_shell_healthcheck_to_dockerfile_cmd():
    source = (
        "FROM wordpress:7.1.2-php8.3-apache\n"
        "HEALTHCHECK --interval=5s --timeout=5s CMD-SHELL test -f /tmp/ready\n"
    )

    assert _normalize_dockerfile_healthcheck_syntax(source) == (
        "FROM wordpress:7.1.2-php8.3-apache\n"
        "HEALTHCHECK --interval=5s --timeout=5s CMD test -f /tmp/ready\n"
    )


def test_normalize_healthcheck_leaves_cmd_form_unchanged():
    source = "HEALTHCHECK --retries=3 CMD [\"curl\", \"-f\", \"http://127.0.0.1/\"]\n"
    assert _normalize_dockerfile_healthcheck_syntax(source) == source
