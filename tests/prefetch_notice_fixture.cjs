const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const body = source.slice(source.indexOf('function renderPrefetchWarnings('), source.indexOf('function renderDownloadFailures('));
const ids = {};
function node() {
  return {children: [], textContent: '', classList: {toggle() {}},
    appendChild(child) {this.children.push(child);},
    replaceChildren() {this.children = [];},
    addEventListener(name, fn) {this[name] = fn;},
    get childElementCount() {return this.children.length;}};
}
ids.downloadFailurePanel = {insertAdjacentElement(where, item) {ids[item.id] = item;}};
let opened;
const context = {$: id => ids[id], document: {createElement: node}, openReplenishment: (...args) => {opened = args;}};
vm.createContext(context);
// setAttribute is part of the actual DOM API used by the production function.
context.document.createElement = () => ({...node(), setAttribute() {}});
vm.runInContext(body, context);
const warning = {taskId:'task-6',batchSequence:6,project:'<img onerror=bad>',material:'碳岩板',failedLinks:[{url:'u'}]};
context.renderPrefetchWarnings({prefetchWarnings:[warning]});
assert.equal(ids.prefetchGapWarnings.children.length, 1);
const line = ids.prefetchGapWarnings.children[0];
assert.match(line.textContent, /提前下载缺 1 条/);
assert.match(line.textContent, /<img onerror=bad>/); // literal text, never HTML
line.children[0].click();
assert.equal(opened[0], 'task-6');
assert.equal(opened[1], warning);
context.renderPrefetchWarnings({});
assert.equal(ids.prefetchGapWarnings.children.length, 0);
console.log('prefetch notice DOM: passed');
