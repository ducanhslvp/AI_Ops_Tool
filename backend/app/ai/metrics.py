from prometheus_client import Counter, Histogram

AI_REQUESTS = Counter(
    "ai_provider_requests_total", "AI provider requests", ("provider", "result")
)
AI_RETRIES = Counter("ai_provider_retries_total", "AI provider retries", ("provider",))
AI_TOKENS = Counter("ai_provider_tokens_total", "AI provider token usage", ("provider", "kind"))
AI_LATENCY = Histogram(
    "ai_provider_request_duration_seconds", "AI provider request duration", ("provider",)
)
AI_STREAMS = Counter("ai_provider_streams_total", "AI provider streams", ("provider", "result"))
