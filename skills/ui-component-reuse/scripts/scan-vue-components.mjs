#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'

const args = process.argv.slice(2)
const shouldForce = args.includes('--force')
const checkOnly = args.includes('--check')
const projectArg = args.find((arg) => !arg.startsWith('--'))
const cwd = projectArg ? path.resolve(projectArg) : process.cwd()
const indexFile = path.resolve(cwd, 'docs/component-map.md')

if (!fs.existsSync(path.join(cwd, 'src')) || !fs.statSync(path.join(cwd, 'src')).isDirectory()) {
  throw new Error(`项目缺少 src/ 目录，请确认项目根目录：${cwd}；未写入索引。`)
}

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

const tableHeaders = {
  公共组件: ['组件', '路径', '用途', 'Props', 'Emits', '引用文件数', '模板使用次数', '引用位置'],
  页面局部组件: ['组件', '路径', '所属页面', '用途', 'Props', 'Emits', '引用文件数', '模板使用次数', '引用位置', '是否建议公共化'],
}

// 保留原始 Markdown 单元格，避免反引号、强调和转义竖线在合并时丢失。
function splitCells(line) {
  return line.trim().split(/(?<!\\)\|/).slice(1, -1).map(cell => cell.trim())
}

function readTables(content) {
  const lines = content.split(/\r?\n/)
  const tables = new Map()
  let section = ''
  let fence = null
  for (let i = 0; i < lines.length; i++) {
    const marker = lines[i].match(/^\s*(`{3,}|~{3,})/)
    if (marker) {
      if (!fence) fence = marker[1]
      else if (marker[1][0] === fence[0] && marker[1].length >= fence.length) fence = null
      continue
    }
    if (fence) continue
    const heading = lines[i].match(/^##\s+(.+?)\s*$/)
    if (heading) section = heading[1]
    if (!Object.hasOwn(tableHeaders, section) || !lines[i].trim().startsWith('|')) continue
    const header = splitCells(lines[i]).map(stripMarkdown)
    if (!header.includes('组件') || !header.includes('路径')) continue
    const separator = splitCells(lines[i + 1] || '')
    if (separator.length !== header.length || !separator.every(cell => /^:?-+:?$/.test(cell))) {
      throw new Error(`${section}表头分隔行无法识别，请先修复表格格式；未写入索引。`)
    }
    if (tables.has(section)) throw new Error(`${section}存在多个组件表格，请先合并；未写入索引。`)
    const items = new Map()
    let end = i + 2
    while (end < lines.length && lines[end].trim().startsWith('|')) {
      const cells = splitCells(lines[end])
      if (cells.length !== header.length) throw new Error(`第 ${end + 1} 行列数不匹配；未写入索引。`)
      const row = Object.fromEntries(header.map((name, index) => [name, cells[index]]))
      const componentPath = stripMarkdown(row['路径'])
      if (!componentPath.endsWith('.vue') || items.has(componentPath)) {
        throw new Error(`第 ${end + 1} 行组件路径无效或重复；未写入索引。`)
      }
      items.set(componentPath, row)
      end++
    }
    tables.set(section, { header, items, start: i, end })
    i = end - 1
  }
  return { lines, tables }
}

function promotion(item) {
  return item.refs.length >= 2 ? '建议评估' : '否'
}

function buildTable(scope, previous) {
  const automatic = tableHeaders[scope]
  const aliases = new Set(['引用次数', '所属 view'])
  const extra = (previous?.header || []).filter(name => !automatic.includes(name) && !aliases.has(name))
  const header = [...automatic, ...extra]
  const lines = [`| ${header.join(' | ')} |`, `| ${header.map(() => '---').join(' | ')} |`]
  for (const item of rows.filter(row => row.scope === scope)) {
    const old = previous?.items.get(item.path) || {}
    const oldSummary = old['用途']
    const keepSummary = oldSummary && !['-', '待补充'].includes(oldSummary) && !oldSummary.includes('用途需结合源码确认')
    const oldPromotion = old['是否建议公共化']
    const keepPromotion = oldPromotion && !['-', '否', '建议评估'].includes(oldPromotion)
    const cells = {
      ...old,
      组件: escapeCell(item.name),
      路径: `\`${escapeCell(item.path)}\``,
      所属页面: escapeCell(item.view),
      用途: keepSummary ? oldSummary : escapeCell(item.summary),
      Props: escapeCell(item.props),
      Emits: escapeCell(item.emits),
      引用文件数: String(item.refs.length),
      模板使用次数: String(item.templateUseCount),
      引用位置: item.refs.join('<br>') || '-',
      是否建议公共化: keepPromotion ? oldPromotion : promotion(item),
    }
    lines.push(`| ${header.map(name => cells[name] || '-').join(' | ')} |`)
  }
  return lines
}

function buildIndex(content) {
  if (!content) {
    const now = new Date().toISOString().slice(0, 10)
    return [
      '# 组件图谱索引', '', `> 生成日期：${now}`,
      '> 扫描范围：`src/components/**/*.vue`、`src/views/**/components/**/*.vue`。',
      '> 本文件是项目正式组件索引；后续 UI / 组件开发前先扫描同步，开发后再次同步。', '',
      ...Object.keys(tableHeaders).flatMap(scope => [`## ${scope}`, '', ...buildTable(scope), '']),
      '## 设计稿拆组件记录', '',
      '| 页面/需求 | 拆分结果 | 复用组件 | 新增组件 | 决策说明 |',
      '| --- | --- | --- | --- | --- |', '',
    ].join('\n')
  }
  const { lines, tables } = readTables(content)
  // 只替换组件表格范围，章节说明和设计记录原样保留。
  const edits = [...tables].map(([scope, previous]) => ({
    start: previous.start, end: previous.end, lines: buildTable(scope, previous),
  }))
  for (const scope of Object.keys(tableHeaders)) {
    if (tables.has(scope)) continue
    const heading = lines.findIndex(line => line.trim() === `## ${scope}`)
    if (heading >= 0) edits.push({ start: heading + 1, end: heading + 1, lines: ['', ...buildTable(scope), ''] })
    else edits.push({ start: lines.length, end: lines.length, lines: ['', `## ${scope}`, '', ...buildTable(scope), ''] })
  }
  for (const edit of edits.sort((a, b) => b.start - a.start)) {
    lines.splice(edit.start, edit.end - edit.start, ...edit.lines)
  }
  return lines.join(content.includes('\r\n') ? '\r\n' : '\n')
}

function parseExistingIndex(content) {
  const items = new Map()
  for (const table of readTables(content).tables.values()) {
    for (const [componentPath, row] of table.items) {
      items.set(componentPath, {
        name: stripMarkdown(row['组件']), path: componentPath,
        summary: stripMarkdown(row['用途']),
        refFileCount: Number(row['引用文件数'] || row['引用次数'] || 0),
        templateUseCount: Number(row['模板使用次数'] || 0),
        promote: stripMarkdown(row['是否建议公共化']),
      })
    }
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
  console.log('提示：用途和已说明原因的公共化判断会保留；请结合源码确认变化候选并更新结论。')
}

const exists = fs.existsSync(indexFile)
const before = exists ? fs.readFileSync(indexFile, 'utf8') : ''
const after = buildIndex(shouldForce ? '' : before)
if (exists && !shouldForce) printCompareReport()
const candidates = rows.filter(item => item.scope === '页面局部组件' && item.refs.length >= 2)
console.log(`- 待核查公共化候选：${candidates.length ? candidates.map(item => `${item.name}（${item.path}，引用文件数 ${item.refs.length}）`).join('；') : '无'}`)
if (checkOnly) {
  console.log(`仅检查，未写入：${before === after ? '索引与扫描结果一致' : '索引需要同步（含表格排序/字段变化）'}`)
} else if (before !== after) {
  fs.mkdirSync(path.dirname(indexFile), { recursive: true })
  fs.writeFileSync(indexFile, after, 'utf8')
  console.log(`${!exists ? '已初始化' : shouldForce ? '已重新生成' : '已同步更新并排序'}组件索引：${path.relative(cwd, indexFile)}`)
} else {
  console.log(`索引已是最新，未重复写入：${path.relative(cwd, indexFile)}`)
}
console.log(`公共组件：${publicFiles.length}，页面局部组件：${viewFiles.length}`)
