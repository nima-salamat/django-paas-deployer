from .contracts import contract_for
from core.throttling import check_scope
from rest_framework.throttling import BaseThrottle


class AgentRateThrottle(BaseThrottle):
    rate_map = {
        "read": "120/min",
        "mutation": "30/min",
        "deployment": "10/min",
        "upload": "5/min",
        "shell": "10/min",
        "exchange": "10/min",
    }

    def allow_request(self, request, view):
        contract = None
        resolver = getattr(view, "get_agent_contract_path", None)
        if callable(resolver):
            try:
                contract = contract_for(resolver(request), request.method)
            except Exception:
                contract = None

        throttle_scope = (
            contract.throttle_scope
            if contract is not None
            else getattr(view, "throttle_scope", "read")
        )
        rate = getattr(view, "throttle_rate", None) or self.rate_map.get(throttle_scope, "60/min")
        limit, window = self.parse_rate(rate)
        if limit is None:
            return True

        agent = getattr(request, "agent", None)
        identity = (
            f"agent:{agent.pk}"
            if agent is not None
            else f"ip:{str(request.META.get('REMOTE_ADDR') or '0.0.0.0')}"
        )
        self._scope = f"agent-api:{throttle_scope}:{identity}"
        self._window = window
        self._limit = limit
        return check_scope(self._scope, limit, window)

    def wait(self):
        return getattr(self, "_window", 60)

    @staticmethod
    def parse_rate(rate):
        try:
            number, period = str(rate).split("/", 1)
            number = int(number)
            unit = period.strip().lower()
            units = {
                "s": 1,
                "sec": 1,
                "second": 1,
                "seconds": 1,
                "m": 60,
                "min": 60,
                "minute": 60,
                "minutes": 60,
                "h": 3600,
                "hour": 3600,
                "hours": 3600,
                "d": 86400,
                "day": 86400,
                "days": 86400,
            }
            for prefix, seconds in units.items():
                if unit.startswith(prefix):
                    return number, seconds
        except Exception:
            pass
        return None, 60
