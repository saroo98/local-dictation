import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const projectRoot = path.resolve(__dirname, '..', '..')

describe('offline policy', () => {
  it('does not include remote scripts, styles, fonts, icons, or telemetry packages', () => {
    const index = fs.readFileSync(path.join(projectRoot, 'index.html'), 'utf8')
    const pkg = fs.readFileSync(path.join(projectRoot, 'package.json'), 'utf8')
    const sourceFiles = fs
      .readdirSync(path.join(projectRoot, 'src'), { recursive: true, withFileTypes: true })
      .filter((entry) => entry.isFile() && /\.(ts|tsx|css)$/.test(entry.name))
      .map((entry) => fs.readFileSync(path.join(entry.parentPath, entry.name), 'utf8'))
      .join('\n')

    expect(index).not.toMatch(/https?:\/\//)
    expect(sourceFiles).not.toMatch(/https?:\/\/.*(font|icon|cdn)/i)
    expect(pkg).not.toMatch(/posthog|segment|amplitude|mixpanel|telemetry/i)
  })
})
