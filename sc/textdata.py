import os
import lz4
import time
import regex
import pickle
import pathlib
import hashlib
import logging
import sqlite3
import datetime
import functools
import threading
from itertools import chain

import sc
import sc.util
import sc.logger
from sc.tools import html

logger = logging.getLogger(__name__)

build_logger = logging.getLogger(__name__ + '.build')
build_logger.addHandler(sc.logger.console_log)
build_logger.addHandler(sc.logger.file_log)
build_logger.addHandler(sc.logger.startup_log)
build_logger.setLevel('INFO')

""" A tool responsible for collating information from the texts

"""

class TextInfo:
    __slots__ = ('uid', 'file_uid', 'lang', 'path', 'bookmark', 'name',
                 'author', 'volpage', 'prev_uid', 'next_uid', 
                 'cdate', 'mdate')

    def __init__(self, **kwargs):
        for key in self.__slots__:
            value = kwargs.get(key, None)
            if key == 'path':
                value = pathlib.Path(value) if value else None
            setattr(self, key, value)
    
    def __repr__(self):
        return 'TextInfo({})'.format(', '.join('{}={}'.format(attr, getattr(self, attr)) for attr in self.__slots__))

    def as_dict(self):
        return {key: getattr(self, key) for key in self.__slots__}

    @property
    def url(self):
        out = '/{}/{}'.format(self.lang, self.uid)
        if self.bookmark:
            out = out + '#{}'.format(self.bookmark)
        return out

class TIMManager:
    db_name_tmpl = 'text-info-model-{lang}_{hash}.pklz'
    version = 2
    def __init__(self):
        self.instance = None
        self.load_lock = threading.Lock()
        self.ready = threading.Event()
    
    @classmethod
    def get_db_name(cls, lang_dir):
        md5 = sc.util.get_folder_deep_md5(lang_dir, include_filter=lambda file: file.endswith('.html'))
        md5.update(str(cls.version).encode('ascii'))
        
        return cls.db_name_tmpl.format(lang=lang_dir.stem, hash=md5.hexdigest()[:10])

    def load_if_needed(self, force=False):
        """ Only load if loading not already in progress
                
        If another thread is already loading the TIM, then
        this method simply waits until loading is complete
        and then returns. It does not result in an unessecary
        load. 
        In contrast the load method will always result
        in the TIM being loaded or reloaded.
        """
        if self.load_lock.acquire(blocking=False):
            try:
                self.load_inner()
            finally:
                self.load_lock.release()
        else:
            self.ready.wait()
        
    def load(self, force=False):
        """ Load an instance of the TextInfoModel 
        
        This generates a database per language folder, if no
        file has changed within a language folder, the cached data is 
        simply unpickled and reused.
        If any file has changed, the entire data for that language is
        regenerated and pickled.
        The individual databases per language folder are finally spliced
        into a single database.
        
        """
        with self.load_lock:
            self.load_inner(force)
    
    def load_inner(self, force=False):        
        components = {}
        files_used = set()
        
        for lang_dir in sorted(sc.text_dir.glob('*')):
            if lang_dir.is_dir():
                lang_uid = lang_dir.stem
                db_filename = self.get_db_name(lang_dir)
                db_file = sc.db_dir / db_filename
                lang_tim = None
                if not force and db_file.exists():
                    try:
                        lang_tim = sc.util.lz4_pickle_load(db_file)
                        build_logger.info('Loading TIM data for "{}" from disk'.format(lang_uid))
                    except Exception as e:
                        logging.exception(e)
                if not lang_tim:
                    build_logger.info('Building TIM data for "{}"'.format(lang_uid))
                    lang_tim = TextInfoModel(name=lang_uid)
                    lang_tim.build(lang_dir, force=True)
                    sc.util.lz4_pickle_dump(lang_tim, db_file)
                components[lang_uid] = lang_tim
                files_used.add(db_file)
        
        build_logger.info('Removing unused db files')
        # Delete Unused Files:
        for file in sc.db_dir.glob(self.db_name_tmpl.format(lang='*', hash='*')):
            if file not in files_used:
                file.unlink()
        
        # Now we need to splice the individual languages
        tim = TextInfoModel('Oneness')
        
        build_logger.info('Splicing TIM data')
        for lang_uid, baby_tim in components.items():
            sc.util.recursive_merge(tim._by_lang, baby_tim._by_lang)
            sc.util.recursive_merge(tim._by_uid, baby_tim._by_uid)
            sc.util.recursive_merge(tim._metadata, baby_tim._metadata)
            sc.util.recursive_merge(tim._codepoints, baby_tim._codepoints)
        
        self._set_instance(tim)
        build_logger.info('TIM is ready')
    
    def get(self):
        if self.instance:
            return self.instance
        self.load_if_needed()
        return self.instance
        
    def _set_instance(self, instance):
        self.instance = instance
        # Other threads can now use it.
        self.ready.set()


class TextInfoModel:
    """ The TextInfoModel is responsible for scanning the entire contents
    of the text folders and building a model containing information not
    easily gleaned at a glance of the filesystem, which is required for
    purposes other than delivering the HTML of the text itself.

    It is required to delve quite deeply into the structure of the documents
    to discover all that is needed to be known, hence the scanning is
    quite time-consuming.

    This is the python-dict based TIM, it generates a structure
    consisting entirely of python dicts which can be pickled.

    """
    FILES_N = 200
    def __init__(self, name="unnamed"):
        self._by_lang = {}
        self._by_uid = {}
        self._metadata = {}
        self._codepoints = {}
        self.name = name
    
    def to_json(self):
        def default(obj):
            if hasattr(obj, 'as_dict'):
                result = obj.as_dict()
                for k, v in list(result.items()):
                    if not v or k in {'path', 'lang', 'cdate', 'mdate', 'uid', 'file_uid', 'bookmark'}:
                        del result[k]
                return result
            elif isinstance(obj, pathlib.Path):
                return str(obj)
            else:
                raise TypeError("{} does not have as_dict method".format(obj))
        return json.dumps(self._by_lang, indent=2, ensure_ascii=False, default=default)
        
    
    def build_process(self, percent):
        if percent % 10 == 0:
            build_logger.info('TIM build {}% done'.format(percent))
    
    def is_happy(self):
        return True
        
    def repair(self):
        return
        
    def datestr(self, timestamp):
        return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
    
    def get_codepoints_used(self, lang_uid=None, weight_or_style='normal'):
        if lang_uid:
            unicodes_by_weight = self._codepoints.get(lang_uid)
            if not unicodes_by_weight: 
                return None
            return unicodes_by_weight[weight_or_style]
        
        result = set()
        result.update(*(unicodes[weight_or_style] for unicodes in self._codepoints.values()))
        return result

    def get(self, uid=None, lang_uid=None):
        """ Returns TextInfo entries which match arguments

        If both uid and lang_uid are defined, a single entry is returned
        if uid is set a dictionary of entries keyed by lang_uid is returned
        if lang_uid is set a dict of entries keyed by uid is returned
        if neither is set a ValueError is raised

        This method returns None or an empty dict if there are no matching entries.
        """
        
        try:
            if uid and lang_uid:
                try:
                    return self._by_uid[uid][lang_uid]
                except KeyError:
                    return None
            elif uid:
                return self._by_uid.get(uid, {})
            elif lang_uid:
                return self._by_lang.get(lang_uid, {})
            else:
                raise ValueError('At least one of uid or lang_uid must be set')
        except KeyError:
            return None

    def exists(self, uid=None, lang_uid=None):
        if uid is None and lang_uid is None:
            raise ValueError
        return bool(self.get(uid, lang_uid))

    def add_text_info(self, lang_uid, uid, textinfo):
        if lang_uid not in self._by_lang:
            self._by_lang[lang_uid] = {}
        self._by_lang[lang_uid][uid] = textinfo
        if uid not in self._by_uid:
            self._by_uid[uid] = {}
        self._by_uid[uid][lang_uid] = textinfo

    def get_palipagenumbinator(self):
        if not self._ppn:
            self._ppn = PaliPageNumbinator()
        return self._ppn
        
    def add_metadata(self, filepath, author, metadata):
        target = self._metadata
        for part in filepath.parent.parts:
            if part not in target:
                target[part] = {}
            target = target[part]
        target['author'] = author
        with (sc.text_dir / filepath).open('r') as f:
            target['string'] = f.read()
            
    def get_metadata(self, filepath):
        target = self._metadata
        for part in filepath.parent.parts:
            if part in target:
                target = target[part]
            else:
                break
        if target == self._metadata:
            return None
        return target
    
    @staticmethod
    def uids_are_related(uid1, uid2, _rex=regex.compile(r'\p{alpha}*(?:-\d+)?')):
        # We will perform a simple uid comparison
        # We could be more sophisticated! For example we could
        # inspect whether they belong to the same division
        if uid1 is None or uid2 is None:
            return False
        
        m1 = _rex.match(uid1)[0]
        m2 = _rex.match(uid2)[0]
        if m1 and m2 and m1 == m2:
            return True
    
    
    def is_bold(self, lang, element):
        if element.tag in {'b', 'strong'}:
            return True
        if lang in {'zh', 'lzh', 'ko', 'jp', 'tw'}:
            if element.tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
                return True
        return False
    
    def is_italic(self, lang, element):
        if element.tag in {'i', 'em'}:
            return True
        return False    
    
    def build(self, lang_dir, force=False):
        # The pagenumbinator should be scoped because it uses
        # a large chunk of memory which should be gc'd.
        # But it shouldn't be created at all if we don't need it.
        # So we use a getter, and delete it when we are done.
        self._ppn = None
        
        codepoints = set()
        bold_codepoints = set()
        italic_codepoints = set()        

        lang_uid = lang_dir.stem
        all_files = sorted(lang_dir.glob('**/*.html'), key=lambda f: sc.util.numericsortkey(f.stem))
        files = [f for f in all_files if f.stem == 'metadata'] + [f for f in all_files if f.stem != 'metadata']
        for i, htmlfile in enumerate(files):
         try:
            if not self._should_process_file(htmlfile, force):
                continue
            logger.info('Adding file: {!s}'.format(htmlfile))
            uid = htmlfile.stem
            root = html.parse(str(htmlfile)).getroot()
            
            #Set codepoint data
            
            _stack = [root]
            while _stack:
                e = _stack.pop()
                if self.is_bold(lang_uid, e):
                    bold_codepoints.update(e.text_content())
                elif self.is_italic(lang_uid, e):
                    italic_codepoints.update(e.text_content())
                else:
                    _stack.extend(e)
            codepoints.update(root.text_content())                
            
            # Set the previous and next uids, using explicit data
            # if available, otherwise making a safe guess.
            # The safe guess relies on comparing uids, and will not
            # capture relationships such as the order of patimokha
            # rules.
            prev_uid = root.get('data-prev')
            next_uid = root.get('data-next')
            if not (prev_uid or next_uid):
                if i > 0:
                    prev_uid = files[i - 1].stem
                    if not self.uids_are_related(uid, prev_uid):
                        prev_uid = None
                if i + 1 < len(files):
                    next_uid = files[i + 1].stem
                    if not self.uids_are_related(uid, next_uid):
                        next_uid = None
            
            path = htmlfile.relative_to(sc.text_dir)
            author = self._get_author(root, lang_uid, uid)
            
            if uid == 'metadata':
                if author is None:
                    raise ValueError('Metadata file {} does not define author'.format(path))
                self.add_metadata(path, author, root)
                continue
            
            if author is None:
                metadata = self.get_metadata(path)
                if metadata:
                    author = metadata['author']
            
            if author is None:
                metadata = root.select_one('#metaarea')
                if metadata:
                    metadata_text = metadata.text_content()
                    m = regex.match(r'.{,80}\.', metadata_text)
                    if not m:
                        m = regex.match(r'.{,80}(?=\s)', metadata_text)
                    if m:
                        author = m[0]
                        
            if author is None:
                logger.warn('Could not determine author for {}/{}'.format(lang_uid, uid))
                author = ''
            
            name = self._get_name(root, lang_uid, uid)
            volpage = self._get_volpage(root, lang_uid, uid)
            embedded = self._get_embedded_uids(root, lang_uid, uid)
            
            fstat = htmlfile.stat()
            cdate = self.datestr(fstat.st_ctime)
            mdate = self.datestr(fstat.st_mtime)

            textinfo = TextInfo(uid=uid, lang=lang_uid, path=path, 
                                name=name, author=author,
                                volpage=volpage, prev_uid=prev_uid,
                                next_uid=next_uid,
                                cdate=cdate,
                                mdate=mdate,
                                file_uid=uid)
            self.add_text_info(lang_uid, uid, textinfo)

            for child in embedded:
                child.path = path
                child.author = author
                child.file_uid = uid
                self.add_text_info(lang_uid, child.uid, child)

            m = regex.match(r'(.*?)(\d+)-(\d+)$', uid)
            if m:
                range_textinfo = TextInfo(uid=uid+'#', 
                lang=lang_uid,
                path=path,
                name=name,
                author=author,
                volpage=volpage,
                file_uid=uid)
                start = int(m[2])
                end = int(m[3]) + 1
                for i in range(start, end):
                    iuid = m[1] + str(i)
                    if self.exists(iuid, lang_uid):
                        continue

                    self.add_text_info(lang_uid, iuid, range_textinfo)
        
         except Exception as e:
             print('An exception occured: {!s}'.format(htmlfile))
             raise
        
        self._codepoints[lang_uid] = {
            'normal': codepoints,
            'bold': bold_codepoints,
            'italic': italic_codepoints
        }
        
        del self._ppn

    def _on_n_files(self):
        return
    def _should_process_file(self, file, force):
        return True
    
    # Class Variables
    _build_lock = threading.Lock()
    _build_ready = threading.Event()
    _instance = None
    
    def _get_author(self, root, lang_uid, uid):
        e = root.select_one('meta[author]')
        if e:
            return e.attrib['author']
        
        e = root.select_one('meta[data-author]')
        if e:
            return e.attrib['data-author']
        e = root.select_one('meta[name=description]')
        
        if e:
            return e.attrib['content']
        
        e = root.select_one('#metaarea > .author')
        if e:
            return e.text
        return None

    
    def _get_name(self, root, lang_uid, uid):
        try:
            hgroup = root.select_one('.hgroup')
            h1 = hgroup.select_one('h1')
            return regex.sub(r'^\P{alpha}*', '', h1.text_content())
        except Exception as e:
            logger.warn('Could not determine name for {}/{}'.format(lang_uid, uid))
            return ''
    
    def _get_volpage(self, element, lang_uid, uid):
        if lang_uid == 'zh':
            e = element.next_in_order()
            while e is not None:
                if e.tag =='a' and e.select_one('.t, .t-linehead'):
                    break
                e = e.next_in_order()
            else:
                return
            return 'T {}'.format(e.attrib['id'])
        elif lang_uid == 'pi':
            ppn = self.get_palipagenumbinator()
            e = element.next_in_order()
            while e:
                if e.tag == 'a' and e.select_one('.ms'):
                    return ppn.get_pts_ref_from_pid(e.attrib['id'])
                e = e.next_in_order()

        return None
    
    def _get_embedded_uids(self, root, lang_uid, uid):
        # Generates possible uids that might be contained
        # within this text.
        out = []
        
        if '-pm' in uid:
            # This is a patimokkha text
            for h4 in root.select('h4'):
                a = h4.select_one('a[id]')
                if not a:
                    continue
                
                volpage = self._get_volpage(h4, lang_uid, uid)
                out.append(TextInfo(
                    uid='{}#{}'.format(uid, a.attrib['id']),
                    bookmark=a.attrib['id'],
                    name=None,
                    volpage=volpage))

        data_uid_seen = set()
        for e in root.select('[data-uid]'):
            if e.tag in {'h1','h2','h3','h4','h5','h6'}:
                heading = e.text_content()
                add = e.select_one('.add')
                if add and add.text_content() == heading:
                    heading = '[' + heading + ']'
            else:
                heading = None
            out.append(TextInfo(uid=e.get('data-uid'), name=heading, bookmark=e.get('id')))
            data_uid_seen.add(e)
        
        for e in root.select('.embeddedparallel'):
            if 'data-uid' in e.attrib:
                if e in data_uid_seen:
                    continue
                # Explicit
                new_uid = e.attrib['data-uid']
            else:
                # Implicit
                new_uid = '{}#{}'.format(uid, e.attrib['id'])
            out.append(TextInfo(
                uid=new_uid,
                bookmark = e.attrib['id']))

        sections = root.select('section.sutta')
        if len(sections) > 1:
            for section in sections:
                data_uid = section.attrib.get('data-uid')
                id = section.attrib.get('id')
                if data_uid:
                    out.append(TextInfo(
                        uid=data_uid,
                        bookmark=id))
        return out

    @classmethod
    def build_once(cls, force_build):
        if cls._build_lock.acquire(blocking=False):
            try:
                tim_base_filename = 'text_info_model_'
                textmd5 = text_dir_md5()
                timfile = sc.db_dir / (tim_base_filename + textmd5 + '.pickle')
                if not force_build and timfile.exists():
                    with timfile.open('rb') as f:
                        newtim = pickle.load(f)
                else:
                    newtim = TextInfoModel()
                    newtim.build()
                    for file in sc.db_dir.glob(tim_base_filename + '*'):
                        file.unlink()

                    with timfile.open('wb') as f:
                        pickle.dump(newtim, f)

                TextInfoModel._instance = newtim
                TextInfoModel._build_ready.set()
            finally:
                TextInfoModel._build_lock.release()

tim_manager = TIMManager()

tim = tim_manager.get
    
def build():
    tim_manager.load()

def ensure_up_to_date():
    tim_manager.load()

class PaliPageNumbinator:
    msbook_to_ptsbook_mapping = {
        'a': 'AN',
        'ap': 'Ap',
        'bu': 'Bv',
        'cn': 'Cnd',
        'cp': 'Cp',
        'd': 'DN',
        'dh': 'Dhp',
        'dhs': 'Ds',
        'dht': 'Dt',
        'it': 'It',
        'j': 'Ja',
        'kh': 'Kp',
        'kv': 'Kv',
        'm': 'MN',
        'mi': 'Mil',
        'mn': 'Mnd',
        'ne': 'Ne',
        'p': 'Pt',
        'pe': 'Pe',
        'ps': 'Ps',
        'pu': 'Pp',
        'pv': 'Pv',
        's': 'SN',
        'sn': 'Snp',
        'th1': 'Thag',
        'th2': 'Thig',
        'ud': 'Ud',
        'v': 'Vin',
        'vbh': 'Vb',
        'vv': 'Vv',
        'y': 'Ya'}

    default_attempts = [0,-1,-2,-3,-4,-5,-6,-7,-8,-9,-10,-11,-12,-13,-14,-15,1,2,3,4,5]
    def __init__(self):
        self.load()

    def load(self):
        from sc.csv_loader import table_reader

        reader = table_reader('pali_concord')

        mapping = {(msbook, int(msnum), edition): (book, page)
                for msbook, msnum, edition, book, page in reader}
        self.mapping = mapping

    def msbook_to_ptsbook(self, msbook):
        m = regex.match(r'\d+([A-Za-z]+(?:(?<=th)[12])?)', msbook)
        return self.msbook_to_ptsbook_mapping[m[1]]

    def get_pts_ref_from_pid(self, pid):
        m = regex.match(r'p_(\w+)_(\d+)', pid)

        msbook = m[1].lower()
        msnum = int(m[2])
        return self.get_pts_ref(msbook, msnum)
        
        
    def get_pts_ref(self, msbook, msnum, attempts=None):
        if not attempts:
            attempts = self.default_attempts
        for i in attempts:
            n = msnum + i
            if n < 1:
                continue
            key1 = (msbook, n, 'pts1')
            key2 = (msbook, n, 'pts2')
            key = None
            if key1 in self.mapping:
                key = key1
            elif key2 in self.mapping:
                key = key2
            if key:
                book, num = self.mapping[key]
                ptsbook = self.msbook_to_ptsbook(msbook)
                return self.format_book(ptsbook, book, num)

    def format_book(self, ptsbook, book, num):
        if not book:
            return '{} {}'.format(ptsbook, num)
        
        book = {'1':'i', '2':'ii', '3':'iii', '4':'iv', '5':'v', '6':'vi'
                }.get(book, book)
        return '{} {} {}'.format(ptsbook, book, num)
