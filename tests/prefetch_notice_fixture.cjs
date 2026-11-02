const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const body = source.slice(source.indexOf('function renderPrefetchWarnings('), source.indexOf('function renderDownloadFailures('));
const viewsBody = source.slice(source.indexOf('function renderPrefetchViews('), source.indexOf('function renderPrefetchWarnings('));
const labelBody = source.slice(source.indexOf('function prefetchLabel('), source.indexOf('function openCardPrefetch('));
const ids = {};
function node() {
  return {children: [], textContent: '', classList: {toggle() {}},
    appendChild(child) {this.children.push(child);},
    replaceChildren() {this.children = [];},
    addEventListener(name, fn) {this[name] = fn;},
    get childElementCount() {return this.children.length;}};
}
ids.gapQuickBar = {insertAdjacentElement(where, item) {assert.equal(where,'afterend');ids[item.id] = item;}};
let opened;
const context = {window:{}, $: id => ids[id], document: {createElement: node}, openReplenishment: (...args) => {opened = args;}};
vm.createContext(context);
// setAttribute is part of the actual DOM API used by the production function.
context.document.createElement = () => ({...node(), setAttribute() {}});
vm.runInContext(body, context);
vm.runInContext(viewsBody + labelBody, context);
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
const view={taskId:'task-6',sequence:6,project:'项目',material:'材料',state:'finished',canReplenish:true,missingCount:3,completed:23,total:26,acceptedPending:0};
context.renderPrefetchViews([view]);
assert.equal(ids.prefetchGapWarnings.children.length,1);
assert.match(ids.prefetchGapWarnings.children[0].textContent,/提前下载缺 3 条/);
assert.match(context.prefetchLabel(view),/已提前下载 23\/26/);
assert.match(context.prefetchLabel({...view,state:'running'}),/提前下载中/);
assert.match(context.prefetchLabel({...view,state:'interrupted'}),/已中断，稍后续下/);
assert.match(context.prefetchLabel({...view,acceptedPending:3}),/已提前补链 3 条，轮到时下载/);
context.renderPrefetchViews([{...view,state:'interrupted',canReplenish:false}]);
assert.equal(ids.prefetchGapWarnings.children.length,0);
context.window.opsCloudPrefetchReadOnly=true;
context.renderPrefetchViews([view]);
const hint=ids.prefetchGapWarnings.children[0].children[0];
assert.equal(hint.textContent,'请在家里 Dashboard 补链');
assert.equal(hint.click,undefined);
console.log('prefetch notice DOM: passed');
