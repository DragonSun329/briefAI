import sys, io, os, re, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import dotenv; dotenv.load_dotenv()
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get('OPENROUTER_API_KEY'),
    base_url='https://openrouter.ai/api/v1'
)

resp = client.chat.completions.create(
    model='tngtech/deepseek-r1t-chimera:free',
    messages=[
        {'role': 'system', 'content': 'You are a JSON-only assistant. Return ONLY valid JSON, no explanation.'},
        {'role': 'user', 'content': 'Return a JSON object with key "trends" containing a list of 2 items, each with "name" and "score" fields.'}
    ],
    temperature=0.3,
    max_tokens=500
)

raw = resp.choices[0].message.content
print('=== RAW RESPONSE ===')
print(repr(raw[-500:]))
print()
print('=== AFTER STRIP ===')
stripped = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
print(repr(stripped[:500]))
print()
try:
    for i, c in enumerate(stripped):
        if c in ('{', '['):
            data = json.loads(stripped[i:])
            print('=== PARSED OK ===')
            print(json.dumps(data, indent=2))
            break
    else:
        print('No JSON object found')
except json.JSONDecodeError as e:
    print(f'Parse failed: {e}')
