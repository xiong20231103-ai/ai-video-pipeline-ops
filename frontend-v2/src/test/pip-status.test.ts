import { describe, it, expect } from 'vitest';
import { capcutSessionNotice } from '../data/pip-status';
const row = {mode:'pip',executorOnline:true,heartbeatEpoch:1000,sessionId:2,state:'busy'};
const wrap = (value: object) => ({overview:{pipeline:{capcut:{capcutSession:value}}}});
describe('PiP runtime status',()=>{
 it('preserves legacy main view',()=>expect(capcutSessionNotice({})).toBeNull());
 it('allows fresh busy executor',()=>expect(capcutSessionNotice(wrap(row),1001)?.online).toBe(true));
 it('refuses stale and future heartbeats',()=>{expect(capcutSessionNotice(wrap(row),1016)?.online).toBe(false);expect(capcutSessionNotice(wrap(row),999)?.online).toBe(false);});
 it('requires positive child session',()=>expect(capcutSessionNotice(wrap({...row,sessionId:0}),1001)?.online).toBe(false));
 it('does not advertise online after workbench marks it offline',()=>expect(capcutSessionNotice(wrap({...row,executorOnline:false}),1001)?.online).toBe(false));
});
