const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const root = path.resolve(__dirname, '..')

for (const relativePath of [
  'src/content/extractor.ts',
  'src/content/extractor_v2.ts',
]) {
  test(`${relativePath} excludes hidden headings before applying its heading limit`, () => {
    const source = fs.readFileSync(path.join(root, relativePath), 'utf8')
    const headingPipeline = source.match(
      /const headings = Array\.from\(document\.querySelectorAll\('h1, h2, h3'\)\)([\s\S]*?)\.map\(\(h\)/,
    )
    assert.ok(headingPipeline, 'heading extraction pipeline must remain present')
    const pipeline = headingPipeline[1]
    const visibilityIndex = pipeline.indexOf('.filter((heading) => isVisible(heading))')
    const sliceIndex = pipeline.indexOf('.slice(')
    assert.notEqual(visibilityIndex, -1, 'hidden headings must be excluded')
    assert.ok(sliceIndex > visibilityIndex, 'visibility filtering must happen before the heading limit')
  })
}
