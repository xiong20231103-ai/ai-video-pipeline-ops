"""Extract selected reviewed definitions; never import the production app."""
import ast
from contextlib import closing,contextmanager
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'app.py'


def definitions(names,namespace):
    tree=ast.parse(SOURCE.read_text(encoding='utf-8-sig'))
    selected=[node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in names]
    selected.insert(0,ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0))
    module=ast.fix_missing_locations(ast.Module(body=selected,type_ignores=[]))
    exec(compile(module,'isolated-startup-shape','exec'),namespace)
    return namespace


class StartupShapeTests(unittest.TestCase):
    def test_module_call_inventory_requires_report_update_if_changed(self):
        tree=ast.parse(SOURCE.read_text(encoding='utf-8-sig'))
        calls={ast.unparse(call.func) for node in tree.body if isinstance(node,(ast.Assign,ast.AnnAssign,ast.Expr,ast.If))
               for call in ast.walk(node) if isinstance(call,ast.Call)}
        self.assertEqual({'ContextVar','Path','Path(__file__).resolve','re.compile','threading.RLock','threading.Lock',
                          'load_config','Store','Collector','FastAPI','app.add_middleware','app.mount','StaticFiles',
                          'uvicorn.run','str','int','CleanupTickets'},calls)

    def test_store_repeated_init_has_same_logical_schema_and_migration_rows(self):
        tree=ast.parse(SOURCE.read_text(encoding='utf-8-sig'))
        markers=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
                     and any(isinstance(target,ast.Name) and target.id=='LEGACY_DRAFT_CLEANUP_MARKERS' for target in node.targets))
        results=[]
        with tempfile.TemporaryDirectory() as folder:
            for count in (1,2):
                root=Path(folder)/str(count)
                ns=definitions({'Store'},dict(DATA_DIR=root,threading=threading,sqlite3=sqlite3,
                    contextmanager=contextmanager,LEGACY_DRAFT_CLEANUP_MARKERS=markers))
                path=root/'ops.db';store=ns['Store'](path)
                with store.connection() as db:
                    db.execute('INSERT INTO tasks(task_id,state,error) VALUES(?,?,?)',('fixture','Completed',markers[0]))
                for _ in range(count):ns['Store'](path)
                with closing(sqlite3.connect(path)) as db:
                    results.append((db.execute('SELECT name,sql FROM sqlite_master ORDER BY name').fetchall(),
                                    db.execute('SELECT task_id,state,error,draft_cleanup_status,draft_cleanup_warning FROM tasks').fetchall()))
            self.assertEqual(results[0],results[1])
            self.assertEqual(('fixture','Completed','','pending',markers[0]),results[0][1][0])

    def test_config_reads_are_same_only_while_file_is_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'config.json';path.write_text('{"listen_port":12345}')
            ns=definitions({'load_config'},dict(Path=Path,BASE_DIR=root,CONFIG_PATH=path,socket=socket,json=json))
            with patch.object(socket,'gethostname',return_value='fixture-host'):
                one=ns['load_config']();two=ns['load_config']()
                self.assertEqual(one,two)
                path.write_text('{"listen_port":12346}')
                self.assertNotEqual(one,ns['load_config']())

    def test_collector_constructor_has_no_thread_start_and_threads_are_lifespan_only(self):
        tree=ast.parse(SOURCE.read_text(encoding='utf-8-sig'))
        collector=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='Collector')
        init=next(node for node in collector.body if isinstance(node,ast.FunctionDef) and node.name=='__init__')
        calls=[ast.unparse(call.func) for call in ast.walk(init) if isinstance(call,ast.Call)]
        self.assertNotIn('threading.Thread',calls);self.assertFalse(any(call.endswith('.start') for call in calls))
        lifespan=next(node for node in tree.body if isinstance(node,ast.AsyncFunctionDef) and node.name=='lifespan')
        self.assertEqual(1,sum(isinstance(node,ast.Call) and ast.unparse(node.func)=='COLLECTOR.start' for node in ast.walk(lifespan)))


if __name__=='__main__':unittest.main()
