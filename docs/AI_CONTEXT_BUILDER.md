# AI Context Builder

## Selection Order

Before every provider call, `WorkspaceContextBuilder` synchronizes the selected System and selects:

1. `system_prompt.md`.
2. Relevant Runbooks, then Knowledge and Skills using deterministic query token matching.
3. Architecture, Inventory, server metadata, Policy, Tool contract, dependencies, and services.
4. Recent active Memory summaries.
5. Current conversation summaries.
6. Recent reports.

Archive Memory is excluded unless a future explicit archive-retrieval workflow selects it. The total
character budget is `WORKSPACE_CONTEXT_MAX_CHARS`; recent Memory count is controlled by
`WORKSPACE_RECENT_MEMORY_FILES`. The selected filenames and size are written to
`context/latest.json` and persisted on the AI Session for status reporting.

There are no embeddings, vector search, or provider-driven database reads. Selection is reproducible,
bounded, and adapter-neutral. If a provider session cannot resume, the same builder restores the
essential System context before a new provider thread starts.
