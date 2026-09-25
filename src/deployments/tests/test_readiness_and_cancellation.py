import unittest
from unittest.mock import Mock, patch

from deployments.common.exceptions import DeploymentCancelled, HealthCheckError
from deployments.core.health import DockerHealthChecker


class HealthCheckerTests(unittest.TestCase):
    @patch('deployments.core.health.urllib.request.urlopen')
    @patch('deployments.core.health.Container')
    def test_http_readiness_success(self, container_cls, urlopen):
        container = Mock()
        container.status.return_value = 'running'
        container.inspect.return_value = {
            'State': {'Running': True},
            'NetworkSettings': {'Networks': {'proxy_net': {'IPAddress': '172.20.0.5'}}},
        }
        container_cls.return_value = container
        response = Mock(status=200)
        response.__enter__ = lambda self: self
        response.__exit__ = lambda *args: False
        response.read.return_value = b'ok'
        urlopen.return_value = response

        result = DockerHealthChecker().wait_until_healthy(
            'app', timeout=1, interval=0.01, healthcheck_path='/ready', port=8080
        )
        self.assertTrue(result['ready'])
        self.assertEqual(result['http_status'], 200)
        urlopen.assert_called_once()
        self.assertIn('172.20.0.5:8080/ready', urlopen.call_args.args[0])

    @patch('deployments.core.health.urllib.request.urlopen')
    @patch('deployments.core.health.Container')
    def test_http_readiness_failure_is_actionable(self, container_cls, urlopen):
        container = Mock()
        container.status.return_value = 'running'
        container.inspect.return_value = {
            'State': {'Running': True},
            'NetworkSettings': {'Networks': {'proxy_net': {'IPAddress': '172.20.0.5'}}},
        }
        container_cls.return_value = container
        import urllib.error
        urlopen.side_effect = urllib.error.HTTPError(
            'http://172.20.0.5:8080/ready', 500, 'boom', {}, None
        )

        with self.assertRaises(HealthCheckError) as ctx:
            DockerHealthChecker().wait_until_healthy(
                'app', timeout=0, interval=0.01, healthcheck_path='/ready', port=8080
            )
        exc = ctx.exception
        self.assertEqual(exc.code, 'APPLICATION_READINESS_FAILED')
        self.assertEqual(exc.stage, 'health_check')
        self.assertIn('HTTP 500', exc.message)
        self.assertIn('readiness endpoint', exc.user_message.lower())
        self.assertEqual(exc.details['probe']['failure_type'], 'http_status')

    @patch('deployments.core.health.Container')
    def test_readiness_timeout_preserves_container_vs_application_context(self, container_cls):
        container = Mock()
        container.status.return_value = 'running'
        container.inspect.return_value = {
            'State': {'Running': True},
            'NetworkSettings': {'Networks': {'proxy_net': {'IPAddress': '172.20.0.5'}}},
        }
        container_cls.return_value = container
        checker = DockerHealthChecker()
        with patch.object(checker, '_probe_http', return_value={
            'ok': False, 'failure_type': 'connection_error', 'error': 'connection refused'
        }):
            with self.assertRaises(HealthCheckError) as ctx:
                checker.wait_until_healthy('app', timeout=0, healthcheck_path='/ready', port=8080)
        self.assertIn('did not accept readiness connections', ctx.exception.message)
        self.assertEqual(ctx.exception.details['healthcheck_path'], '/ready')

    @patch('deployments.core.health.Container')
    def test_running_without_healthcheck_remains_backward_compatible(self, container_cls):
        container = Mock()
        container.status.return_value = 'running'
        container.inspect.return_value = {'State': {'Running': True}}
        container_cls.return_value = container
        result = DockerHealthChecker(min_running_polls=1).wait_until_healthy(
            'app', timeout=1, interval=0.01
        )
        self.assertTrue(result['ready'])
        self.assertFalse(result['healthcheck'])

    @patch('deployments.core.health.Container')
    def test_cancellation_during_readiness(self, container_cls):
        container = Mock()
        container.status.return_value = 'running'
        container.inspect.return_value = {
            'State': {'Running': True},
            'NetworkSettings': {'Networks': {'proxy_net': {'IPAddress': '172.20.0.5'}}},
        }
        container_cls.return_value = container
        with patch.object(DockerHealthChecker, '_probe_http', return_value={
            'ok': False, 'failure_type': 'connection_error'
        }):
            with self.assertRaises(DeploymentCancelled):
                DockerHealthChecker().wait_until_healthy(
                    'app', timeout=1, interval=0.01,
                    healthcheck_path='/ready', port=8080,
                    cancel_check=lambda: True,
                )


class BuildCancellationContractTests(unittest.TestCase):
    def test_build_stream_closes_response_on_cancellation(self):
        from deployments.core.manager.image_manager import Image

        response = Mock()
        response.close = Mock()
        image = object.__new__(Image)
        image.logger = Mock()
        image._iter_build_stream = Mock(return_value=iter([{'stream': 'step 1'}]))

        with patch('deployments.core.manager.image_manager.BuildError', RuntimeError):
            with self.assertRaises(DeploymentCancelled):
                image._handle_build_stream_collect_id(
                    response,
                    cancel_check=lambda: True,
                )
        response.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
