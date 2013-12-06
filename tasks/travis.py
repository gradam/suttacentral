"""Tasks to run in the Travis CI environment."""

import os
import time

import tasks.db
from .helpers import *

TRAVIS_LOCAL_CONF = """\
[mysql]
    user: 'travis'
    password: ''
    db: 'suttacentral'
"""

@task
def prepare():
    """Prepare the travis environment."""
    with open('local.conf', 'w', encoding='utf-8') as f:
        f.write(TRAVIS_LOCAL_CONF)
    run('mysql -e "CREATE DATABASE suttacentral;"')
    tasks.db.reset()

@task
def start_server():
    """Start a daemonized server for the travis environment."""
    run('cd src && python server.py &')
    # Give time to server to warm up.
    time.sleep(10)

@task
def stop_server():
    """Stop the daemonized server for the travis environment."""
    run('pkill -f server.py')
