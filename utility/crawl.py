#!/usr/bin/env python

"""SuttaCentral Offline Crawl Utility

This utility was created specifically for crawling Sutta Central and
creating a reasonably clean and functional set of HTML files and other
assets for offline use.

Nandiya checked out the usual suspects like HTTrack and wget and was not
satisfied (partly the problem with those utilities are they are
"respectful", so it takes them a long time to crawl such a big site.
This utility takes mere minutes CPU cores permitting. They also create
(even more) complicated folder structures and uglier urls.

Features are enabled/disabled in the SuttaCentral code by checking for the
offline cookie flag.
"""

import argparse, collections, os, regex, sys, time, urllib, urllib.request
from lxml import html
from urllib.parse import urljoin

def parse_args():
    parser = argparse.ArgumentParser(
        description='SuttaCentral Offline Crawl Utility',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('host', type=str, help='the host to crawl')
    parser.add_argument('dir', type=str, help='output directory')
    parser.add_argument('-w', '--wait', type=float, default=0.0,
        help='time to wait between requests in seconds')
    parser.add_argument('-q', '--quiet', action='store_true',
        help='suppress non-errors from output')
    return parser.parse_args()

def readurl(url):
    opener = urllib.request.build_opener()
    opener.addheaders.append(('Cookie', 'offline=1'))
    with opener.open(url) as f:
        return f.read()

def addtotaskqueue(url):
    global taskqueue, seen
    url = fixurl(url)
    if url not in seen:
        taskqueue.append(url)
        seen.add(url)

def fixurl(url):
    """
        /a/b/   -> /a/b
        /a/b/#c -> /a/b
        /a/b/?c=1 -> /a/b
    """
    return regex.sub(r'(.)/?([#?].*)?$', r'\1', url)

def getending(url):
    if '.' in url:
        ending = url.split('.')[-1]
        if regex.match(r'\d', ending):
            ending = ''
    else:
        ending = ''
    return ending

def fixcss(text, depth):
    """A hack that only works on sc.css."""
    def callback(m):
        url = m[2]
        addtotaskqueue(url)
        return 'url({}{}{}{})'.format(m[1] or '', '../' * depth, url[1:], m[3] or '')
    return regex.sub(r'url\(([\'"])?(/[^\'")]+)([\'"])?\)', callback, text,
        flags=regex.MULTILINE)

def process(host, url):
    global output_dir
    fullurl = urljoin(host, url)
    ending = getending(url)
    new_url = fixurl(url)[1:]
    if new_url == '':
        new_url = 'index'
    if not ending:
        ending = 'html'
        new_url += '.html'
    depth = len(new_url.split('/')) - 1
    filename = os.path.join(output_dir, new_url)
    try:
        os.makedirs(os.path.dirname(filename))
    except OSError:
        pass
    bytes = readurl(fullurl)

    if ending not in ('html', 'js', 'css'):
        with open(filename, 'wb') as f:
            f.write(bytes)
        return

    if ending in ('css', 'js'):
        text = bytes.decode(encoding='utf8')
        if ending == 'css':
            text = fixcss(text, depth)
        with open(filename, 'w', encoding='utf8') as f:
            f.write(text)
        return

    # We need to be very careful and explicit with lxml to handle utf8
    # correctly. See http://stackoverflow.com/questions/15302125/html-encoding-and-lxml-parsing
    parser = html.HTMLParser(encoding='utf8')
    dom = html.document_fromstring(bytes, parser=parser)
    
    for a in dom.cssselect('[href], [src]'):
        attr = 'href'
        if 'src' in a.attrib:
            attr = 'src'
        try:
            href = a.attrib[attr]
        except KeyError:
            continue
        if not href or not href.startswith('/'):
            continue
        addtotaskqueue(href)
        new_href = fixurl(href)[1:]
        if new_href == '':
            new_href = 'index'
        if depth > 0:
            new_href = '../' * depth + new_href
        ending = getending(href)
        if not ending:
            new_href += '.html'

        a.attrib[attr] = new_href

    with open(filename, 'wb') as f:
        f.write('<!DOCTYPE html>\n'.encode(encoding='utf8'))
        f.write(html.tostring(dom, encoding='utf8'))

if __name__ == '__main__':

    args = parse_args()
    host = 'http://{}'.format(args.host)
    output_dir = args.dir
    quiet = args.quiet
    wait = args.wait

    taskqueue = collections.deque()
    seen = set()
    addtotaskqueue('/')

    start = time.time()
    count = 0
    while len(taskqueue) > 0:
        try:
            path = taskqueue.popleft()
            if not quiet:
                print(path)
            process(host, path)
            count += 1
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            sys.stderr.write("{}: {}\n".format(path, str(e)))
        if wait > 0:
            time.sleep(wait)

    total = time.time() - start
    if not quiet:
        print('{} pages downloaded in {} seconds, {} pages per second.'.format(count, total, round(count / total)))
    if count < 1:
        sys.exit(1)