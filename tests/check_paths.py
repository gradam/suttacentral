#!/usr/bin/env python

from os.path import dirname, join, realpath
import sys

sys.path.insert(1, join(dirname(dirname(realpath(__file__))), 'python'))

import cherrypy
import config, logger, root, scdb, show

def paths():
    dbr = scdb.getDBR()
    for page in show.STATIC_PAGES:
        yield ('/' + page, 'STATIC')
    for division in dbr.divisions.values():
        yield ('/' + division.uid, division)
        if (len(division.subdivisions) > 0 and
                not (division.subdivisions[0].uid or '').endswith('nosub')):
            yield ('/' + division.uid + '/full', division)
            for subdivision in division.subdivisions:
                if subdivision.uid:
                    yield ('/' + subdivision.uid, subdivision)
    for sutta in dbr.suttas.values():
        yield ('/' + sutta.uid, sutta)
        if sutta.url and sutta.url.startswith('/'):
            yield (sutta.url, sutta)
        for translation in sutta.translations:
            if translation.url and translation.url.startswith('/'):
                yield (translation.url, translation)

def get_path(path):
    app = cherrypy.tree.apps['']
    local = cherrypy.lib.httputil.Host('127.0.0.1', 50000, '')
    remote = cherrypy.lib.httputil.Host('127.0.0.1', 50001, '')
    request, _ = app.get_serving(local, remote, 'http', 'HTTP/1.1')
    response = request.run('GET', path, '', 'HTTP/1.1', [('Host', '127.0.0.1')], None)
    if response.output_status.decode('utf-8') != '200 OK':
        raise Exception('Unexpected response: %s' % response.output_status)
    response.collapse_body()
    return len(response.body[0]) > 0

def check_paths():
    for path, obj in paths():
        try:
            result = get_path(path)
            exception = None
        except Exception as e:
            result = False
            exception = e
        if not result:
            print(path)
            print('  Exception: %s' % repr(exception))
            print('  Object: %s' % repr(obj))

def setup():
    config['global'].update({
        'environment': 'test_suite',
        'log.access_file': '',
        'log.error_file': '',
        'log.screen': False,
    })
    config['app'].update({
        'app_log_level': 'CRITICAL',
        'console_log_level': 'CRITICAL',
    })
    logger.setup()
    cherrypy.config.update(config['global'])
    cherrypy.server.unsubscribe()
    cherrypy.tree.mount(root.Root(), config=config)
    cherrypy.engine.start()

if __name__ == '__main__':
    setup()
    check_paths()
    cherrypy.engine.exit()