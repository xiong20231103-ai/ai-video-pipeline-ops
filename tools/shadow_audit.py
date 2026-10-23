"""Audit recorded evidence without touching installed production processes or state."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.shadow_evidence_audit import audit_passive
from agent.core.oracle import LEGACY_SOURCE_SHA256
from agent.core.snapshot import no_links


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--evidence',required=True,type=Path)
    p.add_argument('--batch-id',required=True)
    p.add_argument('--since');p.add_argument('--until')
    p.add_argument('--source',type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args(argv)
    out=no_links(a.out);root=no_links(a.evidence)
    if out.exists() or out==root or out.is_relative_to(root):raise ValueError('new_disjoint_output_required')
    result=audit_passive(root,a.batch_id,since=a.since,until=a.until,source=a.source,expected_source=LEGACY_SOURCE_SHA256)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ('batchId','counts','blockers','comparable','realShadowPassed')}))
    return 0
if __name__=='__main__':raise SystemExit(main())
