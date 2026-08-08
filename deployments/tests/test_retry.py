"""
Tests for ``deployments.common.retry``.
"""

import unittest

from deployments.common.retry import retry_with_backoff, is_retryable_exception
from deployments.common.exceptions import (
    DeploymentError, ImageBuildError, DeploymentValidationError,
)


class TestRetryWithBackoff(unittest.TestCase):

    def test_first_try_succeeds(self):
        calls = [0]
        def func():
            calls[0] += 1
            return "ok"
        result = retry_with_backoff(func, retries=3, base_delay=0.01)
        self.assertEqual(result, "ok")
        self.assertEqual(calls[0], 1)

    def test_retries_on_exception(self):
        calls = [0]
        def func():
            calls[0] += 1
            if calls[0] < 3:
                raise RuntimeError("transient")
            return "ok"
        result = retry_with_backoff(
            func, retries=5, base_delay=0.001, max_delay=0.01,
            retry_on=(RuntimeError,),
        )
        self.assertEqual(result, "ok")
        self.assertEqual(calls[0], 3)

    def test_exhausts_retries(self):
        calls = [0]
        def func():
            calls[0] += 1
            raise RuntimeError("permanent")
        with self.assertRaises(RuntimeError):
            retry_with_backoff(
                func, retries=2, base_delay=0.001, max_delay=0.01,
                retry_on=(RuntimeError,),
            )
        self.assertEqual(calls[0], 3)  # 1 initial + 2 retries

    def test_skip_on_does_not_retry(self):
        calls = [0]
        def func():
            calls[0] += 1
            raise ValueError("permanent, do not retry")
        with self.assertRaises(ValueError):
            retry_with_backoff(
                func, retries=5, base_delay=0.001,
                retry_on=(Exception,),
                skip_on=(ValueError,),
            )
        self.assertEqual(calls[0], 1)

    def test_no_retry_on_empty_retry_on(self):
        calls = [0]
        def func():
            calls[0] += 1
            raise RuntimeError("x")
        with self.assertRaises(RuntimeError):
            retry_with_backoff(func, retries=5, retry_on=())
        self.assertEqual(calls[0], 1)


class TestIsRetryableException(unittest.TestCase):

    def test_permanent_type_returns_false(self):
        err = DeploymentValidationError("bad config")
        self.assertFalse(is_retryable_exception(
            err, recoverable_types=(ImageBuildError,),
        ))

    def test_recoverable_type_returns_true(self):
        err = ImageBuildError("transient build failure")
        self.assertTrue(is_retryable_exception(
            err, recoverable_types=(ImageBuildError,),
        ))

    def test_recoverable_attr_false_returns_false(self):
        err = DeploymentError("x", recoverable=False)
        self.assertFalse(is_retryable_exception(err))

    def test_transient_marker_in_name(self):
        err = ConnectionError("lost connection")
        self.assertTrue(is_retryable_exception(
            err, transient_markers=("connection",),
        ))

    def test_transient_marker_in_message(self):
        err = RuntimeError("docker daemon temporarily unavailable")
        self.assertTrue(is_retryable_exception(
            err, transient_markers=("temporarily", "unavailable"),
        ))

    def test_no_marker_returns_false(self):
        err = ValueError("invalid argument")
        self.assertFalse(is_retryable_exception(
            err, transient_markers=("timeout", "connection"),
        ))

    def test_permanent_overrides_recoverable(self):
        # If exc is in permanent_types, return False even if it would
        # otherwise be retryable.
        err = ImageBuildError("bad dockerfile")
        self.assertFalse(is_retryable_exception(
            err, permanent_types=(ImageBuildError,),
            recoverable_types=(ImageBuildError,),
        ))


if __name__ == "__main__":
    unittest.main()
