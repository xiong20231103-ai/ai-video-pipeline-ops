import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools.shadow_stage_package import stage
from tools.shadow_capture import CaptureError
class StagePackageTests(unittest.TestCase):
    def test_git_objects_only_excludes_working_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'repo';repo.mkdir();out=root/'package';sha='a'*40
            names=['agent/readonly.py','tools/shadow_capture_runtime.py','tools/shadow_replay_worker.py','tools/shadow_agent_observer.py','config.json','data/ops.db','voice-client/data/copy_library.csv']
            def git(args,**kwargs):
                op=args[3]
                if op=='rev-parse':return (sha+'\n').encode()
                if op=='ls-tree' and '-r' in args:return ('\0'.join(names)+'\0').encode()
                if op=='ls-tree':return b'100644 blob fixture\tfile\n'
                if op=='show':return b'# synthetic source\n'
                raise AssertionError(args)
            with patch('tools.shadow_stage_package.subprocess.check_output',side_effect=git):result=stage(repo,sha,out)
            self.assertEqual(4,result['files']);self.assertFalse(result['enabled']);self.assertFalse((out/'config.json').exists())
            manifest=json.loads((out/'shadow-package.json').read_bytes());self.assertEqual(4,len(manifest['files']))
    def test_nonexact_commit_and_reused_destination_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'repo';repo.mkdir();out=root/'package';out.mkdir()
            for sha in ['main','a'*40]:
                with self.assertRaises(CaptureError):stage(repo,sha,out)
    def test_source_tree_destination_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp)
            with self.assertRaises(CaptureError):stage(repo,'a'*40,repo/'new')
if __name__=='__main__':unittest.main()
