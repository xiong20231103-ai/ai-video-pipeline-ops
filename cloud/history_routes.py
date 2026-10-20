"""Opt-in history APIs. All writes stay in new cloud history.db; no home commands."""
from fastapi import Request,HTTPException
from starlette.concurrency import run_in_threadpool
from contracts.history import HistoryError
from contracts.timeline import analyze
def mount_history(app,history,agent,session,csrf,bounded_json):
    def call(method,*args,**kwargs):
        try:return method(*args,**kwargs)
        except HistoryError as error:raise HTTPException(error.status,error.code) from None
        except (ValueError,TypeError,KeyError,UnicodeError):raise HTTPException(400,'invalid_history_contract') from None
    @app.post('/agent/history/begin')
    async def begin(request:Request):
        agent(request);data=await bounded_json(request)
        return await run_in_threadpool(call,history.begin,data)
    @app.get('/agent/history/{generation}')
    def status(generation:str,request:Request):agent(request);return call(history.status,generation)
    @app.post('/agent/history/{generation}/chunks/{position}')
    async def chunk(generation:str,position:int,request:Request):
        agent(request);data=await bounded_json(request)
        return await run_in_threadpool(call,history.put,generation,position,data.get('operations'))
    @app.post('/agent/history/{generation}/finish')
    async def finish(generation:str,request:Request):
        agent(request);await bounded_json(request)
        return await run_in_threadpool(call,history.finish,generation)
    @app.get('/console/history/{source}')
    def source(source:str,request:Request):session(request);return call(history.source,source)
    @app.get('/console/history/{source}/records')
    def records(source:str,request:Request,kind:str,limit:int=100,after:str='',generation:str|None=None):
        session(request);return call(history.listing,source,kind,limit=limit,after=after,generation=generation)
    @app.get('/console/history/{source}/timeline')
    def timeline(source:str,request:Request,batchId:str,projectId:str,generation:str|None=None):
        session(request);return call(history.timeline,source,batchId,projectId,generation=generation)
    @app.post('/console/history/{source}/select')
    async def select(source:str,request:Request):
        row=session(request);csrf(request,row);data=await bounded_json(request)
        return await run_in_threadpool(call,history.select,source,data.get('generationId'),data.get('confirmation'))
