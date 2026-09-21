"""
deployments/tests/__init__.py
-----------------------------
Test suite for the deployment subsystem.

Tests are pure-Python where possible (state machine, security validation,
config parsing, retry policy) and Django/DB-backed only where unavoidable
(state transitions with select_for_update, advisory locks).
"""
