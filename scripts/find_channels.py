"""Find YouTube channel IDs for podcast channels."""
import yt_dlp

channels = [
    'https://www.youtube.com/@acquiredpodcast/videos',
    'https://www.youtube.com/@a16z/videos',
    'https://www.youtube.com/@20aborrar/videos',  
    'https://www.youtube.com/@20VCwithHarryStebbings/videos',
    'https://www.youtube.com/@LoganBartlett/videos',
    'https://www.youtube.com/@CognitiveRevolutionPodcast/videos',
    'https://www.youtube.com/@bg2pod/videos',
    'https://www.youtube.com/@TheTWIMLAIPodcast/videos',
    'https://www.youtube.com/@EyeonAI/videos',
]

ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True, 'playlistend': 1}

for url in channels:
    handle = url.split('/@')[1].split('/')[0] if '/@' in url else url
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        cid = info.get('channel_id', '?')
        name = info.get('channel', info.get('uploader', '?'))
        entries = list(info.get('entries', []))
        latest = entries[0].get('title', '')[:50] if entries else 'no videos'
        date = entries[0].get('upload_date', '?') if entries else '?'
        print(f"{handle}: {cid} | {name} | {latest} ({date})")
    except Exception as e:
        err = str(e)[:80].encode('ascii','replace').decode()
        print(f"{handle}: ERR {err}")
