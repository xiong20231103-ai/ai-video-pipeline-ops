import copy
import ast
import json
from pathlib import Path
import unittest
import app
from contracts.cache import MATRIX,cache_key,semantic_hash
from contracts.golden import differences,replay_receiver

class ContractTests(unittest.TestCase):
    def test_parameter_order_and_scalar_last_value(self):
        self.assertEqual(cache_key('GET','/api/dashboard?date=10.16&batchId=b'),cache_key('get','/api/dashboard?batchId=b&date=10.16'))
        self.assertEqual(cache_key('GET','/api/tasks?state=a&state=b'),cache_key('GET','/api/tasks?state=b'))

    def test_all_effective_query_values_are_identity(self):
        for target in ['/api/dashboard?date=10.16&batchId=b','/api/tasks?state=failed&date=10.16&include_history=true','/api/events?limit=30']:
            key=cache_key('GET',target)
            for value in target.split('?',1)[1].split('&'):
                altered=target.replace(value,value+'x',1)
                self.assertNotEqual(key,cache_key('GET',altered))

    def test_reject_non_contract_targets(self):
        for target in ['https://external.invalid/api/dashboard','/api/../dashboard','/api//dashboard','/api/dashboard?unused=x','/api/dashboard#x']:
            with self.assertRaises(ValueError): cache_key('GET',target)
        with self.assertRaises(ValueError): cache_key('POST','/api/control-commands')

    def test_semantic_hash_excludes_only_named_outer_paths(self):
        data={'updatedAt':'a','metrics':{'time':'a'},'command':{'expiresAt':'a','lastHeartbeat':'a','attemptId':'a'}}
        other=copy.deepcopy(data); other['updatedAt']='b'; other['metrics']['time']='b'
        self.assertEqual(semantic_hash(data),semantic_hash(other))
        for key in data['command']:
            changed=copy.deepcopy(data); changed['command'][key]='b'
            self.assertNotEqual(semantic_hash(data),semantic_hash(changed))

    def test_strict_golden_preserves_types_array_order_and_business_times(self):
        self.assertTrue(differences({'x':True},{'x':1}))
        self.assertTrue(differences({'x':[1,2]},{'x':[2,1]}))
        self.assertTrue(differences({'expiresAt':'a'},{'expiresAt':'b'}))
        self.assertEqual([],differences({'updatedAt':'a'},{'updatedAt':'b'},('/updatedAt',)))
        with self.assertRaises(ValueError): differences({}, {}, ('/*/updatedAt',))

    def test_frozen_receiver_goldens_match_legacy(self):
        folder=Path(__file__).parent/'fixtures/golden'
        fixtures=json.loads((folder/'receiver-inputs.json').read_text(encoding='utf-8'))
        expected=json.loads((folder/'receiver-expected.json').read_text(encoding='utf-8'))
        for name,fixture in fixtures.items():
            with self.subTest(name=name):
                self.assertEqual([],differences(expected[name],replay_receiver(app,fixture)))

    def test_read_matrix_has_explicit_coverage_and_side_effect_boundaries(self):
        read=[row for row in MATRIX if row['method']=='GET']
        self.assertTrue(read)
        for row in read:
            self.assertIn(row['coverage'], {'first-screen','periodic','on-demand','after-operation'})
            self.assertIn('source',row)
            self.assertIn('offline',row)
            self.assertIn('mayWriteSourceState',row)

    def test_route_inventory_matches_current_dashboard_source(self):
        tree=ast.parse((Path(__file__).parents[1]/'app.py').read_text(encoding='utf-8'))
        actual=set()
        for node in tree.body:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                for deco in node.decorator_list:
                    if isinstance(deco,ast.Call) and isinstance(deco.func,ast.Attribute) and deco.func.attr in {'get','post'}:
                        path=ast.literal_eval(deco.args[0])
                        if path.startswith('/api/'):
                            actual.add((deco.func.attr.upper(),path))
        documented={(row['method'],row['path']) for row in MATRIX if row['source']=='dashboard'}
        self.assertEqual(actual,documented)
