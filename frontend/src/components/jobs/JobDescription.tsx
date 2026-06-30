'use client'

import { useState } from 'react'

interface JobDescriptionProps {
  content: string
}

const COLLAPSE_HEIGHT = 480
const HTML_TAG_RE = /<[a-z][\s\S]*?>/i

/** Returns true when the string contains HTML tags (Greenhouse-style). */
function looksLikeHtml(text: string): boolean {
  return HTML_TAG_RE.test(text)
}

/**
 * A minimal style block injected into the sandboxed iframe so the scraped
 * HTML inherits the app's font stack and sensible typography without any
 * JS execution risk (sandbox has no allow-scripts).
 */
const IFRAME_STYLES = `
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    html { font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; line-height: 1.6; color: #1a1a1a; background: transparent; margin: 0; padding: 0; }
    body { margin: 0; padding: 12px 16px; }
    h1, h2, h3, h4 { margin: 1em 0 0.4em; font-weight: 600; }
    h1 { font-size: 1.25rem; } h2 { font-size: 1.1rem; } h3 { font-size: 1rem; }
    p { margin: 0.5em 0; }
    ul, ol { padding-left: 1.4em; margin: 0.5em 0; }
    li { margin-bottom: 0.2em; }
    a { color: #4f46e5; }
    strong, b { font-weight: 600; }
    @media (prefers-color-scheme: dark) {
      html { color: #e5e5e5; }
      a { color: #818cf8; }
    }
  </style>
`

function HtmlDescription({ content }: { content: string }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const srcDoc = `<!doctype html><html><head><meta charset="utf-8">${IFRAME_STYLES}</head><body>${content}</body></html>`

  return (
    <div className="relative">
      <div
        className="overflow-hidden transition-all duration-300"
        style={{ maxHeight: isExpanded ? 'none' : `${COLLAPSE_HEIGHT}px` }}
      >
        <iframe
          srcDoc={srcDoc}
          title="Job description"
          sandbox="allow-same-origin"
          className="w-full border-0"
          style={{ minHeight: `${COLLAPSE_HEIGHT}px`, display: 'block' }}
          onLoad={(e) => {
            const iframe = e.currentTarget
            const doc = iframe.contentDocument
            if (doc?.body) {
              const h = doc.body.scrollHeight
              iframe.style.height = `${h}px`
            }
          }}
        />
      </div>
      {!isExpanded && (
        <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-card to-transparent pointer-events-none" />
      )}
      <button
        type="button"
        onClick={() => setIsExpanded(prev => !prev)}
        className="mt-2 text-xs text-muted-foreground hover:text-foreground underline underline-offset-2 transition-colors"
      >
        {isExpanded ? 'Show less' : 'Show full description'}
      </button>
    </div>
  )
}

function PlainDescription({ content }: { content: string }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const isLong = content.length > 1200

  return (
    <div className="relative">
      <div
        className="overflow-hidden transition-all duration-300"
        style={isLong && !isExpanded ? { maxHeight: `${COLLAPSE_HEIGHT}px` } : undefined}
      >
        <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap prose prose-sm max-w-none">
          {content}
        </p>
      </div>
      {isLong && !isExpanded && (
        <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-card to-transparent pointer-events-none" />
      )}
      {isLong && (
        <button
          type="button"
          onClick={() => setIsExpanded(prev => !prev)}
          className="mt-2 text-xs text-muted-foreground hover:text-foreground underline underline-offset-2 transition-colors"
        >
          {isExpanded ? 'Show less' : 'Show full description'}
        </button>
      )}
    </div>
  )
}

export function JobDescription({ content }: JobDescriptionProps) {
  const isHtml = looksLikeHtml(content)

  return (
    <section className="bg-card border border-border rounded-xl">
      <div className="px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold">Job description</h2>
      </div>
      <div className="p-4">
        {isHtml ? (
          <HtmlDescription content={content} />
        ) : (
          <PlainDescription content={content} />
        )}
      </div>
    </section>
  )
}
