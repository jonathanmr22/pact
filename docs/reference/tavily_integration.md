# Tavily Integration — PACT Web Research

Tavily provides web search, extraction, and research capabilities for PACT worker models. When combined with `pact-delegate --web-search`, it gives Trinity and other workers web-informed research at 98% less cost than Claude subagents with native WebSearch.

## Setup

1. Sign up at [tavily.com](https://www.tavily.com) (free tier, no credit card)
2. Get your API key from the dashboard (starts with `tvly-`)
3. Set environment variable: `TAVILY_API_KEY=tvly-your-key`

Free tier: 1,000 searches/month. Paid: starts at $50/month for 10K searches.

## API Endpoints

All endpoints use `POST` with `Authorization: Bearer tvly-YOUR_API_KEY`.

### Search — `POST https://api.tavily.com/search`

```json
{
  "query": "best kayaking YouTube channel",
  "search_depth": "basic",
  "max_results": 5,
  "include_answer": true
}
```

Returns search results with titles, URLs, content snippets, and an AI-generated answer summary. 1 credit per call.

### Extract — `POST https://api.tavily.com/extract`

```json
{
  "urls": ["https://example.com/page"],
  "query": "focus on pricing info",
  "chunks_per_source": 3,
  "extract_depth": "basic",
  "include_images": false,
  "include_favicon": true,
  "format": "markdown"
}
```

Converts web pages into clean markdown. Handles JavaScript-rendered content. Supports query-focused extraction that returns only relevant chunks. 1 credit for basic, 2 for advanced.

### Research — `POST https://api.tavily.com/research`

AI-powered deep research that gathers sources, analyzes them, and produces a cited report. Given a query, it performs multiple iterative searches, reasons over the data, and returns a comprehensive report.

Costs 10-50 credits depending on depth. Best for complex questions that need multi-source synthesis.

### Map — `POST https://api.tavily.com/map`

Discovers all URLs on a website without extracting content. Useful for identifying the right page before extraction.

### Crawl — `POST https://api.tavily.com/crawl`

Crawls websites and extracts content from multiple pages with semantic filtering.

## Integration with pact-delegate

```bash
# Auto-search from prompt
pact-delegate research "What changed in Drift 2.30?" --web-search

# Explicit search queries (more targeted)
pact-delegate research "Find the best kayaking YouTube channel" \
  --search "best kayaking YouTube channel 2026"

# Multiple searches for comprehensive research
pact-delegate research "Compare React vs Vue in 2026" \
  --search "React vs Vue 2026 comparison" \
  --search "React 19 new features" \
  --search "Vue 4 release notes"
```

## Cost Comparison

| Approach | Cost per research task | Web access |
|---|---|---|
| Claude subagent + WebSearch | ~$0.05-0.15 | Native |
| Trinity + Tavily search | ~$0.001 | Via pact-delegate |
| Trinity + Tavily research | ~$0.01 | Deep multi-source |

## When to Use Each Tavily Skill

| Skill | Use When | Credits |
|---|---|---|
| **Search** | Finding specific sources, quick facts, URL discovery | 1 |
| **Extract** | Reading a specific page's content (API docs, changelogs) | 1-2 |
| **Research** | Complex questions needing multi-source synthesis | 10-50 |
| **Map** | Discovering site structure before extracting | 1 |
| **Crawl** | Bulk content extraction from a site | varies |
