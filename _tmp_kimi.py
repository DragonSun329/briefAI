import requests, json

KEY = "sk-kimi-2piZh9Y7dahdQcTAc5iGwBpRdQgTD2lViXvsRMZ0l0hXtKLCjoIHnnAVfb04EQkF"
headers = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

# Try a chat completion directly — maybe models endpoint is restricted
bases = [
    "https://api.moonshot.cn/v1",
    "https://api.moonshot.ai/v1",
]

models_to_try = [
    "kimi-2.5",
    "kimi-latest",
    "moonshot-v1-auto",
    "moonshot-v1-8k",
    "k1",
    "kimi-k1.5",
]

for base in bases:
    print(f"\n=== {base} ===")
    for model in models_to_try:
        try:
            resp = requests.post(
                f"{base}/chat/completions",
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 10,
                },
                timeout=15,
            )
            status = resp.status_code
            body = resp.text[:200]
            if status == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                print(f"  {model}: OK -> {content[:50]}")
                # If it works, list models
                break
            else:
                print(f"  {model}: {status} {body[:100]}")
        except Exception as e:
            print(f"  {model}: {e}")
