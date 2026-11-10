# gemini-throttle

**Version**: 0.8
**License**: MIT
**Author**: mit. Panda Captain & Reika AI

## Overview

`gemini-throttle` is a lightweight reverse proxy that sits between your application and the Google Gemini API. It avoids short-term rate limit (429) errors by **parking** (waiting) requests until the rate limit window resets, then retrying automatically.

This tool targets **short-term quota limits only** (RPM/TPM within a 1-minute window). It does not handle daily limits (RPD), authentication errors, or model-not-found errors. Fallback to other providers is out of scope — this tool focuses solely on short-term quota avoidance for Gemini.

## Problem

- Google Gemini API enforces strict short-term rate limits (RPM/TPM)
- Free tier: approximately 10-20 requests per minute
- When an AI agent (Hermes, Claude Code, etc.) calls the API in a tight loop, it hits 429 within seconds
- 429 errors are temporary — they resolve when the time window passes
- Retrying immediately does not help; the request must wait for the window to reset

## Solution

`gemini-throttle` places a proxy at `127.0.0.1:8899` between your application and Google AI Studio. When a 429 is received, it:

1. Extracts the retry delay from the response (Retry-After header, RetryInfo JSON, or body text)
2. Waits for that duration (up to 65 seconds)
3. Retries the request automatically (up to 3 attempts)

Additionally, a **TokenBucket** pre-throttles requests before they reach Google, smoothing traffic to avoid hitting 429 in the first place.

## Architecture

```
Application (Hermes, etc.)
    ↓
127.0.0.1:8899 (gemini-throttle)
    ↓ (429 → park → retry)
generativelanguage.googleapis.com/v1beta/openai
```

## Key Features

- **Park on 429**: Waits for the rate limit window to reset, then retries
- **TokenBucket pre-throttling**: 10 req/min sliding window to avoid 429 proactively
- **3-stage retry delay extraction**: Retry-After header → RetryInfo JSON → body text → default 10s
- **Max wait**: 65 seconds (configurable)
- **Max retries**: 3 (configurable)
- **Localhost only**: Binds to 127.0.0.1 (no external exposure)
- **No API key storage**: Relays the client's Authorization header (proxy holds no keys)
- **Path normalization**: Deduplicates `/v1`, `/openai`, `/v1beta` segments
- **Gemini-scoped**: Does not affect other providers (DeepInfra, OpenRouter, etc.)

## Integration

### custom_providers (recommended)

Add to your `config.yaml`:

```yaml
custom_providers:
  - name: gemini-throttled
    base_url: http://127.0.0.1:8899/v1
    api_key: ${GOOGLE_API_KEY}
    model: gemini-3.5-flash-lite
```

The existing `gemini` provider remains unchanged. Use `gemini-throttled` explicitly when needed.

### Important: Do NOT use GEMINI_BASE_URL

Setting `GEMINI_BASE_URL` in `.env` overrides **all** providers' base URLs in Hermes, causing non-Gemini providers (DeepInfra, etc.) to route to Google and fail with 404. This is a known issue. Use `custom_providers` instead.

## Configuration

Proxy settings are loaded from `config/gemini.json`:

```json
{
  "rate_per_min": 10,
  "max_retries": 3,
  "max_wait_sec": 65,
  "timeout_sec": 40
}
```

## Constraints

- 429 wait blocks the request synchronously
- Maximum wait: 65 seconds
- Maximum retries: 3
- Binds to 127.0.0.1 only
- Environment variable `GOOGLE_API_KEY` is relayed (proxy holds no keys)
- Single worker (uvicorn workers=1) to preserve TokenBucket state

## Directory Structure

```
gemini-throttle/
├── README.md
├── context.md
├── scripts/
│   └── gemini_throttle_proxy.py
├── config/
│   └── gemini.json
├── tests/
│   └── test_proxy.py
└── docs/
    └── deployment.md
```

## License

MIT License

Copyright (c) 2026 mit. Panda Captain & Reika AI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```