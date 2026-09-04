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

test('extractor_v2 does not treat arbitrary descendant prose as a control identity', () => {
  const source = fs.readFileSync(path.join(root, 'src/content/extractor_v2.ts'), 'utf8')
  assert.match(source, /Descendant prose is not automatically an interactive identity/)
  assert.match(source, /if \(nameFromContent\.has\(tag\) \|\| nameFromContent\.has\(role\)\)/)
  assert.match(source, /return ''/)
})

test('extractor_v2 records generic ARIA and native disabled state', () => {
  const source = fs.readFileSync(path.join(root, 'src/content/extractor_v2.ts'), 'utf8')
  assert.match(source, /aria-disabled[^\n]+state\['aria_disabled'\] = true/)
  assert.match(source, /state\['disabled'\] = true/)
})
