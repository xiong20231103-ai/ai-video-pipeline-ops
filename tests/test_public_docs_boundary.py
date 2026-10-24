from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from tools.check_public_docs import violations


class PublicDocsBoundaryTests(unittest.TestCase):
    def test_repository_has_no_private_documents(self):
        self.assertEqual(violations(Path(__file__).resolve().parents[1]),[])

    def test_nested_docs_and_handoff_files_are_blocked(self):
        with TemporaryDirectory(prefix='public-docs-boundary-') as folder:
            root=Path(folder);(root/'docs'/'nested').mkdir(parents=True)
            (root/'docs'/'nested'/'review.md').write_text('synthetic review',encoding='utf-8')
            (root/'交接记录_fixture.md').write_text('synthetic handoff',encoding='utf-8')
            (root/'家庭电脑部署说明.md').write_text('synthetic deployment',encoding='utf-8')
            self.assertEqual(violations(root),['docs/nested/review.md','交接记录_fixture.md','家庭电脑部署说明.md'])

    def test_code_readmes_and_runtime_contracts_are_allowed(self):
        with TemporaryDirectory(prefix='public-docs-boundary-') as folder:
            root=Path(folder);(root/'contracts'/'migration').mkdir(parents=True)
            (root/'contracts'/'migration'/'r1-provenance.json').write_text('{}',encoding='utf-8')
            for name in ('README.md','AGENTS.md'):(root/name).write_text('synthetic',encoding='utf-8')
            self.assertEqual(violations(root),[])
