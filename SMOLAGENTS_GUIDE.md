# SmolAgents Implementation Guide

## Overview

The Research Dashboard uses **SmolAgents** with **ToolCallingAgent** to autonomously discover and synthesize research across domains. This document explains the implementation details and best practices.

## Architecture

### Agent Types

We use `ToolCallingAgent` from SmolAgents, which leverages Claude's native tool calling capabilities:

```python
from smolagents import ToolCallingAgent
from smolagents.models import AnthropicModel

# Discovery agent with tools
discovery_agent = ToolCallingAgent(
    tools=[WebSearchTool(), FetchURLTool()],
    model=AnthropicModel(model_id="claude-3-haiku-20240307"),
    max_steps=15,  # Allow multiple tool invocations
)

# Synthesis agent (no tools needed)
synthesis_agent = ToolCallingAgent(
    tools=[],
    model=AnthropicModel(model_id="claude-3-5-sonnet-20241022"),
    max_steps=3,
)
```

### Why ToolCallingAgent vs CodeAgent?

- **ToolCallingAgent**: Uses Claude's native function calling. More reliable, easier to debug.
- **CodeAgent**: Writes Python code to use tools. More flexible but can be brittle.

For research discovery, we need reliability over flexibility, so ToolCallingAgent is the right choice.

## Tools

### Discovery Tools

1. **WebSearchTool** - Brave Search API integration
   - Searches web for recent developments
   - Returns formatted results with titles, URLs, snippets

2. **FetchURLTool** - Content extraction
   - Fetches full content from URLs
   - Cleans HTML, extracts text
   - Truncates to 10K characters

### How Agents Use Tools

The agent autonomously:
1. Calls `web_search` for each configured query
2. Analyzes results
3. Calls `fetch_url` on promising findings
4. Scores significance based on domain filter prompts
5. Returns structured data via `final_answer`

## Final Answer Pattern

**Critical**: Agents MUST use `final_answer` to return structured outputs.

### Best Practices

✅ **DO**: Use placeholder descriptions in schemas
```python
{{
  "title": "[descriptive title of the finding]",
  "source": "[source name like Nature or arXiv]",
  "significance_score": "[number between 0.0 and 1.0]"
}}
```

❌ **DON'T**: Use concrete examples (causes overfitting)
```python
{{
  "title": "Quantum computing breakthrough at IBM",  # Too specific!
  "source": "Nature",  # Agent might bias toward Nature
  "significance_score": "0.8"  # Agent might anchor to 0.8
}}
```

### Why This Matters

Concrete examples in schemas can cause the agent to:
- Overfit to example formats
- Bias toward example sources (e.g., always returning "Nature")
- Anchor to example numbers (e.g., scores clustering around 0.8)

## Discovery Prompt Structure

```python
discover_prompt = f"""You are researching recent developments in {domain_name}.

Domain description: {description}

Your task:
1. Use web_search tool to find recent news, papers, and developments
2. For promising results, use fetch_url tool to get full content
3. Analyze each finding and score its significance

{filter_prompt}  # Domain-specific filtering criteria

Search queries to execute:
- {query_1}
- {query_2}
...

IMPORTANT: After gathering information, you MUST call final_answer with this JSON structure:
{{
  "findings": [
    {{
      "title": "[descriptive title]",
      "source": "[source name]",
      "source_url": "[full URL]",
      "summary": "[2-3 sentence summary]",
      "significance": "[why this matters]",
      "significance_score": "[0.0 to 1.0]",
      "raw_content": "[relevant excerpt]"
    }}
  ]
}}

Significance scoring guide:
- 0.0-0.3: Minor update, incremental progress
- 0.4-0.6: Notable development, worth tracking
- 0.7-0.9: Significant breakthrough
- 1.0: Field-defining, paradigm-shifting

Only include items with significance_score >= 0.4.
"""
```

## Synthesis Prompt Structure

```python
synthesis_prompt = f"""Synthesize a domain update for {domain_name}.

{synthesis_prompt_guidelines}

Significant items discovered:
{formatted_items}

IMPORTANT: Use final_answer tool with this JSON structure:
{{
  "summary": "[2-3 paragraph analysis referencing items by number]",
  "open_questions": [
    "[first specific question the field is investigating]",
    "[second question]",
    "[third question]"
  ]
}}

Guidelines:
1. Analyze current frontier and active investigations
2. Highlight surprising or unexpected results
3. Note blocked or slow progress areas
4. Reference items by number (e.g., "Item 1 demonstrates...")
5. Be analytical, flag uncertainties
6. Make questions specific to recent developments
"""
```

## Handling Agent Outputs

SmolAgents agents return their `final_answer` result directly:

```python
result = agent.run(prompt)

# Result can be dict, list, or string depending on how agent called final_answer
if isinstance(result, dict):
    items = result.get("findings", [])
elif isinstance(result, str):
    # Try parsing as JSON
    parsed = json.loads(result)
    items = parsed.get("findings", [])
```

## Error Handling

```python
try:
    result = discovery_agent.run(discover_prompt)
    items_data = self._parse_result(result)

    self.event_log.append(
        "items_discovered",
        domain_id=self.config.id,
        payload={"count": len(items_data)},
    )

except Exception as e:
    logger.error(f"Discovery failed: {e}", exc_info=True)
    self.event_log.append(
        "discovery_failed",
        domain_id=self.config.id,
        payload={"error": str(e)},
    )
    return []
```

## Model Selection

- **Discovery**: `claude-3-haiku-20240307` (fast, cheap, good for tool use)
- **Synthesis**: `claude-3-5-sonnet-20241022` (better quality for analysis)

Configure in `backend/config.py`:
```python
default_filter_model: str = "claude-3-haiku-20240307"
default_synthesis_model: str = "claude-3-5-sonnet-20241022"
```

## Async Considerations

SmolAgents tools are synchronous, but our repository is async. We handle this by:

1. Running agent synchronously (it's fast with Haiku)
2. Storing results asynchronously in the orchestrator
3. Using asyncio event loop for scheduling

```python
async def _run_domain_update(self, domain_id: str):
    # Discovery runs synchronously but returns quickly
    raw_items = await agent.discover()

    # Storage is async
    for item in items:
        await self.item_repo.create(item)
        await self.embeddings.add_item(item)
```

## Debugging Tips

1. **Set verbosity_level=1** to see tool calls:
   ```python
   agent = ToolCallingAgent(tools=tools, model=model, verbosity_level=1)
   ```

2. **Check event log** for agent outputs:
   ```bash
   tail -f data/events.jsonl
   ```

3. **Test individual tools**:
   ```python
   tool = WebSearchTool(api_key=api_key)
   result = tool.forward("quantum computing breakthrough")
   print(result)
   ```

4. **Validate agent outputs** match expected schema before storing

## Performance Optimization

- **Limit max_steps**: Discovery uses 15 max, synthesis uses 3
- **Truncate content**: FetchURLTool limits to 10K characters
- **Parallel execution**: Orchestrator can run multiple domains concurrently
- **Caching**: Consider caching search results for duplicate queries

## Future Enhancements

- [ ] Add ArXivTool for academic papers
- [ ] Implement RSSFeedTool for blog monitoring
- [ ] Add CitationExtractorTool for reference chains
- [ ] Support for multi-modal content (PDFs, images)
- [ ] Agent memory for cross-domain connections
