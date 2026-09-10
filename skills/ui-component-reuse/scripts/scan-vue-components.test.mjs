import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'

const script = fileURLToPath(new URL('./scan-vue-components.mjs', import.meta.url))
function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'component-map-test-'))
  t.after(() => fs.rmSync(root, { recursive: true, force: true }))
  const write = (name, content) => {
    const file = path.join(root, name)
    fs.mkdirSync(path.dirname(file), { recursive: true })
    fs.writeFileSync(file, content)
  }
  return {
    root, write,
    run: (...args) => execFileSync(process.execPath, [script, root, ...args], { encoding: 'utf8', stdio: 'pipe' }),
    read: () => fs.readFileSync(path.join(root, 'docs/component-map.md'), 'utf8'),
  }
}
const names = (content) => [...content.matchAll(/^\| (\w+) \| `src\//gm)].map(m => m[1])

test('已有索引同步增删、接口、引用位置和数量，并按当前数据重新排序', t => {
  const f = fixture(t)
  f.write('src/components/Alpha.vue', '<template><div /></template>')
  f.write('src/components/Beta.vue', '<template><div /></template>')
  f.write('src/components/Removed.vue', '<template><div /></template>')
  f.write('src/views/One.vue', '<template><Alpha /><Beta /></template>')
  f.write('src/views/Two.vue', '<template><Alpha /></template>')
  f.run()
  assert.deepEqual(names(f.read()), ['Alpha', 'Beta', 'Removed'])
  fs.unlinkSync(path.join(f.root, 'src/components/Removed.vue'))
  f.write('src/components/Gamma.vue', '<template><div /></template>')
  f.write('src/components/Beta.vue', '<script setup lang="ts">defineProps<{ title: string }>()</script><template><div /></template>')
  f.write('src/views/Two.vue', '<template><Beta /><Beta /><Gamma /></template>')
  f.run()
  assert.deepEqual(names(f.read()), ['Beta', 'Alpha', 'Gamma'])
  assert.match(f.read(), /\| Beta \|[^\n]*\| title \| - \| 2 \| 3 \|/)
  assert.match(f.read(), /\| Alpha \|[^\n]*\| 1 \| 1 \| src\/views\/One.vue \|/)
})

test('仅有行顺序错误也会修正；无变化时不写文件', t => {
  const f = fixture(t)
  for (const name of ['Alpha', 'Beta']) f.write(`src/components/${name}.vue`, '<template><div /></template>')
  f.run()
  const lines = f.read().split('\n')
  const a = lines.findIndex(l => l.startsWith('| Alpha |'))
  const b = lines.findIndex(l => l.startsWith('| Beta |'))
  ;[lines[a], lines[b]] = [lines[b], lines[a]]
  f.write('docs/component-map.md', lines.join('\n'))
  f.run()
  assert.deepEqual(names(f.read()), ['Alpha', 'Beta'])
  const file = path.join(f.root, 'docs/component-map.md')
  fs.utimesSync(file, 1000, 1000)
  const before = f.read()
  f.run()
  assert.equal(f.read(), before)
  assert.equal(fs.statSync(file).mtimeMs, 1000000)
})

test('保留用途、含转义竖线的备注、自定义列、表外说明及设计记录', t => {
  const f = fixture(t)
  f.write('src/components/Alpha.vue', '<template><div /></template>')
  const prefix = '# 我的组件索引\n\n> 自定义说明\n\n## 公共组件\n\n表格前的说明。\n\n'
  const suffix = '\n\n表格后的说明。\n\n## 设计稿拆组件记录\n\n| 页面/需求 | 决策说明 |\n| --- | --- |\n| 页面甲 | 保留既有设计 |\n\n## 其他说明\n\n原样保留。\n'
  f.write('docs/component-map.md', prefix + '| 组件 | 路径 | 用途 | 引用次数 | 备注 | 负责人 |\n| --- | --- | --- | --- | --- | --- |\n| Alpha | `src/components/Alpha.vue` | **筛选** `A\\|B` | 99 | 备注甲\\|乙 | 张三 |' + suffix)
  f.run()
  const content = f.read()
  assert.ok(content.startsWith(prefix))
  assert.ok(content.includes(suffix))
  assert.match(content, /\*\*筛选\*\* `A\\\|B`/)
  assert.match(content, /备注甲\\\|乙 \| 张三/)
  assert.ok(!content.includes('引用次数'))
  assert.match(content, /\| 引用文件数 \| 模板使用次数 \| 引用位置 \|/)
  const before = f.read()
  f.run()
  assert.equal(f.read(), before)
})

test('局部组件重新排序并刷新候选，同时保留已写明原因的公共化判断', t => {
  const f = fixture(t)
  for (const name of ['Alpha', 'Beta']) f.write(`src/views/Home/components/${name}.vue`, '<template><div /></template>')
  f.run()
  f.write('docs/component-map.md', f.read().replace(/(\| Beta \|[^\n]*)\| 否 \|/, '$1| 否：依赖当前页面权限 |'))
  f.write('src/views/One.vue', '<template><Alpha /><Beta /></template>')
  f.write('src/views/Two.vue', '<template><Alpha /><Alpha /><Beta /></template>')
  const output = f.run()
  assert.deepEqual(names(f.read()), ['Alpha', 'Beta'])
  assert.match(f.read(), /\| Alpha \|[^\n]*\| 2 \| 3 \|[^\n]*\| 建议评估 \|/)
  assert.match(f.read(), /\| Beta \|[^\n]*\| 否：依赖当前页面权限 \|/)
  assert.ok(output.includes('Alpha') && output.includes('Beta'))
})

test('--check 仅检查，不创建或更新正式索引', t => {
  const f = fixture(t)
  f.write('src/components/Alpha.vue', '<template><div /></template>')
  f.run('--check')
  assert.ok(!fs.existsSync(path.join(f.root, 'docs')))
  f.run()
  const before = f.read()
  f.write('src/components/Beta.vue', '<template><div /></template>')
  f.run('--check')
  assert.equal(f.read(), before)
  f.run()
  assert.ok(f.read().includes('| Beta |'))
})

test('目标目录缺少 src 时不清空已有索引', t => {
  const f = fixture(t)
  const original = '# 保留已有索引\n'
  f.write('docs/component-map.md', original)
  assert.throws(() => f.run(), /src/)
  assert.equal(f.read(), original)
})

test('列数异常时拒绝写入，避免吞掉人工内容', t => {
  const f = fixture(t)
  f.write('src/components/Alpha.vue', '<template><div /></template>')
  const original = '## 公共组件\n\n| 组件 | 路径 | 用途 |\n| --- | --- | --- |\n| Alpha | `src/components/Alpha.vue` | 用途 | 多出的说明 |\n'
  f.write('docs/component-map.md', original)
  assert.throws(() => f.run(), /列数不匹配/)
  assert.equal(f.read(), original)
  f.run('--force')
  assert.match(f.read(), /\| Alpha \|/)
  assert.ok(!f.read().includes('多出的说明'))
})

test('保留 CRLF 换行；仅显式 --force 才丢弃自定义内容', t => {
  const f = fixture(t)
  f.write('src/components/Alpha.vue', '<template><div /></template>')
  f.run()
  f.write('docs/component-map.md', (f.read() + '\n## 说明\n\n保留自定义内容\n').replace(/\n/g, '\r\n'))
  f.write('src/views/One.vue', '<template><Alpha /></template>')
  f.run()
  assert.ok(f.read().includes('保留自定义内容'))
  assert.ok(!/(?<!\r)\n/.test(f.read()))
  f.run('--force')
  assert.ok(!f.read().includes('保留自定义内容'))
})
