#!/usr/bin/env node

const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const scriptPath = path.join(__dirname, 'git-tag-release.cjs');

function main() {
  const tests = [
    ['continues existing dev prefix and rolls over after 100', testExistingDevPrefixRollover],
    ['starts new target prefix from project abbreviation at 0.0.0', testNewTargetPrefixStartsAtZero],
    ['starts new target prefix from repository directory instead of package name', testNewTargetPrefixUsesRepositoryDirectory],
    ['stops when multiple prefixes exist for one target', testMultipleTargetPrefixesStop],
    ['uses package tag abbreviation to choose among multiple target prefixes', testPackageTagAbbreviationSelectsTargetPrefix],
    ['uses package tag abbreviation with requested production target', testPackageTagAbbreviationSwitchesTarget],
    ['uses package tagPrefix abbreviation before repository directory', testPackageTagPrefixAbbreviation],
    ['uses package tagPrefix deployment prefix with requested target', testPackageTagPrefixDeploymentPrefixSwitchesTarget],
  ];

  for (const [name, fn] of tests) {
    fn();
    console.log(`ok - ${name}`);
  }
}

function testExistingDevPrefixRollover() {
  const repo = createRepo('cqwx-dual-grid-h5');
  git(repo.cwd, ['tag', 'cq-dev-v0.0.99']);
  git(repo.cwd, ['tag', 'cq-dev-v0.0.100']);
  git(repo.cwd, ['push', 'origin', '--tags']);

  const result = preview(repo.cwd, ['--target', 'dev']);

  assert.strictEqual(result.prefix, 'cq-dev-v');
  assert.strictEqual(result.finalTag, 'cq-dev-v0.1.0');
  assert.strictEqual(result.ready, true);
}

function testNewTargetPrefixStartsAtZero() {
  const repo = createRepo('ga-portal', 'ga-portal');

  const result = preview(repo.cwd, ['--target', 'prod']);

  assert.strictEqual(result.prefix, 'gp-prod-v');
  assert.strictEqual(result.finalTag, 'gp-prod-v0.0.0');
  assert.strictEqual(result.ready, true);
}

function testNewTargetPrefixUsesRepositoryDirectory() {
  const repo = createRepo('vite-tpl', 'wdbigscreen');

  const result = preview(repo.cwd, ['--target', 'prod']);

  assert.strictEqual(result.prefix, 'wd-prod-v');
  assert.strictEqual(result.prefixSource, 'repository-directory');
  assert.strictEqual(result.finalTag, 'wd-prod-v0.0.0');
  assert.strictEqual(result.ready, true);
}

function testMultipleTargetPrefixesStop() {
  const repo = createRepo('cqwx-dual-grid-h5');
  git(repo.cwd, ['tag', 'cq-dev-v0.0.1']);
  git(repo.cwd, ['tag', 'dg-dev-v0.0.2']);
  git(repo.cwd, ['push', 'origin', '--tags']);

  const result = preview(repo.cwd, ['--target', 'dev']);

  assert.strictEqual(result.ready, false);
  assert(result.problems.some((item) => item.includes('Multiple tag prefixes')));
}

function testPackageTagAbbreviationSelectsTargetPrefix() {
  const repo = createRepo('cqwx-dual-grid-h5', 'cqwx-dual-grid-h5', {
    tag: 'cq-dev-v0.1.8',
  });
  git(repo.cwd, ['tag', 'cq-dev-v0.1.8']);
  git(repo.cwd, ['tag', 'wx-dev-v0.1.9']);
  git(repo.cwd, ['push', 'origin', '--tags']);

  const result = preview(repo.cwd, ['--target', 'dev']);

  assert.strictEqual(result.ready, true);
  assert.strictEqual(result.prefix, 'cq-dev-v');
  assert.strictEqual(result.prefixSource, 'package.json#tag');
  assert.strictEqual(result.finalTag, 'cq-dev-v0.1.9');
}

function testPackageTagAbbreviationSwitchesTarget() {
  const repo = createRepo('cqwx-dual-grid-h5', 'cqwx-dual-grid-h5', {
    tag: 'cq-dev-v0.1.8',
  });
  git(repo.cwd, ['tag', 'cq-prod-v0.0.3']);
  git(repo.cwd, ['tag', 'wx-prod-v0.0.4']);
  git(repo.cwd, ['push', 'origin', '--tags']);

  const result = preview(repo.cwd, ['--target', 'prod']);

  assert.strictEqual(result.ready, true);
  assert.strictEqual(result.prefix, 'cq-prod-v');
  assert.strictEqual(result.prefixSource, 'package.json#tag');
  assert.strictEqual(result.finalTag, 'cq-prod-v0.0.4');
}

function testPackageTagPrefixAbbreviation() {
  const repo = createRepo('vite-tpl', 'wdbigscreen', {
    tagPrefix: ['cq'],
  });

  const result = preview(repo.cwd, ['--target', 'dev']);

  assert.strictEqual(result.ready, true);
  assert.strictEqual(result.prefix, 'cq-dev-v');
  assert.strictEqual(result.prefixSource, 'package.json#tagPrefix');
  assert.strictEqual(result.finalTag, 'cq-dev-v0.0.0');
}

function testPackageTagPrefixDeploymentPrefixSwitchesTarget() {
  const repo = createRepo('vite-tpl', 'wdbigscreen', {
    tagPrefix: ['cq-dev-v'],
  });

  const result = preview(repo.cwd, ['--target', 'prod']);

  assert.strictEqual(result.ready, true);
  assert.strictEqual(result.prefix, 'cq-prod-v');
  assert.strictEqual(result.prefixSource, 'package.json#tagPrefix');
  assert.strictEqual(result.finalTag, 'cq-prod-v0.0.0');
}

function createRepo(packageName, repoName = 'repo', packageOverrides = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'git-tag-release-test-'));
  const remote = path.join(root, 'remote.git');
  const cwd = path.join(root, repoName);

  execFileSync('git', ['init', '--bare', remote], { stdio: 'ignore' });
  execFileSync('git', ['init', cwd], { stdio: 'ignore' });
  git(cwd, ['config', 'user.name', 'Test User']);
  git(cwd, ['config', 'user.email', 'test@example.com']);
  git(cwd, ['remote', 'add', 'origin', remote]);

  fs.writeFileSync(
    path.join(cwd, 'package.json'),
    `${JSON.stringify({ name: packageName, ...packageOverrides }, null, 2)}\n`,
    'utf8'
  );
  git(cwd, ['add', 'package.json']);
  git(cwd, ['commit', '-m', 'init']);
  git(cwd, ['push', '-u', 'origin', 'HEAD']);

  return { cwd, remote };
}

function preview(cwd, extraArgs) {
  const output = execFileSync(
    process.execPath,
    [scriptPath, 'preview', '--cwd', cwd, ...extraArgs, '--json'],
    { encoding: 'utf8' }
  );
  return JSON.parse(output);
}

function git(cwd, args) {
  return execFileSync('git', args, {
    cwd,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

main();
