import os

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage


class VersionedStaticFilesStorage(StaticFilesStorage):
    """
    Development: add ``?v=<file modification time>`` to every {% static %} URL so a
    changed CSS / JS file gets a new URL and browsers never show a stale cached copy.
    (Production uses ManifestStaticFilesStorage, which does the same with file hashes.)
    """

    def url(self, name):
        url = super().url(name)
        path = finders.find(name)
        if path and os.path.exists(path):
            return f"{url}?v={int(os.path.getmtime(path))}"
        return url
