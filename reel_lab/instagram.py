import re
import time
from urllib.parse import urlencode, urlsplit, quote
from pathlib import Path
from .net import request, RemoteError


class PublishUncertain(RuntimeError):
    pass


class Instagram:
    def __init__(self, config):
        self.c = config
        self.base = ('https://graph.facebook.com/' if config.login == 'facebook' else 'https://graph.instagram.com/') + config.version + '/'
        if not config.allow_live or config.dry_run:
            raise ValueError('Live publishing is disabled')
        if not re.fullmatch(r'\d+', config.user_id) or not config.token:
            raise ValueError('Configure IG_USER_ID and IG_ACCESS_TOKEN')
        if config.login == 'instagram' and config.upload == 'resumable':
            raise ValueError('Instagram Login requires URL uploads; use Facebook Login for local uploads')

    def graph(self, path, method='GET', payload=None, query=None):
        return request(self.base + path + ('?' + urlencode(query) if query else ''), method=method, payload=payload, headers={'Authorization': 'Bearer ' + self.c.token})

    def identity(self):
        return self.graph(self.c.user_id, query={'fields': 'id,username'})

    def publish(self, job):
        if job['trial'] not in ('MANUAL', 'SS_PERFORMANCE'):
            raise ValueError('Invalid trial strategy')
        body = {'media_type':'REELS', 'caption':job['caption'], 'trial_params':{'graduation_strategy': job['trial']}}
        if self.c.upload == 'resumable':
            body['upload_type'] = 'resumable'
        else:
            url = job['video_url'] or (self.c.media_base.rstrip('/') + '/' + quote(Path(job['path']).name) if self.c.media_base else '')
            if urlsplit(url).scheme != 'https' or not urlsplit(url).hostname:
                raise ValueError('URL mode requires a public HTTPS video URL')
            body['video_url'] = url
        container = self.graph(self.c.user_id + '/media', 'POST', payload=body)
        container_id = str(container['id'])
        if not container_id.isdigit():
            raise ValueError('Invalid container ID')
        if self.c.upload == 'resumable':
            path = Path(job['path'])
            if path.stat().st_size > 300_000_000:
                raise ValueError('Video exceeds configured upload limit')
            uri = f'https://rupload.facebook.com/ig-api-upload/{self.c.version}/{container_id}'
            result = request(uri, method='POST', raw=path.read_bytes(), headers={'Authorization': 'OAuth ' + self.c.token,'offset':'0','file_size':str(path.stat().st_size),'Content-Type':'application/octet-stream'}, timeout=300)
            if result.get('success') is not True:
                raise RemoteError('Video upload was not confirmed')
        for _ in range(30):
            status = self.graph(container_id, query={'fields':'status_code'}).get('status_code')
            if status == 'FINISHED':
                break
            if status in ('ERROR','EXPIRED','PUBLISHED'):
                raise RemoteError('Container is not publishable: ' + status)
            time.sleep(10)
        else:
            raise RemoteError('Video processing timed out')
        # Do not retry the final publish call, even on timeout.
        try:
            result = self.graph(self.c.user_id + '/media_publish', 'POST', payload={'creation_id':container_id})
            media_id = str(result['id'])
            if not media_id.isdigit():
                raise ValueError('Invalid response ID')
            return media_id
        except Exception as exc:
            raise PublishUncertain('Publish outcome unknown; inspect Instagram before reconciling') from exc

    def insights(self, media_id):
        values = {}
        for metric in ('views', 'reach', 'likes', 'comments', 'shares', 'saved', 'ig_reels_avg_watch_time'):
            try:
                data = self.graph(str(media_id) + '/insights', query={'metric':metric}).get('data', [])
                item = data[0] if data else {}
                v = item.get('values', [])
                val = item.get('total_value', {}).get('value') if not v else v[0].get('value')
                if isinstance(val, (int, float)):
                    values[metric] = val
            except RemoteError:
                continue
        return values
