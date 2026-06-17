#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'

const args = process.argv.slice(2)
const shouldForce = args.includes('--force')
const projectArg = args.find((arg) => !arg.startsWith('--'))
const cwd = projectArg ? path.resolve(projectArg) : process.cwd()
const indexFile = path.resolve(cwd, 'docs/component-map.md')

const includeRoots = [
  { dir: path.join(cwd, 'src/components'), scope: '公共组件' },
  { dir: path.join(cwd, 'src/views'), scope: '页面局部组件' },
]

function walkVueFiles(dir) {
  if (!fs.existsSync(dir)) return []
  const result = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('.')) continue
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      result.push(...walkVueFiles(full))
    } else if (entry.isFile() && entry.name.endsWith('.vue')) {
      result.push(full)
    }
  }
  return result
}

function toPosix(file) {
  return path.relative(cwd, file).split(path.sep).join('/')
}

function escapeCell(value) {
  return String(value || '').replace(/\|/g, '\\|').replace(/\n/g, '<br>')
}

function extractTypeArgument(content, name) {
  const start = content.indexOf(`${name}<`)
  if (start < 0) return ''
  const open = content.indexOf('<', start)
  let depth = 0
  for (let i = open; i < content.length; i++) {
    const ch = content[i]
    if (ch === '<') depth++
    if (ch === '>') depth--
    if (depth === 0) return content.slice(open + 1, i)
  }
  return ''
}

function extractRuntimeObject(content, name) {
  const start = content.indexOf(`${name}(`)
  if (start < 0) return ''
  const open = content.indexOf('(', start)
  let depth = 0
  for (let i = open; i < content.length; i++) {
    const ch = content[i]
    if (ch === '(') depth++
    if (ch === ')') depth--
    if (depth === 0) return content.slice(open + 1, i)
  }
  return ''
}

function extractNamesFromTypeBlock(block) {
  if (!block) return []
  const names = new Set()
  const interfaceBody = block.match(/\{([\s\S]*)\}/)?.[1] || block
  for (const match of interfaceBody.matchAll(/['"]?([A-Za-z_$][\w$-]*)['"]?\??\s*:/g)) {
    names.add(match[1])
  }
  return [...names]
}


function extractEmitNames(block) {
  if (!block) return []
  const names = new Set()
  const interfaceBody = block.match(/\{([\s\S]*)\}/)?.[1] || block
  for (const match of interfaceBody.matchAll(/(?:^|[;\n])\s*['"]([^'"]+)['"]\s*:/g)) {
    names.add(match[1])
  }
  for (const match of interfaceBody.matchAll(/(?:^|[;\n])\s*([A-Za-z_$][\w$-]*)\??\s*:/g)) {
    names.add(match[1])
  }
  return [...names]
}

function extractDefineOptionsName(content) {
  const match = content.match(/defineOptions\s*\(\s*\{[\s\S]*?name\s*:\s*['"]([^'"]+)['"]/)
  return match?.[1]
}

function extractCommentSummary(content) {
  const scriptComment = content.match(/<script[\s\S]*?>\s*\/\*\*([\s\S]*?)\*\//)?.[1]
  const htmlComment = content.match(/<template>\s*<!--([\s\S]*?)-->/)?.[1]
  const raw = scriptComment || htmlComment || ''
  return raw
    .split('\n')
    .map((line) => line.replace(/^\s*\*\s?/, '').trim())
    .filter(Boolean)
    .slice(0, 2)
    .join('；')
}

function splitWords(value) {
  return String(value || '')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
}

function hasAny(words, candidates) {
  return candidates.some((candidate) => words.includes(candidate))
}

function toKebabCase(value) {
  return String(value || '')
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/[\s_]+/g, '-')
    .toLowerCase()
}

function stripMarkdown(value) {
  return String(value || '')
    .replace(/<br\s*\/?\>/gi, '\n')
    .replace(/`/g, '')
    .trim()
}

function inferUsage({ name, path: rel, props, scope, view }) {
  const words = splitWords(`${name} ${rel}`)
  const propWords = splitWords(props.join(' '))
  const isPageLocal = scope === '页面局部组件'
  const prefix = isPageLocal && view && view !== '未识别' ? `${view} 页面` : ''
  const withPrefix = (text) => `${prefix}${text}`.trim()

  if (hasAny(words, ['chart', 'echarts']) || rel.includes('/charts/')) {
    if (hasAny(words, ['bar', 'column', 'histogram'])) return withPrefix('柱状图展示组件')
    if (hasAny(words, ['line', 'trend'])) return withPrefix('趋势折线图展示组件')
    if (hasAny(words, ['pie', 'ring', 'donut', 'doughnut'])) return withPrefix('饼图/环形图展示组件')
    if (hasAny(words, ['rank', 'ranking'])) return withPrefix('排行图表组件')
    if (hasAny(words, ['map'])) return withPrefix('地图图表组件')
    return withPrefix('图表展示组件')
  }

  if (hasAny(words, ['search', 'filter', 'query'])) return withPrefix('筛选查询组件')
  if (hasAny(words, ['form'])) return withPrefix('表单组件')
  if (hasAny(words, ['modal', 'dialog', 'popup'])) return withPrefix('弹窗组件')
  if (hasAny(words, ['drawer'])) return withPrefix('抽屉组件')
  if (hasAny(words, ['table', 'grid'])) return withPrefix('表格组件')
  if (hasAny(words, ['list'])) return withPrefix('列表组件')
  if (hasAny(words, ['card'])) return withPrefix('卡片容器组件')
  if (hasAny(words, ['panel', 'pane'])) return withPrefix('面板容器组件')
  if (hasAny(words, ['header', 'head'])) return withPrefix('头部区域组件')
  if (hasAny(words, ['title'])) return withPrefix('标题展示组件')
  if (hasAny(words, ['tag', 'badge', 'status'])) return withPrefix('状态标识组件')
  if (hasAny(words, ['tabs', 'tab'])) return withPrefix('标签页切换组件')
  if (hasAny(words, ['tree'])) return withPrefix('树形选择/展示组件')
  if (hasAny(words, ['upload', 'uploader'])) return withPrefix('上传组件')
  if (hasAny(words, ['editor'])) return withPrefix('编辑器组件')
  if (hasAny(words, ['detail', 'info', 'profile'])) return withPrefix('详情信息展示组件')
  if (hasAny(words, ['statistic', 'statistics', 'stats', 'metric', 'count', 'number'])) return withPrefix('指标数据展示组件')
  if (hasAny(words, ['toolbar', 'actions', 'operation', 'operate'])) return withPrefix('操作区组件')
  if (hasAny(words, ['empty'])) return withPrefix('空状态组件')
  if (hasAny(words, ['loading', 'skeleton'])) return withPrefix('加载状态组件')
  if (hasAny(words, ['layout', 'container', 'wrapper'])) return withPrefix('布局容器组件')

  if (hasAny(propWords, ['page', 'pagesize', 'total'])) return withPrefix('分页数据展示组件')
  if (hasAny(propWords, ['items', 'list'])) return withPrefix('列表数据展示组件')
  if (hasAny(propWords, ['data', 'dataset', 'series'])) return withPrefix('数据展示组件')
  if (hasAny(propWords, ['title'])) return withPrefix('带标题内容展示组件')

  return `${name} 组件（用途需结合源码确认）`
}

function collectUsage(allTextFiles, componentFile, componentName) {
  const base = componentName || path.basename(componentFile, '.vue')
  const fileBase = path.basename(componentFile, '.vue')
  const names = [...new Set([base, fileBase].filter(Boolean))]
  const kebabNames = names.map(toKebabCase)
  const rel = toPosix(componentFile).replace(/\.vue$/, '')
  const aliasRel = '@/' + rel.replace(/^src\//, '')
  const refs = new Set()
  let templateUseCount = 0

  for (const file of allTextFiles) {
    if (file === componentFile) continue
    const content = fs.readFileSync(file, 'utf8')
    const relFile = toPosix(file)
    const hasImportLikeRef = names.some((name) => content.includes(name)) || content.includes(rel) || content.includes(aliasRel)

    let fileTemplateUseCount = 0
    if (file.endsWith('.vue')) {
      for (const name of names) {
        fileTemplateUseCount += [...content.matchAll(new RegExp(`<${name}(?=[\\s>/])`, 'g'))].length
      }
      for (const name of kebabNames) {
        fileTemplateUseCount += [...content.matchAll(new RegExp(`<${name}(?=[\\s>/])`, 'g'))].length
      }
    }

    if (hasImportLikeRef || fileTemplateUseCount > 0) refs.add(relFile)
    templateUseCount += fileTemplateUseCount
  }

  return { refs: [...refs], templateUseCount }
}

function walkTextFiles(dir) {
  if (!fs.existsSync(dir)) return []
  const result = []
  const skip = new Set(['node_modules', 'dist', 'build', '.git'])
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('.') && entry.name !== '.env') continue
    if (entry.isDirectory()) {
      if (!skip.has(entry.name)) result.push(...walkTextFiles(path.join(dir, entry.name)))
    } else if (entry.isFile() && /\.(vue|ts|tsx|js|jsx)$/.test(entry.name)) {
      result.push(path.join(dir, entry.name))
    }
  }
  return result
}

const publicFiles = walkVueFiles(path.join(cwd, 'src/components'))
const viewFiles = walkVueFiles(path.join(cwd, 'src/views')).filter((file) => file.split(path.sep).includes('components'))
const allTextFiles = walkTextFiles(path.join(cwd, 'src'))

function inspect(file, scope) {
  const content = fs.readFileSync(file, 'utf8')
  const props = extractNamesFromTypeBlock(extractTypeArgument(content, 'defineProps') || extractRuntimeObject(content, 'defineProps'))
  const emits = extractEmitNames(extractTypeArgument(content, 'defineEmits') || extractRuntimeObject(content, 'defineEmits'))
  const name = extractDefineOptionsName(content) || path.basename(file, '.vue')
  const usage = collectUsage(allTextFiles, file, name)
  const refs = usage.refs
  const rel = toPosix(file)
  const viewMatch = rel.match(/^src\/views\/([^/]+)/)
  return {
    name,
    path: rel,
    scope,
    view: scope === '页面局部组件' ? (viewMatch?.[1] || '未识别') : '-',
    props: props.join(', ') || '-',
    emits: emits.join(', ') || '-',
    refs,
    templateUseCount: usage.templateUseCount,
    summary: extractCommentSummary(content) || inferUsage({
      name,
      path: rel,
      props,
      scope,
      view: scope === '页面局部组件' ? (viewMatch?.[1] || '未识别') : '-',
    }),
  }
}

const rows = [
  ...publicFiles.map((file) => inspect(file, '公共组件')),
  ...viewFiles.map((file) => inspect(file, '页面局部组件')),
].sort((a, b) => b.refs.length - a.refs.length || b.templateUseCount - a.templateUseCount || a.path.localeCompare(b.path))

const now = new Date().toISOString().slice(0, 10)
function buildLines() {
  const lines = []
  lines.push('# 组件图谱索引')
lines.push('')
lines.push(`> 生成日期：${now}`)
lines.push('> 扫描范围：`src/components/**/*.vue`、`src/views/**/components/**/*.vue`。')
lines.push('> 本文件是项目正式组件索引；后续 UI / 组件开发前先读取，开发后同步更新。')
lines.push('')
lines.push('## 公共组件')
lines.push('')
lines.push('| 组件 | 路径 | 用途 | Props | Emits | 引用文件数 | 模板使用次数 | 引用位置 |')
lines.push('| --- | --- | --- | --- | --- | --- | --- | --- |')
for (const item of rows.filter((row) => row.scope === '公共组件')) {
  lines.push(`| ${escapeCell(item.name)} | \`${escapeCell(item.path)}\` | ${escapeCell(item.summary)} | ${escapeCell(item.props)} | ${escapeCell(item.emits)} | ${item.refs.length} | ${item.templateUseCount} | ${escapeCell(item.refs.join('<br>') || '-')} |`)
}
lines.push('')
lines.push('## 页面局部组件')
lines.push('')
lines.push('| 组件 | 路径 | 所属 view | 用途 | Props | Emits | 引用文件数 | 模板使用次数 | 引用位置 | 是否建议公共化 |')
lines.push('| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |')
for (const item of rows.filter((row) => row.scope === '页面局部组件')) {
  const promote = item.refs.length >= 2 ? '建议评估' : '否'
  lines.push(`| ${escapeCell(item.name)} | \`${escapeCell(item.path)}\` | ${escapeCell(item.view)} | ${escapeCell(item.summary)} | ${escapeCell(item.props)} | ${escapeCell(item.emits)} | ${item.refs.length} | ${item.templateUseCount} | ${escapeCell(item.refs.join('<br>') || '-')} | ${promote} |`)
}
lines.push('')
return lines
}


function parseExistingIndex(content) {
  const items = new Map()
  const lines = content.split(/\r?\n/)
  let header = null
  for (const line of lines) {
    if (!line.startsWith('|')) continue
    const cells = line.split('|').slice(1, -1).map((cell) => stripMarkdown(cell))
    if (cells.length < 2) continue
    if (cells.every((cell) => /^-+$/.test(cell.replace(/\s/g, '')))) continue
    if (cells.includes('组件') && cells.includes('路径')) {
      header = cells
      continue
    }
    if (!header) continue
    const row = {}
    header.forEach((name, index) => { row[name] = cells[index] || '' })
    const componentPath = row['路径']
    if (!componentPath || componentPath === '路径') continue
    items.set(componentPath, {
      name: row['组件'] || path.basename(componentPath, '.vue'),
      path: componentPath,
      summary: row['用途'] || '',
      refFileCount: Number(row['引用文件数'] || row['引用次数'] || 0),
      templateUseCount: Number(row['模板使用次数'] || 0),
      promote: row['是否建议公共化'] || '',
    })
  }
  return items
}

function hasDesignRecord(content) {
  const marker = '## 设计稿拆组件记录'
  const index = content.indexOf(marker)
  if (index < 0) return false
  const rest = content.slice(index + marker.length)
  return rest
    .split(/\r?\n/)
    .some((line) => line.startsWith('|') && !line.includes('---') && !line.includes('页面/需求'))
}

function printCompareReport() {
  const content = fs.readFileSync(indexFile, 'utf8')
  const existing = parseExistingIndex(content)
  const current = new Map(rows.map((item) => [item.path, {
    name: item.name,
    path: item.path,
    summary: item.summary,
    refFileCount: item.refs.length,
    templateUseCount: item.templateUseCount,
    promote: item.scope === '页面局部组件' ? (item.refs.length >= 2 ? '建议评估' : '否') : '',
  }]))

  const added = [...current.values()].filter((item) => !existing.has(item.path))
  const removed = [...existing.values()].filter((item) => !current.has(item.path))
  const changed = []
  const promoteChanged = []
  const usageChanged = []

  for (const [componentPath, item] of current) {
    const old = existing.get(componentPath)
    if (!old) continue
    const metricChanges = []
    if (old.refFileCount !== item.refFileCount) metricChanges.push(`引用文件数 ${old.refFileCount} → ${item.refFileCount}`)
    if (old.templateUseCount !== item.templateUseCount) metricChanges.push(`模板使用次数 ${old.templateUseCount} → ${item.templateUseCount}`)
    if (metricChanges.length) changed.push(`${item.name}（${item.path}）：${metricChanges.join('，')}`)
    if (old.summary && old.summary !== item.summary) usageChanged.push(`${item.name}（${item.path}）：用途可能变化，请确认是否需由“${old.summary}”更新为“${item.summary}”`)
    if (old.promote && item.promote && old.promote !== item.promote) promoteChanged.push(`${item.name}（${item.path}）：公共化建议 ${old.promote} → ${item.promote}`)
  }

  console.log('组件图谱对比扫描结果：')
  console.log(`- 新增组件：${added.length ? added.map((item) => `${item.name}（${item.path}）`).join('；') : '无'}`)
  console.log(`- 删除组件：${removed.length ? removed.map((item) => `${item.name}（${item.path}）`).join('；') : '无'}`)
  console.log(`- 引用指标变化：${changed.length ? changed.join('；') : '无'}`)
  console.log(`- 用途变化候选：${usageChanged.length ? usageChanged.join('；') : '无'}`)
  console.log(`- 新增公共组件候选/建议变化：${promoteChanged.length ? promoteChanged.join('；') : '无'}`)
  console.log(`- 新增/复用/改造记录是否已写入：${hasDesignRecord(content) ? '已存在记录，请结合本次需求确认是否补充最新记录' : '未发现有效记录，若本次涉及 UI/组件开发必须补充'}`)
  console.log('提示：脚本不会自动覆盖已有正式索引；请根据以上差异更新 docs/component-map.md，或在回复中明确未更新原因。')
}

fs.mkdirSync(path.dirname(indexFile), { recursive: true })

if (fs.existsSync(indexFile) && !shouldForce) {
  console.log(`索引已存在，未覆盖：${path.relative(cwd, indexFile)}`)
  printCompareReport()
} else {
  const lines = buildLines()
  fs.writeFileSync(indexFile, lines.join('\n'), 'utf8')
  console.log(`${shouldForce ? '已重新生成' : '已初始化'}组件索引：${path.relative(cwd, indexFile)}`)
}

console.log(`公共组件：${publicFiles.length}，页面局部组件：${viewFiles.length}`)
