const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../cloud/material_handoff.js'), 'utf8');

class Element {
  constructor(tag = 'div') { this.tag = tag; this.children = []; this.value = ''; this.checked = false; this.disabled = true; this.textContent = ''; }
  append(node) { this.children.push(node); }
  replaceChildren() { this.children = []; }
  set value(value) { this._value = value; }
  get value() { return this._value || (this.tag === 'select' ? this.children[0]?.value || '' : ''); }
}
async function fixture({ lostAck = false } = {}) {
  const elements = new Map(['message','status','audit','reason','stopped','submit','takeover','refresh','package-note'].map(id => [id, new Element()]));
  elements.set('package', new Element('select')); elements.set('target', new Element('select'));
  elements.get('target').value = 'home';
  const packageRow = { id: 'fixture-package', device: 'office', committed_at: 1000, summary: { unresolved: { imports: 1 } } };
  let state = { generation: 'fixture-generation', epoch: 1, holder: 'office', phase: 'active', lease_lost: false,
    lease_until: 1100, last_contact_at: 1000, package: packageRow, current_package: packageRow.id,
    candidates: [packageRow], audit: [], storage: { reserved_bytes: 100, cap_bytes: 1000 } };
  let nextId = 0;
  const posts = [];
  const context = vm.createContext({ document: { getElementById: id => elements.get(id), createElement: tag => new Element(tag) },
    crypto: { randomUUID: () => 'fixture-request-' + ++nextId },
    fetch: async (url, options) => {
      if (url === '/auth/session') return { ok: true, json: async () => ({ csrf: 'fixture-csrf' }) };
      if (url.endsWith('/status')) return { ok: true, json: async () => structuredClone(state) };
      assert(url.endsWith('/force-takeover'));
      const body = JSON.parse(options.body); posts.push({ body, headers: options.headers });
      if (lostAck && posts.length === 1) throw Error('fixture dropped acknowledgement');
      state = { ...state, holder: body.target_device, phase: 'preparing', epoch: state.epoch + 1 };
      return { ok: true, json: async () => structuredClone(state) };
    } });
  vm.runInContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  return { elements, posts };
}

test('confirmation is never preselected and no mutation occurs on read', async () => {
  const { elements, posts } = await fixture();
  assert.equal(elements.get('stopped').checked, false);
  assert.equal(elements.get('submit').disabled, true);
  assert.equal(posts.length, 0);
  elements.get('reason').value = 'fixture stopped';
  elements.get('stopped').checked = true;
  elements.get('stopped').oninput();
  assert.equal(elements.get('submit').disabled, false);
  await elements.get('refresh').onclick();
  assert.equal(elements.get('stopped').checked, false);
  assert.equal(elements.get('submit').disabled, true);
  assert.equal(posts.length, 0);
});

test('lost acknowledgement retries the same request and successful takeover re-confirms', async () => {
  const { elements, posts } = await fixture({ lostAck: true });
  elements.get('reason').value = 'fixture shutdown';
  elements.get('stopped').checked = true;
  elements.get('stopped').oninput();
  const submit = () => elements.get('takeover').onsubmit({ preventDefault() {} });
  await submit();
  assert.equal(posts.length, 1);
  assert(elements.get('message').textContent.includes('勿假定未执行'));
  await submit();
  assert.equal(posts.length, 2);
  assert.equal(posts[0].body.request_id, posts[1].body.request_id);
  assert.equal(posts[1].headers['X-CSRF-Token'], 'fixture-csrf');
  assert.equal(posts[1].body.other_device_stopped, true);
  assert.equal(posts[1].body.epoch, 1);
  assert.equal(elements.get('stopped').checked, false);
  assert(elements.get('message').textContent.includes('激活成功后才能开工'));
});
