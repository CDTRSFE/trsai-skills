#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

function main() {
  try {
    const { command, options } = parseArgs(process.argv.slice(2));

    if (!command || options.help) {
      printHelp();
      process.exit(options.help ? 0 : 1);
    }

    if (!['preview', 'execute'].includes(command)) {
      throw new Error(`Unsupported command: ${command}`);
    }

    const result = command === 'preview' ? preview(options) : execute(options);
    printResult(result, options.json);
  } catch (error) {
    printError(error);
    process.exit(1);
  }
}

function parseArgs(argv) {
  const positional = [];
  const options = {};

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];

    if (!token.startsWith('--')) {
      positional.push(token);
      continue;
    }

    const body = token.slice(2);
    const eqIndex = body.indexOf('=');
    if (eqIndex >= 0) {
      options[body.slice(0, eqIndex)] = body.slice(eqIndex + 1);
      continue;
    }

    const next = argv[i + 1];
    if (next && !next.startsWith('--')) {
      options[body] = next;
      i += 1;
      continue;
    }

    options[body] = true;
  }

  return {
    command: positional[0],
    options,
  };
}

function printHelp() {
  const text = `
git-tag-release

Usage:
  node scripts/git-tag-release.js preview --cwd /repo [options]
  node scripts/git-tag-release.js execute --cwd /repo [options]

Options:
  --cwd <path>            Target repository path. Defaults to current directory.
  --remote <name>         Remote to fetch/push. Defaults to the first git remote.
  --prefix <value>        Tag prefix. Defaults to package.json#tagPrefix[0].
  --version-type <type>   major | minor | patch | RC. Defaults to patch.
  --suffix <value>        Optional suffix appended to the final tag.
  --edit-pkg <bool>       true | false. Defaults to true.
  --tag <value>           Explicit final tag. Useful after preview confirmation.
  --json                  Print machine-readable JSON output.
  --help                  Show this help message.
`.trim();

  console.log(text);
}

function preview(options) {
  const context = inspectRepository(options);
  const problems = [];

  if (context.finalTagExists) {
    problems.push(`Tag already exists: ${context.finalTag}`);
  }

  return {
    mode: 'preview',
    cwd: context.cwd,
    remote: context.remote,
    prefix: context.prefix,
    versionType: context.versionType,
    suffix: context.suffix,
    editPkg: context.editPkg,
    finalTag: context.finalTag,
    manualTagUsed: context.manualTagUsed,
    tagPrefixes: context.tagPrefixes,
    warnings: context.warnings,
    problems,
    ready: problems.length === 0,
    actions: buildActions(context),
  };
}

function execute(options) {
  const context = inspectRepository(options);

  if (context.finalTagExists) {
    throw new Error(`Tag already exists: ${context.finalTag}`);
  }

  const performed = [];

  if (context.editPkg) {
    const nextPkg = {
      ...context.packageJson,
      tag: context.finalTag,
    };
    const nextContent = `${JSON.stringify(nextPkg, null, detectIndent(context.packageJsonRaw))}\n`;

    fs.writeFileSync(context.packageJsonPath, nextContent, 'utf8');
    performed.push(`Updated package.json#tag -> ${context.finalTag}`);

    if (runGit(['status', '--porcelain', '--', 'package.json'], context.cwd).trim()) {
      runGit(['add', 'package.json'], context.cwd);
      performed.push('git add package.json');
      runGit(['commit', '-m', 'chore(release): update package.json#tag', '--no-verify'], context.cwd);
      performed.push("git commit -m 'chore(release): update package.json#tag' --no-verify");
    } else {
      performed.push('Skipped package.json commit because there was no diff');
    }
  }

  runGit(['tag', context.finalTag], context.cwd);
  performed.push(`git tag ${context.finalTag}`);

  runGit(['push', context.remote, context.finalTag], context.cwd);
  performed.push(`git push ${context.remote} ${context.finalTag}`);

  return {
    mode: 'execute',
    cwd: context.cwd,
    remote: context.remote,
    prefix: context.prefix,
    versionType: context.versionType,
    suffix: context.suffix,
    editPkg: context.editPkg,
    finalTag: context.finalTag,
    manualTagUsed: context.manualTagUsed,
    warnings: context.warnings,
    actions: buildActions(context),
    performed,
  };
}

function inspectRepository(options) {
  const cwd = path.resolve(options.cwd || process.cwd());
  ensureGitRepo(cwd);

  const packageJsonPath = path.join(cwd, 'package.json');
  if (!fs.existsSync(packageJsonPath)) {
    throw new Error(`package.json not found: ${packageJsonPath}`);
  }

  const packageJsonRaw = fs.readFileSync(packageJsonPath, 'utf8');
  let packageJson;
  try {
    packageJson = JSON.parse(packageJsonRaw);
  } catch (error) {
    throw new Error(`package.json is not valid JSON: ${error.message}`);
  }

  const tagPrefixes = packageJson.tagPrefix;
  if (!Array.isArray(tagPrefixes) || tagPrefixes.length === 0) {
    throw new Error('package.json#tagPrefix must be a non-empty array');
  }

  const remotes = runGit(['remote'], cwd)
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);

  if (remotes.length === 0) {
    throw new Error('No git remotes found');
  }

  const remote = options.remote || remotes[0];
  if (!remotes.includes(remote)) {
    throw new Error(`Remote not found: ${remote}`);
  }

  runGit(['fetch', remote, '--tags'], cwd);

  const manualTag = typeof options.tag === 'string' ? options.tag : '';
  const prefix = options.prefix || inferPrefix(manualTag, tagPrefixes) || tagPrefixes[0];
  const requestedVersionType = options['version-type'] || 'patch';
  const suffix = typeof options.suffix === 'string' ? options.suffix : '';
  const editPkg = parseBooleanOption(options['edit-pkg'], true);

  if (!manualTag && !prefix) {
    throw new Error('A tag prefix is required when --tag is not provided');
  }

  if (!['major', 'minor', 'patch', 'RC'].includes(requestedVersionType)) {
    throw new Error(`Unsupported version type: ${requestedVersionType}`);
  }

  const tags = runGit(['tag'], cwd)
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);

  const groupedTags = resolveTags(tags);
  const computedTag = manualTag || buildTag({
    prefix,
    versionType: requestedVersionType,
    suffix,
    tags: groupedTags[prefix] || [],
  });

  const versionType = manualTag && !options['version-type'] ? 'manual' : requestedVersionType;

  const finalTagExists = runGit(['tag', '--list', computedTag], cwd)
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
    .includes(computedTag);

  const warnings = [];
  const packageStatus = runGit(['status', '--porcelain', '--', 'package.json'], cwd).trim();
  const worktreeStatus = runGit(['status', '--porcelain'], cwd).trim();

  if (editPkg && packageStatus) {
    warnings.push('package.json has uncommitted changes and will be included when committing package.json');
  }

  if (worktreeStatus) {
    warnings.push('Working tree is dirty; review local changes before publishing a tag');
  }

  return {
    cwd,
    remote,
    remotes,
    prefix,
    suffix,
    versionType,
    editPkg,
    manualTagUsed: Boolean(manualTag),
    finalTag: computedTag,
    finalTagExists,
    tagPrefixes,
    packageJson,
    packageJsonRaw,
    packageJsonPath,
    warnings,
  };
}

function buildActions(context) {
  const actions = [];

  if (context.editPkg) {
    actions.push('Update package.json#tag');
    actions.push('git add package.json');
    actions.push("git commit -m 'chore(release): update package.json#tag' --no-verify");
  }

  actions.push(`git tag ${context.finalTag}`);
  actions.push(`git push ${context.remote} ${context.finalTag}`);

  return actions;
}

function ensureGitRepo(cwd) {
  const result = runGit(['rev-parse', '--is-inside-work-tree'], cwd).trim();
  if (result !== 'true') {
    throw new Error(`Not a git repository: ${cwd}`);
  }
}

function runGit(args, cwd) {
  try {
    return execFileSync('git', args, {
      cwd,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (error) {
    const message = error.stderr ? String(error.stderr).trim() : error.message;
    throw new Error(`git ${args.join(' ')} failed: ${message}`);
  }
}

function resolveTags(tags) {
  const result = {};

  for (const tag of tags) {
    const match = tag.match(/(.*?)(\d+\.\d+\.\d+)/);
    if (!match) {
      continue;
    }

    const [, prefix, versionNumber] = match;
    if (!prefix || !versionNumber) {
      continue;
    }

    if (!result[prefix]) {
      result[prefix] = [];
    }

    result[prefix].push(versionNumber);
  }

  return result;
}

function latestTag(tags) {
  const sorted = [...tags].sort((left, right) => compareSemver(left, right));
  return sorted.pop() || '0.0.0';
}

function compareSemver(left, right) {
  const leftParts = left.split('.').map((item) => Number(item));
  const rightParts = right.split('.').map((item) => Number(item));

  for (let i = 0; i < 3; i += 1) {
    const diff = (leftParts[i] || 0) - (rightParts[i] || 0);
    if (diff !== 0) {
      return diff;
    }
  }

  return 0;
}

function buildTag({ prefix, versionType, suffix, tags }) {
  let version = latestTag(tags);
  const updateIndex = ['major', 'minor', 'patch'].indexOf(versionType);

  if (updateIndex >= 0) {
    const parts = version.split('.');
    parts[updateIndex] = String(Number(parts[updateIndex]) + 1);

    for (let i = updateIndex + 1; i < parts.length; i += 1) {
      parts[i] = '0';
    }

    version = parts.join('.');
  } else {
    version = `${version}-RC-${formatTimestamp(new Date())}`;
  }

  return `${prefix}${version}${suffix}`;
}

function inferPrefix(tag, tagPrefixes) {
  if (!tag) {
    return '';
  }

  return [...tagPrefixes]
    .sort((left, right) => right.length - left.length)
    .find((prefix) => tag.startsWith(prefix)) || '';
}

function formatTimestamp(date) {
  const parts = [
    date.getFullYear(),
    pad2(date.getMonth() + 1),
    pad2(date.getDate()),
    pad2(date.getHours()),
    pad2(date.getMinutes()),
    pad2(date.getSeconds()),
  ];

  return parts.join('');
}

function pad2(value) {
  return String(value).padStart(2, '0');
}

function parseBooleanOption(value, defaultValue) {
  if (value === undefined || value === true) {
    return defaultValue;
  }

  if (typeof value === 'boolean') {
    return value;
  }

  if (typeof value === 'string') {
    if (value === 'true') {
      return true;
    }

    if (value === 'false') {
      return false;
    }
  }

  throw new Error(`Expected boolean value, received: ${value}`);
}

function detectIndent(content) {
  const match = content.match(/^[ \t]+(?="[^"]+":)/m);
  if (!match) {
    return 2;
  }

  return match[0].includes('\t') ? '\t' : match[0].length;
}

function printResult(result, asJson) {
  if (asJson) {
    console.log(JSON.stringify(result, null, 2));
    return;
  }

  console.log(`${result.mode}: ${result.finalTag}`);
  console.log(`remote: ${result.remote}`);
  console.log(`editPkg: ${String(result.editPkg)}`);

  if (result.actions && result.actions.length > 0) {
    console.log('actions:');
    for (const action of result.actions) {
      console.log(`- ${action}`);
    }
  }

  if (result.warnings && result.warnings.length > 0) {
    console.log('warnings:');
    for (const warning of result.warnings) {
      console.log(`- ${warning}`);
    }
  }

  if (result.problems && result.problems.length > 0) {
    console.log('problems:');
    for (const problem of result.problems) {
      console.log(`- ${problem}`);
    }
  }

  if (result.performed && result.performed.length > 0) {
    console.log('performed:');
    for (const item of result.performed) {
      console.log(`- ${item}`);
    }
  }
}

function printError(error) {
  const payload = {
    error: error.message || String(error),
  };
  console.error(JSON.stringify(payload, null, 2));
}

main();
