"""Exercise a running API and one real analyzer job against the configured DB.

Run from the app root: .venv/Scripts/python.exe scripts/smoke-test.py --video clip.mp4
This intentionally creates an analysis record; use a test database/pond.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urljoin

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', required=True, type=Path)
    parser.add_argument('--api', default='http://127.0.0.1:8000')
    parser.add_argument('--max-frames', default=8, type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with httpx.Client(base_url=args.api, timeout=60) as client:
        health = client.get('/api/health')
        health.raise_for_status()
        session = client.get('/api/session')
        session.raise_for_status()
        csrf_headers = {'X-Tide-CSRF': session.json()['csrf_token']}
        with args.video.open('rb') as video:
            response = client.post('/api/jobs', headers=csrf_headers, files={'file': (args.video.name, video, 'video/mp4')}, data={
                'pond': '驗證池 A-01', 'recorded_at': datetime.now().astimezone().isoformat(),
                'mode': 'general', 'water_policy': 'report', 'max_frames': str(args.max_frames),
            })
        assert response.status_code == 202, response.text
        job_id = response.json()['id']
        print(f'Upload accepted; job {job_id}', flush=True)
        subprocess.run([sys.executable, '-m', 'app.worker', '--once'], cwd=root / 'backend', check=True, timeout=600)
        detail_response = client.get(f'/api/jobs/{job_id}')
        detail_response.raise_for_status()
        detail = detail_response.json()
        assert detail['status'] == 'completed', detail
        assert detail['tracks'] and all(detail[key] and detail[key] > 0 for key in ('avg_length_mm', 'avg_width_mm', 'avg_weight_g')), detail
        assert detail['processed_frames'] == args.max_frames, detail
        for field in ('source_video_url', 'result_video_url'):
            assert detail[field], (field, detail)
            result = client.get(urljoin(args.api, detail[field]), headers={'Range': 'bytes=0-1023'})
            assert result.status_code == 206 and 'bytes 0-' in result.headers['content-range'], result.headers
            assert b'ftyp' in result.content[:32], (field, result.content[:32])
        thumbnail = client.get(urljoin(args.api, detail['thumbnail_url']))
        assert thumbnail.status_code == 200 and thumbnail.headers['content-type'].startswith('image/'), thumbnail.headers
        overview = client.get('/api/overview', params={'pond': detail['pond']})
        overview.raise_for_status()
        summary = overview.json()['summary']
        assert summary['completed'] >= 1 and summary['shrimp_count'] >= len(detail['tracks']), summary
        for artifact in detail['artifacts']:
            download = client.get(urljoin(args.api, artifact['url']))
            assert download.status_code == 200, artifact
        local = root / '.local'
        local.mkdir(exist_ok=True)
        (local / 'smoke-result.json').write_text(json.dumps({'job': detail, 'overview': overview.json()}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'PASS: {len(detail["tracks"])} tracks; measurements persisted; video Range, thumbnail and exports available.')


if __name__ == '__main__':
    main()
