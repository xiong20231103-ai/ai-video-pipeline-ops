"""Explicit Dashboard namespace GET binding; never patches process-global urllib.

Caller installs only into a reviewed isolated/idle Dashboard namespace. It must
retain the returned handle and restore on shutdown. No network is performed here.
"""
from urllib.parse import urlsplit
from tools.shadow_capture import CaptureError

class Proxy:
    def __init__(self,original,**overrides):self.original=original;self.overrides=overrides
    def __getattr__(self,name):return self.overrides[name] if name in self.overrides else getattr(self.original,name)

class DashboardReadBinding:
    def __init__(self,namespace,observer,routes):
        if not routes or len(routes)>16:raise CaptureError('dashboard_observer_routes_required')
        self.namespace=namespace;self.observer=observer;self.routes=dict(routes)
        self.original=namespace['urllib'];original_open=self.original.request.urlopen
        for url,(port,path) in self.routes.items():
            parsed=urlsplit(url)
            if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path!=path or (port,path) not in observer.ports:raise CaptureError('dashboard_observer_route_invalid')
        def open_existing(request,*args,**kwargs):
            url=request.full_url if hasattr(request,'full_url') else str(request)
            method=request.get_method() if hasattr(request,'get_method') else ('POST' if args and args[0] is not None or kwargs.get('data') is not None else 'GET')
            if (args and args[0] is not None) or kwargs.get('data') is not None:method='POST'
            binding=self.routes.get(url) if method=='GET' else None;attempt=None
            if binding:
                try:attempt=observer.begin(*binding)
                except Exception:pass
            try:response=original_open(request,*args,**kwargs)
            except BaseException:
                if attempt is not None:
                    try:observer.end(attempt)
                    except Exception:pass
                raise
            if attempt is None:return response
            class ReadTee:
                def __getattr__(self,name):return getattr(response,name)
                def __enter__(self):response.__enter__();return self
                def __exit__(self,*args):
                    try:observer.end(attempt)
                    except Exception:pass
                    return response.__exit__(*args)
                def read(self,*args,**kwargs):
                    raw=response.read(*args,**kwargs)
                    size=args[0] if args else kwargs.get('amt',kwargs.get('size',-1))
                    # Dashboard json.load/read() consumes whole bodies. A partial
                    # read cannot prove EOF and is rejected without another read.
                    if size is None or size<0:
                        try:observer.complete(attempt,getattr(response,'status',0),raw)
                        except Exception:pass
                    return raw
            return ReadTee()
        self.proxy=Proxy(self.original,request=Proxy(self.original.request,urlopen=open_existing))
        namespace['urllib']=self.proxy
    def restore(self):
        if self.namespace.get('urllib') is not self.proxy:raise CaptureError('dashboard_observer_binding_changed')
        self.namespace['urllib']=self.original
