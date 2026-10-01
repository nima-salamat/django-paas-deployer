from core.throttling import check_scope
from rest_framework.throttling import BaseThrottle
class AgentRateThrottle(BaseThrottle):
    rate_map={"read":"120/min","mutation":"30/min","deployment":"10/min","upload":"5/min","shell":"10/min","exchange":"10/min"}
    def allow_request(self,request,view):
        rate=getattr(view,"throttle_rate",None) or self.rate_map.get(getattr(view,"throttle_scope","read"),"60/min"); limit,window=self.parse_rate(rate)
        if limit is None:return True
        agent=getattr(request,"agent",None); identity=f"agent:{agent.pk}" if agent else f"ip:{str(request.META.get('REMOTE_ADDR') or '0.0.0.0')}"; self._scope=f"agent-api:{getattr(view,'throttle_scope','read')}:{identity}"; self._window=window
        return check_scope(self._scope,limit,window)
    @staticmethod
    def parse_rate(rate):
        try:
            number,period=str(rate).split("/",1); number=int(number); unit=period.strip().lower(); units={"s":1,"sec":1,"second":1,"seconds":1,"m":60,"min":60,"minute":60,"minutes":60,"h":3600,"hour":3600,"hours":3600,"d":86400,"day":86400,"days":86400}
            for k,v in units.items():
                if unit.startswith(k):return number,v
        except Exception:pass
        return None,60
    def wait(self):return getattr(self,"_window",60)
