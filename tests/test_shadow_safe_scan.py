import random,re,string,unittest
from agent.core.snapshot import SnapshotError,safe_facts
from tools.shadow_capture import CaptureError,_PRIVATE_STRING,_safe

# The pattern before the speed-up, kept verbatim as the reference.
OLD=re.compile(r'''(?i)["']?[^"'\s]*(?:token|password|secret|webhook|authorization|cookie|api.?key)[^"'\s]*["']\s*[:=]|-----BEGIN .*PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}''')

SAMPLES=['', 'plain text', '"token": 1', "'Password'=x", 'my_api_key" : v', 'apikey"=1', 'api-key\'=', 'xTOKENy"  :',
         'token "=x', 'token\t"=', 'secret', 'cookie"', '"cookie"\n:', 'webhookUrl":"https://x"', 'authorization=Bearer',
         '-----BEGIN RSA PRIVATE KEY-----', 'ghp_'+'a'*30, 'ghp_'+'a'*29, 'github_pat_'+'b'*30, 'xghp_'+'a'*40,
         '"note": "token budget"', '"tokens": [1]', 'passwordless "=', "'secret'  =  1"]


class SafeScanEquivalenceTests(unittest.TestCase):
    def test_new_pattern_matches_exactly_when_old_pattern_matches(self):
        rng=random.Random(20261023)
        alphabet=string.ascii_letters+string.digits+'"\' \t\n:=_-{}[],.'
        words=['token','PASSWORD','secret','webhook','authorization','cookie','apikey','api_key','api-key','"',"'",':','=',' ']
        samples=list(SAMPLES)
        for _ in range(5000):
            parts=[rng.choice(words) if rng.random()<.4 else ''.join(rng.choice(alphabet) for _ in range(rng.randint(0,6))) for _ in range(rng.randint(1,8))]
            samples.append(''.join(parts))
        for sample in samples:
            self.assertEqual(bool(OLD.search(sample)),bool(_PRIVATE_STRING.search(sample)),sample)

    def test_safe_still_rejects_and_accepts_the_same_values(self):
        # Either layer may be the one that refuses; both did so before the change.
        for value in [{'token':'x'},{'nested':[{'apiKey':'x'}]},'"password": "x"',{'u':'https://a/b?token=1'},
                      {'u':'https://user:pw@a/b'},{'invitationLink':'x'},{'deep':{'deeper':{'list':['tskey-abc']}}},
                      'see "my_cookie" = 1','ghp_'+'a'*36]:
            with self.subTest(value=value),self.assertRaises((CaptureError,SnapshotError)):_safe(value)
        _safe({'batch':'10.22','items':[{'status':'done','note':'token budget fine'}],'url':'https://a/b?page=2'})

    def test_large_nested_state_scans_quickly(self):
        import time
        value={'tasks':[{'id':i,'status':'done','steps':[{'name':'s'+str(j),'note':'x'*40} for j in range(20)]} for i in range(3000)]}
        started=time.monotonic();_safe(value);safe_facts(value)
        # Previously quadratic in depth and per-key set rebuilds; generous bound.
        self.assertLess(time.monotonic()-started,10)


if __name__=='__main__':unittest.main()
