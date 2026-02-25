import asyncio, sys, os
sys.path.insert(0, '.')

# Temporarily disable Kimi to avoid hanging calls
# Unset Kimi keys so provider switcher skips them
for key in ['KIMI_API_KEY', 'KIMI25_API_KEY']:
    os.environ.pop(key, None)

from modules.daily_brief import DailyBriefGenerator

async def main():
    gen = DailyBriefGenerator()
    path = await gen.generate(top_n_stories=15)
    print(f'DONE: {path}')

asyncio.run(main())
