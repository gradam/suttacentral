"""Temporary file tasks."""

from tasks.helpers import *


@task
def clean(ctx):
    """Delete Python cache and temporary files."""
    blurb(clean)
    rm_rf(
        '__pycache__',
        '*/__pycache__',
        '*/*/__pycache__',
        'tmp/*'
    )
