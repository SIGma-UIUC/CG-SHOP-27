const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');

// Execute the actual privileged preparation script without network or writes.
const workflow = fs.readFileSync(path.join(__dirname, '../workflows/solver-benchmark-comment.yml'), 'utf8');
const lines = workflow.split('\n');
const start = lines.findIndex(line => line === '          script: |') + 1;
const body = [];
for (const line of lines.slice(start)) {
  if (line.trim() && !line.startsWith('            ')) break;
  body.push(line.slice(12));
}
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const prepare = new AsyncFunction('require', 'context', 'github', 'core', body.join('\n'));

for (const rows of [[], [{solver: 'candidate/example', instance: 'tiny', status: 'timeout'}]]) {
  for (const existingBranch of [false, true]) {
    test(`prepares ${rows.length} rows without GIFs, existing branch: ${existingBranch}`, async () => {
      let comment, ready, published = false;
      const sha = 'candidate-sha';
      const context = {
        repo: {owner: 'team', repo: 'solvers'},
        payload: {repository: {id: 1}, workflow_run: {
          id: 42, head_sha: sha, conclusion: 'success',
          pull_requests: [{number: 7, base: {repo: {id: 1}}}],
        }},
      };
      const fakeFs = {
        existsSync: file => file === 'report-data/results.json',
        statSync: () => ({size: 100}),
        readFileSync: () => JSON.stringify(rows),
        writeFileSync: (file, contents) => {
          assert.equal(file, 'comment.json');
          comment = JSON.parse(contents);
        },
      };
      const git = {
        getRef: async () => {
          if (!existingBranch) throw Object.assign(new Error('Not found'), {status: 404});
          return {data: {object: {sha: 'previous'}}};
        },
        getCommit: async () => ({data: {tree: {sha: 'previous-tree'}}}),
        getTree: async () => ({data: {tree: []}}),
        createTree: async ({tree}) => {
          assert.ok(tree.length > 0, 'GitHub rejects tree: []');
          assert.ok(tree.some(entry => entry.path === 'README.md' && entry.content));
          return {data: {sha: 'new-tree'}};
        },
        createCommit: async ({tree, parents}) => {
          assert.equal(tree, 'new-tree');
          assert.deepEqual(parents, existingBranch ? ['previous'] : []);
          return {data: {sha: 'new-commit'}};
        },
      };
      git[existingBranch ? 'updateRef' : 'createRef'] = async ({sha}) => {
        assert.equal(sha, 'new-commit');
        published = true;
      };
      await prepare(name => {assert.equal(name, 'fs'); return fakeFs;}, context,
        {rest: {pulls: {get: async () => ({data: {head: {sha}}})}, git}},
        {setOutput: (name, value) => {assert.equal(name, 'ready'); ready = value;}});
      assert.ok(published);
      assert.equal(ready, 'true');
      assert.equal(comment.number, 7);
      assert.equal(comment.sha, sha);
      assert.match(comment.body, rows.length ? /candidate\/example/ : /<!-- solver-benchmark -->/);
    });
  }
}
