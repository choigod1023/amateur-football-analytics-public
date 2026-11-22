"""Bounded latest-preview worker; analysis itself never enters this queue.

One snapshot may be publishing and at most one more may be pending. Replacing a
pending snapshot drops its frame and metadata together. ``close`` drains the
latest pending snapshot and reports any worker failure to the caller.
"""
from copy import deepcopy
from threading import Condition, Thread


class PublishWorkerError(RuntimeError):
    """Preview publication failed in the worker; the original error is chained."""


class AsyncPublisher:
    def __init__(self, publisher):
        self.publisher = publisher
        self._condition = Condition()
        self._pending = None
        self._closing = False
        self._error = None
        self._active = False
        self._submitted = 0
        self._completed = 0
        self._replaced = 0
        self._abandoned = 0
        self._worker = Thread(target=self._run, name='football-preview-publisher', daemon=True)
        self._worker.start()

    def _raise_error(self):
        if self._error is not None:
            raise PublishWorkerError('Preview publisher worker failed') from self._error

    def publish(self, frame, *args, **kwargs):
        """Capture an independent snapshot, replacing only the pending preview.

        Returns None: an asynchronous call does not return LivePublisher's data.
        The caller can safely draw on/reuse its frame after this method returns.
        """
        with self._condition:
            self._raise_error()
            if self._closing:
                raise RuntimeError('Preview publisher is closed')
        snapshot = (frame.copy(), deepcopy(args), deepcopy(kwargs))
        with self._condition:
            self._raise_error()
            if self._closing:
                raise RuntimeError('Preview publisher is closed')
            if self._pending is not None:
                self._replaced += 1
            self._pending = snapshot
            self._submitted += 1
            self._condition.notify()

    @property
    def stats(self):
        with self._condition:
            return {'submitted': self._submitted, 'completed': self._completed,
                    'replaced': self._replaced, 'abandoned': self._abandoned,
                    'pending': int(self._pending is not None), 'active': self._active,
                    'closed': self._closing, 'failed': self._error is not None}

    def close(self, timeout=None):
        """Flush the latest pending preview and propagate errors, never hide them.

        A timeout leaves the worker closing (it may finish later); calling close
        again is allowed. The default waits for the bounded queue to finish.
        """
        with self._condition:
            self._closing = True
            self._condition.notify_all()
        self._worker.join(timeout=timeout)
        if self._worker.is_alive():
            raise TimeoutError('Preview publisher did not finish before close timeout')
        with self._condition:
            self._raise_error()

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._pending is not None or self._closing)
                if self._pending is None:
                    return
                snapshot, self._pending = self._pending, None
                self._active = True
            frame, args, kwargs = snapshot
            try:
                self.publisher.publish(frame, *args, **kwargs)
            except BaseException as exc:
                with self._condition:
                    self._error = exc
                    self._active = False
                    self._abandoned += int(self._pending is not None)
                    self._pending = None
                    self._closing = True
                    self._condition.notify_all()
                return
            with self._condition:
                self._completed += 1
                self._active = False
                self._condition.notify_all()
