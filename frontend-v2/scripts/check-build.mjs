import { execFileSync } from 'node:child_process'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'
import { relative, resolve } from 'node:path'
import { createHash } from 'node:crypto'

const root = fileURLToPath(new URL('../..', import.meta.url))
const git = args => execFileSync('git', ['-c', `safe.directory=${root.replaceAll('\\', '/')}`, '-C', root, ...args], { windowsHide: true })
const tracked = git(['ls-files', '-z', 'static/v2']).toString().split('\0').filter(Boolean).sort()
function list(dir) {
  return readdirSync(dir).sort().flatMap(name => {
    const path = resolve(dir, name)
    return statSync(path).isDirectory() ? list(path) : [relative(root, path).replaceAll('\\', '/')]
  })
}
const built = list(resolve(root, 'static/v2')).sort()
const hash = content => createHash('sha256').update(content).digest('hex')
if (JSON.stringify(tracked) !== JSON.stringify(built)) throw new Error('Build file set differs from the committed static/v2 file set (including untracked files).')
for (const file of built) {
  if (hash(readFileSync(resolve(root, file))) !== hash(git(['show', `HEAD:${file}`]))) throw new Error(`Build bytes differ: ${file}`)
}
console.log(`Build matches committed static/v2 byte-for-byte (${built.length} files).`)
