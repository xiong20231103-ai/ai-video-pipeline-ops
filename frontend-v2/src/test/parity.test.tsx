import { readFileSync } from 'node:fs'
import { resolve, sep } from 'node:path'
import { JSDOM } from 'jsdom'
import ts from 'typescript'
import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import Dashboard from '@/components/views/Dashboard'
import fixture from './fixture.json'
import { object as o, list, type Row } from '@/data/types'
import {
  heroFor,
  metricValues,
  uploadValues,
  currentValues,
  pipelineFor,
  commandLabels,
} from '@/components/views/presentation'
import { safetyEntries } from '@/data/legacy-formatters'

const root = resolve(process.cwd(), '..') + sep
const legacy = readFileSync(root + 'static/app.js', 'utf8')
const ast = ts.createSourceFile(
  'app.js',
  legacy,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.JS,
)
const declarations = ast.statements
  .filter((x) => ts.isFunctionDeclaration(x) || ts.isVariableStatement(x))
  .map((x) => x.getText(ast))
  .join('\n')
let parityData: Row = fixture.dashboard
let parityMode = 'home'
vi.mock('@/data/useDashboard', () => ({
  useDashboard: () => ({
    snapshot: {
      mode: parityMode,
      dashboard: parityData,
      safety: fixture.safety,
      status: fixture.status,
      commands: fixture.commands.items,
      backups: null,
      pendingDelete: fixture.pendingDelete,
      session: { username: '隔离账号' },
      error: '',
      healthFailures: 0,
      receivedAt: new Date(),
      receivedTick: performance.now(),
      sources: {},
      loading: false,
    },
    reader: { current: null },
    refresh: () => undefined,
  }),
}))
function reference(data: Row) {
  const dom = new JSDOM(readFileSync(root + 'static/index.html', 'utf8'), {
    runScripts: 'outside-only',
    url: 'https://reference.invalid/',
  })
  dom.window.eval(
    declarations +
      `\n globalThis.compareLegacy = data => {
    renderOverview(data.overview || {}, data.projectGaps?.items || []);
    renderPipelinePayload(data.pipeline || {}, data.currentProjectStatus || {});
    renderTasks(data.tasks?.items || []); renderTaskBoxes(data.taskBoxes || {});
    renderSafety(data.fixtureSafety || {});
    renderHealth(data.health || {}); renderProjectGaps(data.projectGaps?.items || []);
  };`,
  )
  const compare = Reflect.get(dom.window, 'compareLegacy') as (
    value: Row,
  ) => void
  compare(data)
  return dom
}
function projection(data: Row) {
  const values: Record<string, string | number> = {},
    hero = heroFor(data),
    overview = o(data.overview)
  values.heroTitle = hero.title
  values.heroSubtitle = hero.subtitle
  for (const x of metricValues(o(overview.metrics))) {
    values[x.key + 'Value'] = x.value
    values[x.key + 'Note'] = x.note
  }
  for (const [key, value] of Object.entries(currentValues(o(overview.current))))
    if (key !== 'category') values[key] = value
  const items = list(o(data.tasks).items)
  for (const key of ['total', 'waiting', 'running', 'completed', 'failed'])
    values['count' + key[0].toUpperCase() + key.slice(1)] =
      key === 'total'
        ? items.length
        : items.filter((x) => x.category === key).length
  const upload = uploadValues(o(pipelineFor(data).upload))
  values.uploadCardTitle = upload.title
  values.uploadCardMessage = upload.message
  values.uploadCardBadge = upload.badge
  if (upload.live)
    Object.assign(values, {
      uploadProgressLabel: upload.label,
      uploadProgressPercent: upload.percentage,
      uploadBytesText: upload.bytes,
      uploadSpeedText: upload.speed,
      uploadRemainingText: upload.remaining,
      uploadEtaText: upload.eta,
      uploadCurrentFile: upload.file,
    })
  return values
}
describe('old/new same-data parity, home and cloud', () => {
  for (const mode of ['home', 'cloud'])
    for (const scenario of ['baseline', 'empty', 'unconfigured']) {
      it(`${mode}: ${scenario} has zero field/state differences`, () => {
        const data: Row = structuredClone(fixture.dashboard)
        data.fixtureSafety = fixture.safety
        if (scenario === 'empty') {
          data.tasks = { items: [] }
          data.overview = { ...o(data.overview), current: null }
          data.projectGaps = { items: [] }
        }
        if (scenario === 'unconfigured')
          data.pipeline = {
            items: [
              { key: 'upload', state: 'unconfigured' },
              {
                key: 'download',
                state: 'failed',
                failed: 1,
                failureItems: [
                  { url: 'https://example.invalid', reason: '模拟失败' },
                ],
              },
            ],
          }
        const dom = reference(data),
          values = projection(data)
        try {
          parityData = data
          parityMode = mode
          const actual = new JSDOM(
            ['overview', 'tasks', 'uploads', 'health']
              .map((view) =>
                renderToStaticMarkup(
                  <Dashboard view={view as 'overview' | 'tasks' | 'uploads' | 'health'} />,
                ),
              )
              .join(''),
          )
          for (const [id, value] of Object.entries(values))
            expect(
              dom.window.document.getElementById(id)?.textContent,
              `${mode}/${scenario}/${id}`,
            ).toBe(String(value))
          for (const [id, value] of Object.entries(values))
            expect(
              actual.window.document.querySelector(`[data-legacy="${id}"]`)
                ?.textContent || '',
              `actual React ${mode}/${scenario}/${id}`,
            ).toBe(String(value))
          const safety = safetyEntries(fixture.safety)
          const normalize = (value: string | null) => (value || '').replace(/\s+/g, '')
          const cells = (document: Document, selector: string) => [...document.querySelectorAll(selector)].map(row => [...row.querySelectorAll('td')].map(cell => normalize(cell.textContent)))
          expect(cells(actual.window.document, '[data-panel="全流程状态"] table tbody tr').slice(0, 5)).toEqual(cells(dom.window.document, '#pipelineRows tr'))
          expect(cells(actual.window.document, '.task-group table tbody tr')).toEqual(cells(dom.window.document, '#taskRows tr:not(.task-group-row)').filter(row => row.length === 6))
          const tiles = (document: Document, selector: string) => [...document.querySelectorAll(selector)].map(node => normalize(node.textContent))
          expect(tiles(actual.window.document, '[data-panel="任务箱总览"] .taskbox-tile').slice(0, 1)).toEqual(tiles(dom.window.document, '#taskBoxItems article'))
          const referenceSafety = [
            ...dom.window.document.querySelectorAll('#safetyGrid article'),
          ].map((x) => ({
            title: x.querySelector('strong')?.textContent,
            text: x.querySelector('span')?.textContent,
          }))
          expect(safety.map(({ title, text }) => ({ title, text }))).toEqual(
            referenceSafety,
          )
          expect(values.cpuValue).not.toBe('0%')
          actual.window.close()
        } finally {
          dom.window.close()
        }
      })
    }
  it('uses every cloud receipt state and its exact original Chinese meaning', () => {
    const code = readFileSync(root + 'cloud/commands.js', 'utf8'),
      source = ts.createSourceFile(
        'commands.js',
        code,
        ts.ScriptTarget.Latest,
        true,
      )
    let literal = ''
    const visit = (node: ts.Node) => {
      if (
        ts.isVariableDeclaration(node) &&
        node.name.getText(source) === 'labels'
      )
        literal = node.initializer!.getText(source)
      ts.forEachChild(node, visit)
    }
    visit(source)
    expect(literal).not.toBe('')
    const original = new Function(`return (${literal})`)() as Record<
      string,
      string
    >
    expect(commandLabels).toEqual(original)
    expect(commandLabels.completed).toContain('业务进度请看原状态')
  })
})
