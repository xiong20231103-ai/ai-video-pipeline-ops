"""Explicit opt-in transfer; no worker registration, credentials or home requests."""
from contracts.history import HistoryError
from .history_export import validate_bundle
def transfer(bundle,client):
    validate_bundle(bundle)
    generation=bundle['generationId'];reply=client.post('/agent/history/begin',bundle['manifest'])
    if reply.get('generationId')!=generation:raise HistoryError('history_begin_ack_missing')
    # Every retry queries the existing generation; never creates a second ID.
    current=client.get('/agent/history/'+generation)
    received=set(current['receivedChunks'])
    for position,operations in enumerate(bundle['chunks']):
        if position not in received:
            reply=client.post('/agent/history/'+generation+'/chunks/'+str(position),{'operations':operations})
            if reply.get('generationId')!=generation or position not in reply.get('receivedChunks',[]):raise HistoryError('history_chunk_ack_missing')
    reply=client.post('/agent/history/'+generation+'/finish',{})
    if reply.get('generationId')!=generation or reply.get('state')!='ready':raise HistoryError('history_finish_ack_missing')
    return {'generationId':generation,'state':'ready','homeBusinessRequests':0}
