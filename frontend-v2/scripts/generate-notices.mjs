import { readFileSync, readdirSync, writeFileSync, existsSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'
import { resolve } from 'node:path'

const root = fileURLToPath(new URL('..', import.meta.url))
const project = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'))
const lock = JSON.parse(readFileSync(resolve(root, 'package-lock.json'), 'utf8'))
const direct = ['dependencies', 'devDependencies'].flatMap(group => Object.entries(project[group]).map(([name, version]) => {
  const entry = JSON.parse(readFileSync(resolve(root, 'node_modules', name, 'package.json'), 'utf8'))
  return { name, version, license: entry.license, role: group === 'dependencies' ? 'runtime (shared JS chunks)' : 'build/test only (0 runtime JS)' }
})).sort((a, b) => a.name.localeCompare(b.name, 'en'))
writeFileSync(resolve(root, 'public/dependencies.json'), JSON.stringify(direct, null, 2) + '\n')

const sections = ['Third-party runtime notices for Ops Dashboard V2\n\nVendored component licenses: licenses/shadcn-ui.LICENSE.md and licenses/react-bits.LICENSE.md.\n']
for (const [location, meta] of Object.entries(lock.packages).sort(([a], [b]) => a.localeCompare(b, 'en'))) {
  if (!location || meta.dev || !existsSync(resolve(root, location))) continue
  const dir = resolve(root, location)
  const pkg = JSON.parse(readFileSync(resolve(dir, 'package.json'), 'utf8'))
  const licenses = readdirSync(dir).filter(name => /^(licen[sc]e|copying)(\.|$)/i.test(name))
  // The published 2.3.8 tarball omits LICENSE. Copy its official fixed license blob.
  // https://github.com/theKashey/react-remove-scroll-bar/blob/master/LICENSE
  // Git blob SHA1: 7c08c3990396ecefd90f99ff5d9a34f26f5b5616
  const fallback = pkg.name === 'react-remove-scroll-bar' && pkg.version === '2.3.8'
    ? resolve(root, 'public/licenses/react-remove-scroll-bar.LICENSE') : null
  if (!licenses.length && !fallback) throw new Error(`No runtime license file found: ${location}`)
  const text = (licenses.length ? licenses.map(name => readFileSync(resolve(dir, name), 'utf8')).join('\n') : readFileSync(fallback, 'utf8')).replaceAll('\r\n', '\n')
  sections.push(`\n--- ${pkg.name}@${pkg.version} (${pkg.license}) ---\n\n${text}\n`)
}
writeFileSync(resolve(root, 'public/THIRD_PARTY_NOTICES.txt'), sections.join('').trimEnd() + '\n')
