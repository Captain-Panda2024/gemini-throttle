# gemini-throttle

**Version**: 1.0
**License**: MIT
**Author**: Panda Captain & Reika AI

## Overview

`gemini-throttle` is a lightweight gateway/reverse proxy that sits between your application and the Google Gemini API. It avoids short-term rate limit (429) errors by parking requests and provides intelligent daily quota management to maximize Free Tier usage.

## v1.0 Enhancements

- **Budget Management**: Optimized budget tracking. Only successful generation requests (status 200) count towards the daily limit, excluding health checks and errors.
- **Model-Level Guarding**: Budget limits are enforced per-model, ensuring one model's exhaustion does not block usage of others.
- **Model Name Normalization**: Automatically normalizes model prefixes (`models/`, `google/`, etc.) to prevent double-counting.
- **Health Check Bypass**: Budget guard is scoped to AI generation requests. Health checks (e.g., `/v1/models`, `/props`) pass through unimpeded.
- **Observability**: Added `counted=1|0` flags to logs for precise budget auditing.

## Key Features

- **Daily Budget Guard**: Tracks generation success counts and proactively blocks requests at the proxy level when the daily limit is reached.
- **Park on 429**: Waits for rate limit windows to reset, then retries automatically.
- **TokenBucket pre-throttling**: 10 req/min sliding window to avoid 429 proactively.
- **Path normalization**: Deduplicates `/v1`, `/openai`, `/v1beta` segments.
- **Gemini-scoped**: Does not affect other providers (DeepInfra, OpenRouter, etc.).

## Integration

### custom_providers (recommended)

Add to your `config.yaml`:

```yaml
custom_providers:
  - name: gemini-throttled
    base_url: http://127.0.0.1:8899/v1
    api_key: ${GOOGLE_API_KEY}
    model: gemini-3.1-flash-lite
```

Use `gemini-throttled` explicitly to ensure requests go through the proxy.

### Important: Do NOT use GEMINI_BASE_URL

Setting `GEMINI_BASE_URL` in `.env` overrides **all** providers' base URLs in Hermes, causing non-Gemini providers to route to Google and fail. Use `custom_providers` instead.

## Configuration

Proxy settings are loaded from `config/gemini.json`:

```json
{
  "listen_host": "127.0.0.1",
  "listen_port": 8899,
  "max_retries": 3,
  "max_wait_sec": 65,
  "timeout_sec": 40
}
```

## Directory Structure

```
gemini-throttle/
├── README.md
├── README.ja.md
├── api/              # Stats and aggregation logic
├── proxy/            # Proxy core
├── config/           # Configuration
└── docs/             # Deployment documentation
```

## License

MIT License. Copyright (c) 2026 Panda Captain & Reika AI.
