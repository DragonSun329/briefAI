# Claude Client Quick Reference

## Import

```python
from utils.claude_client import ClaudeClient
from utils.cache_manager import CacheManager
```

## Basic Usage

```python
# Simple initialization
client = ClaudeClient()

# With caching
cache = CacheManager()
client = ClaudeClient(enable_caching=True, cache_manager=cache)

# Custom settings
client = ClaudeClient(
    model="claude-3-opus-20240229",
    temperature=0.7,
    max_tokens=2000
)
```

## Core Methods

### Chat
```python
response = client.chat(
    system_prompt="You are a helpful assistant",
    user_message="Hello, Claude!",
    temperature=0.5,          # Optional
    max_tokens=1000,          # Optional
    use_cache=True            # Optional
)
```

### Structured JSON
```python
result = client.chat_structured(
    system_prompt="Return JSON only",
    user_message="Extract name and age from: John, 30"
)
# Returns: {"name": "John", "age": 30}
```

### Batch Processing
```python
requests = [
    {"system_prompt": "Translate", "user_message": "Hello"},
    {"system_prompt": "Translate", "user_message": "Goodbye"}
]
responses = client.batch_chat(
    requests,
    delay_between_calls=0.5
)
```

## Statistics

```python
# Get stats as dict
stats = client.get_stats()

# Print formatted stats
client.print_stats()

# Reset stats
client.reset_stats()
```

## Common Patterns

### Pattern 1: Evaluate Articles
```python
cache = CacheManager()
client = ClaudeClient(enable_caching=True, cache_manager=cache)

for article in articles:
    score = client.chat_structured(
        system_prompt="Rate this article 1-10",
        user_message=article['content']
    )
    article['score'] = score['rating']

client.print_stats()  # Check cost and cache hits
```

### Pattern 2: Batch Translation
```python
client = ClaudeClient()

requests = [
    {"system_prompt": f"Translate to {lang}", "user_message": text}
    for lang in languages
    for text in texts
]

translations = client.batch_chat(requests, delay_between_calls=0.3)
```

### Pattern 3: Monitor Costs
```python
client = ClaudeClient()

# Make requests...
client.chat(...)
client.chat(...)

# Check costs periodically
stats = client.get_stats()
if stats['total_cost'] > 1.0:
    print(f"Warning: Cost exceeded $1.00: ${stats['total_cost']:.2f}")
```

## Error Handling

```python
from anthropic import RateLimitError, APIError

try:
    response = client.chat(
        system_prompt="...",
        user_message="..."
    )
except RateLimitError:
    print("Rate limit - automatic retry failed")
except APIError as e:
    print(f"API error: {e}")
except ValueError as e:
    print(f"Invalid JSON: {e}")
```

## Pricing Reference

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| Sonnet 4.5 | $3.00 | $15.00 |
| Sonnet 4 | $3.00 | $15.00 |
| Sonnet 3.5 | $3.00 | $15.00 |
| Opus | $15.00 | $75.00 |

## Tips

1. **Enable caching** for repeated similar requests (80% cost savings)
2. **Use batch_chat** for multiple requests with delay to respect rate limits
3. **Monitor stats** regularly with `print_stats()`
4. **Lower temperature** (0.0-0.3) for factual/deterministic tasks
5. **Higher temperature** (0.5-0.8) for creative tasks
6. **Set max_tokens** appropriately to avoid overgeneration

## Debugging

```python
# Enable debug logging
import os
os.environ['LOG_LEVEL'] = 'DEBUG'

# Check what's cached
cache = CacheManager()
print(cache.cache_dir)  # See cache location

# Force disable cache for testing
response = client.chat(..., use_cache=False)
```

---

**See full documentation:** [CLAUDE_CLIENT_API.md](CLAUDE_CLIENT_API.md)
