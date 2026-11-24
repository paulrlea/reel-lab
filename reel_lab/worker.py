import logging
from .instagram import Instagram, PublishUncertain
from .media import fingerprint

log = logging.getLogger(__name__)


def tick(config, store, client=None):
    if not config.dry_run and client is None:
        client = Instagram(config)
    job = store.claim()
    if job:
        try:
            if fingerprint(job['path']) != job['hash']:
                raise ValueError('Approved video has changed')
            if config.dry_run:
                store.finish(job['id'], 'simulated')
            else:
                media_id = client.publish(job)
                # If this commit fails, leave publishing/uncertain; do not retry.
                store.finish(job['id'], 'published', media_id)
        except PublishUncertain:
            store.finish(job['id'], 'uncertain', error='Check Instagram before manual reconciliation')
        except Exception as exc:
            # Conservative exception handling even for database write failures.
            state = 'failed' if config.dry_run else 'uncertain'
            store.finish(job['id'], state, error=f'{type(exc).__name__}: review job and logs; no automatic retry')
            log.warning('Job %s stopped (%s)', job['id'], type(exc).__name__)
    if not config.dry_run:
        for id, media_id, age in store.due_metrics():
            try:
                result = client.insights(media_id)
                if result:
                    store.save_metrics(id, age, result)
            except Exception as exc:
                log.warning('Metrics for job %s unavailable (%s)', id, type(exc).__name__)
    return job['id'] if job else None
