import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agent.readonly import ReadOnlyAgent
from cloud.store import Store
from contracts.cache import cache_key
from prefetch_view import public_views


class PrefetchTransportTests(unittest.TestCase):
 def test_existing_agent_outbox_and_cloud_cache_preserve_only_public_projection(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);states=root/'home/handoff/download/prefetch';states.mkdir(parents=True)
   task={'taskId':'task-6','batchId':'batch','expectedCount':26,'batchSequence':6,'date':'11.2','project':'项目','material':'材料'}
   (states/'task-6.json').write_text(json.dumps({**task,'urlCount':26,'completedOutputs':23,'state':'finished',
     'failedLinks':[{'url':'private-url'}],'token':'PRIVATE-TOKEN','downloadPath':'PRIVATE-PATH'}),encoding='utf-8')
   body={'prefetchViews':public_views(root/'home',[task])}
   agent=ReadOnlyAgent('https://fixture.ts.net','FIXTURE-AGENT-TOKEN',root/'agent')
   with patch.object(agent,'home',return_value=(200,body,'fixture-etag')) as get:
    agent.collect('/api/dashboard/summary',conditional=False)
    get.assert_called_once_with('/api/dashboard/summary',conditional=False,reason='periodic')
   payload=agent.ledger.next()
   cloud=Store(root/'cloud.db')
   self.assertEqual('stored',cloud.push(payload))
   row=cloud.box_response(cache_key('GET','/api/dashboard/summary'))
   self.assertEqual(body,json.loads(row['body']))
   serialized=json.dumps(payload)
   for private in ('private-url','PRIVATE-TOKEN','PRIVATE-PATH','FIXTURE-AGENT-TOKEN','downloadPath','failedLinks'):
    self.assertNotIn(private,serialized)
   self.assertEqual(1,body['prefetchViews'][0]['missingCount'])
