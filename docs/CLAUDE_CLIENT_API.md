# Claude Client API Documentation

## Overview

The `ClaudeClient` is an enhanced wrapper for the Anthropic Claude API that provides:

- **Automatic retry** with exponential backoff for transient errors
- **Response caching** to reduce API costs and improve performance
- **Token counting** and cost estimation
- **Batch processing** for multiple requests
- **Structured JSON parsing** with validation
- **Comprehensive error handling** for different failure modes
- **Usage statistics tracking** for monitoring and optimization

## Installation

```bash
pip install anthropic tenacity loguru python-dotenv
```

## Quick Start

```python
from utils.claude_client import ClaudeClient

# Initialize client
client = ClaudeClient()

# Basic chat
response = client.chat(
    system_prompt="You are a helpful assistant.",
    user_message="Explain AI in one sentence"
)
print(response)

# Get statistics
client.print_stats()
```

## API Reference

### Initialization

```python
ClaudeClient(
    api_key: Optional[str] = None,
    model: str = "claude-sonnet-4-5-20250429",
    max_tokens: int = 4096,
    temperature: float = 0.3,
    enable_caching: bool = True,
    cache_manager: Optional[CacheManager] = None
)
```

**Parameters:**
- `api_key`: Anthropic API key (defaults to `ANTHROPIC_API_KEY` env var)
- `model`: Claude model identifier
- `max_tokens`: Maximum tokens in response (default: 4096)
- `temperature`: Temperature for generation 0.0-1.0 (default: 0.3)
- `enable_caching`: Enable response caching (default: True)
- `cache_manager`: Optional CacheManager instance for caching

**Supported Models:**
- `claude-sonnet-4-5-20250429` (default) - Latest Sonnet, best balance
- `claude-sonnet-4-20250514` - Sonnet 4
- `claude-3-5-sonnet-20241022` - Sonnet 3.5
- `claude-3-opus-20240229` - Most capable, highest cost

### Core Methods

#### `chat()`

Send a text request to Claude.

```python
response = client.chat(
    system_prompt: str,
    user_message: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    use_cache: bool = True
) -> str
```

**Example:**
```python
response = client.chat(
    system_prompt="You are an expert in AI.",
    user_message="What is a transformer model?",
    temperature=0.5
)
```

#### `chat_structured()`

Send a request expecting JSON response.

```python
json_response = client.chat_structured(
    system_prompt: str,
    user_message: str,
    response_format: str = "json",
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    use_cache: bool = True
) -> Dict[str, Any]
```

**Example:**
```python
result = client.chat_structured(
    system_prompt="You are a data extractor.",
    user_message="Extract the title and author from: 'The Great Gatsby by F. Scott Fitzgerald'"
)
# Returns: {"title": "The Great Gatsby", "author": "F. Scott Fitzgerald"}
```

**JSON Parsing:**
- Automatically extracts JSON from code blocks (```json)
- Handles plain JSON responses
- Validates and parses the response
- Raises `ValueError` if JSON is invalid

#### `batch_chat()`

Process multiple requests in batch.

```python
responses = client.batch_chat(
    requests: List[Dict[str, str]],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    delay_between_calls: float = 0.5
) -> List[str]
```

**Example:**
```python
requests = [
    {
        "system_prompt": "You are a translator.",
        "user_message": "Translate 'hello' to Spanish"
    },
    {
        "system_prompt": "You are a translator.",
        "user_message": "Translate 'goodbye' to French"
    }
]

responses = client.batch_chat(requests)
```

### Statistics & Monitoring

#### `get_stats()`

Get usage statistics.

```python
stats = client.get_stats() -> Dict[str, Any]
```

**Returns:**
```python
{
    "total_calls": 42,
    "cache_hits": 15,
    "cache_misses": 27,
    "total_input_tokens": 12500,
    "total_output_tokens": 8300,
    "total_cost": 0.4835,
    "errors": 2,
    "cache_hit_rate": "35.7%",
    "average_cost_per_call": 0.0115
}
```

#### `print_stats()`

Print formatted statistics to console.

```python
client.print_stats()
```

**Output:**
```
==================================================
Claude API Usage Statistics
==================================================
Total API calls:       42
Cache hits:            15 (35.7%)
Cache misses:          27
Errors:                2

Total input tokens:    12,500
Total output tokens:   8,300
Total tokens:          20,800

Total cost:            $0.4835
Avg cost per call:     $0.0115
==================================================
```

#### `reset_stats()`

Reset all statistics to zero.

```python
client.reset_stats()
```

## Features

### 1. Automatic Retry

Automatically retries on transient errors with exponential backoff.

```python
# Automatically retries up to 3 times
response = client.chat(
    system_prompt="...",
    user_message="..."
)
```

**Retried Errors:**
- `RateLimitError` - Rate limit exceeded
- `APIConnectionError` - Network issues

**Backoff Strategy:**
- Initial wait: 2 seconds
- Maximum wait: 10 seconds
- Multiplier: 1.0 (exponential)

### 2. Response Caching

Reduces API costs by caching responses.

```python
from utils.cache_manager import CacheManager

cache = CacheManager()
client = ClaudeClient(enable_caching=True, cache_manager=cache)

# First call - API request
response1 = client.chat(system_prompt="...", user_message="...")

# Second identical call - cached response (no API call)
response2 = client.chat(system_prompt="...", user_message="...")

assert response1 == response2
print(f"Cache hits: {client.stats['cache_hits']}")  # 1
```

**Cache Behavior:**
- Cache key based on: model, system_prompt, user_message, temperature, max_tokens
- Default TTL: 24 hours
- Can be disabled per-request with `use_cache=False`

### 3. Cost Tracking

Automatically tracks token usage and calculates costs.

**Pricing (per million tokens):**

| Model | Input | Output |
|-------|-------|--------|
| Claude Sonnet 4.5 | $3.00 | $15.00 |
| Claude Sonnet 4 | $3.00 | $15.00 |
| Claude 3.5 Sonnet | $3.00 | $15.00 |
| Claude 3 Opus | $15.00 | $75.00 |

```python
# Make some calls
client.chat(...)

# Check costs
stats = client.get_stats()
print(f"Total cost: ${stats['total_cost']:.4f}")
print(f"Average per call: ${stats['average_cost_per_call']:.4f}")
```

### 4. Error Handling

Comprehensive error handling with logging.

```python
try:
    response = client.chat(
        system_prompt="...",
        user_message="..."
    )
except RateLimitError:
    print("Rate limit exceeded - retries exhausted")
except APIConnectionError:
    print("Network connection failed")
except APIError as e:
    print(f"API error: {e}")
except ValueError as e:
    print(f"Invalid response format: {e}")
```

## Best Practices

### 1. Use Caching for Repeated Requests

```python
# Enable caching for repetitive tasks
cache = CacheManager()
client = ClaudeClient(enable_caching=True, cache_manager=cache)

# Evaluation of similar articles will benefit from caching
for article in articles:
    score = client.chat_structured(
        system_prompt=EVALUATION_PROMPT,
        user_message=f"Evaluate: {article}"
    )
```

### 2. Use Appropriate Temperature

```python
# Low temperature (0.0-0.3) for factual tasks
response = client.chat(
    system_prompt="Extract facts.",
    user_message="...",
    temperature=0.2
)

# Higher temperature (0.5-0.8) for creative tasks
response = client.chat(
    system_prompt="Write a story.",
    user_message="...",
    temperature=0.7
)
```

### 3. Batch Similar Requests

```python
# Instead of individual calls
for item in items:
    client.chat(...)  # Inefficient

# Use batch processing
requests = [
    {"system_prompt": "...", "user_message": item}
    for item in items
]
responses = client.batch_chat(requests, delay_between_calls=0.5)
```

### 4. Monitor Statistics

```python
# Periodically check statistics
if client.stats["total_calls"] % 10 == 0:
    client.print_stats()

# Reset stats for new reporting period
client.reset_stats()
```

### 5. Handle Errors Gracefully

```python
try:
    response = client.chat(...)
except Exception as e:
    logger.error(f"Claude API failed: {e}")
    # Fallback to default behavior
    response = fallback_response
```

## Examples

### Example 1: Category Selection

```python
client = ClaudeClient()

response = client.chat_structured(
    system_prompt="""You are a category selector.
Available categories: AI, Politics, Business, Tech.
Return JSON: {"categories": [...]}""",
    user_message="I want news about AI and Business"
)

print(response["categories"])  # ["AI", "Business"]
```

### Example 2: Article Evaluation

```python
articles = load_articles()
evaluations = []

for article in articles:
    eval_result = client.chat_structured(
        system_prompt="Rate this article on impact (1-10) and relevance (1-10).",
        user_message=f"Title: {article['title']}\nContent: {article['content']}"
    )
    evaluations.append(eval_result)

# Print cost summary
client.print_stats()
```

### Example 3: Batch Translation

```python
texts = ["Hello", "Goodbye", "Thank you"]

requests = [
    {
        "system_prompt": "Translate to Chinese, return only the translation.",
        "user_message": text
    }
    for text in texts
]

translations = client.batch_chat(requests, delay_between_calls=0.3)
```

## Troubleshooting

### Issue: "ANTHROPIC_API_KEY not found"

**Solution:** Set your API key:
```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
# or
echo "ANTHROPIC_API_KEY=sk-ant-api03-..." >> .env
```

### Issue: Rate limits

**Solution:** Use batch processing with delays:
```python
responses = client.batch_chat(
    requests,
    delay_between_calls=1.0  # 1 second between calls
)
```

### Issue: JSON parsing errors

**Solution:** Improve your prompt:
```python
system_prompt = """
Return ONLY valid JSON with no additional text.
Format: {"key": "value"}
"""
```

### Issue: High costs

**Solutions:**
1. Enable caching
2. Use lower max_tokens
3. Use Sonnet instead of Opus
4. Monitor with `print_stats()`

## Performance Tips

1. **Enable caching** for repeated similar requests
2. **Use batch processing** for multiple requests
3. **Set appropriate max_tokens** to avoid overgeneration
4. **Use lower temperature** for deterministic tasks
5. **Monitor stats** regularly to track costs

## API Version

This client is compatible with:
- Anthropic API: v1
- anthropic-sdk-python: >= 0.25.0

---

**Last Updated:** October 2024
