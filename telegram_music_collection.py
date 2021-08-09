#!/usr/bin/env python
"""
Class abcollection provides audio books collection interface, made specialy for mds collection format.
implements search in captions 
merge files
split files
prepare for telegram bot usage 
"""

import logging
from pathlib import Path
from difflib import get_close_matches
import re
import random
from hashlib import md5
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
from base64 import b64encode

logging.basicConfig(format='%(asctime)s %(name)s %(funcName)s %(levelname)s %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def get_author(filename):
    """extracts author from filename 'Author - title'"""
    separator = ' - '
    if separator in filename:
        return filename.split(sep=separator)[0]
    else:
        return ''

def get_title(filename):
    """extracts title from filename 'Author - title'"""
    separator = ' - '
    if separator in filename:
        return filename.split(sep=separator)[1]
    else:
        return filename



class TelegramMusicCollection:
    def __init__(self, path, id3based = False):
        """
        self.mds_basedir - Path object refering to base directory of mds collection
        self.mds_dict - a python dict containing information about files in mds collection
        """
        self.mds_basedir = Path(path)
        if (self.mds_basedir.exists() and self.mds_basedir.is_dir()):
            self.mds_dict = self.make_index(self.mds_basedir, id3based)
            logger.info('New music collection instance created for tracks in %s' % (path)) 
        else:
            raise FileNotFoundError('%s is not valid directory' % path)

    def make_index(self, path, id3based = False):
        """
        args: path - Path object of base directory
        returns dictionary with files in path directory and subdirectories
        """
        logger.info('Building index for collection in %s', str(path))
        if (id3based):
            index_dict = {}
            for p in path.glob('**/*.mp3'):
                file_id3 = EasyID3(p)
                author = file_id3['artist'][0] if 'artist' in file_id3.keys() and file_id3['artist'] else ""
                album = file_id3['album'][0] if 'album' in file_id3.keys() and file_id3['album'] else ""
                title = file_id3['title'][0] if 'title' in file_id3.keys() and file_id3['title'] else ""
                index_dict[author + ' - '*int(bool(author)) + title] = {'path' : p, 
                                                                'author': author,
                                                                'title': title,
                                                                'album': album,
                                                                'filename': p.name, 
                                                                'length': str(int(MP3(str(p)).info.length)), 
                                                                'hash': md5(bytes(re.sub('\s+', ' ', p.name.strip('.mp3')), 'utf-8')).hexdigest()[:10]}
            return index_dict

        return {re.sub('\s+', ' ', p.name.strip('.mp3')) : {'path' : p, 
                                                            'author' : get_author(p.name.strip('.mp3')) , 
                                                            'title' : get_title(p.name.strip('.mp3')), 
                                                            'filename': p.name, 
                                                            'length': str(int(MP3(str(p)).info.length)), 
                                                            'hash': md5(bytes(re.sub('\s+', ' ', p.name.strip('.mp3')), 'utf-8')).hexdigest()[:10]} for p in path.glob('**/*.mp3')}

    
    def reindex(self):
        """
        makes new mds_dict for mds_base_dir
        """        
        self.mds_dict = self.make_index(self.mds_basedir)

    def random(self):
        """
        returns caption: {path, author, title}
        returns random title 
        """
        pattern = '\(часть \d+\)|\(глава \d+\)|\(глава \d+\-\d+\)|\(часть \d+, глава \d+\)'
        return random.choice([caption for caption in self.mds_dict.keys() if not re.search(pattern, caption, flags=re.IGNORECASE)])



    def dump(self):
        #logger.info([x for x in self.mds_dict.keys() if ('часть' in x.lower()) or ('глава' in x.lower())])
        print(self.mds_dict)
        logger.info(self.mds_dict)

    def path(self, caption):
        """
        returns path for given caption
        """
        if caption in self.mds_dict.keys():
            return self.mds_dict[caption]['path']
        else:
            return None

    def filename(self, caption):
        """
        returns path for given caption
        """
        if caption in self.mds_dict.keys():
            return self.mds_dict[caption]['filename']
        else:
            return None


    def exists(self, caption):
        if caption in self.mds_dict.keys():
            return True
        else:
            return False

    def get_by_hash(self, hash):
        """
        returns caption by singe argument - hash
        """
        try:
            return [caption for caption in self.mds_dict.keys() if self.mds_dict[caption]['hash'] == hash][0]
        except:
            return None
   
    def hash(self, caption):
        """
        returns hash for given caption
        """
        if caption in self.mds_dict.keys():
            return self.mds_dict[caption]['hash']
        else:
            return None

    def author(self, caption):
        """
        returns author for given caption
        """
        if caption in self.mds_dict.keys():
            return self.mds_dict[caption]['author']
        else:
            return None

    def title(self, caption):
        """
        returns title for given caption
        """
        if caption in self.mds_dict.keys():
            return self.mds_dict[caption]['title']
        else:
            return None

    def length(self, caption):
        """
        returns length for given caption
        """
        if caption in self.mds_dict.keys():
            return self.mds_dict[caption]['length']
        else:
            return None


    def search(self, search_string):
        # skip search on empty and short strings
        if len(search_string) < 3:
            return []

        # cut search string if it's too large
        if len(search_string) > 100:
            search_string = search_string[:100]

        return list(sorted(set(self.search_exact(search_string) + self.search_diff_author(search_string) + self.search_diff_title(search_string) + self.search_diff_caption(search_string))))

    def search_diff_caption(self, search_string):
        return sorted(get_close_matches(search_string, self.mds_dict.keys()))

    def search_diff_title(self, search_string):
        junk_pattern = '\(часть \d+\)|\(глава \d+\)|\(глава \d+\-\d+\)|\(часть \d+, глава \d+\)'
        titles = get_close_matches(search_string, [v['title'] for v in self.mds_dict.values()])
        return sorted([caption for caption in self.mds_dict.keys() if self.mds_dict[caption]['title'] in titles ])

    def search_diff_author(self, search_string):
        authors = get_close_matches(search_string, [v['author'] for v in self.mds_dict.values()])
        return sorted([caption for caption in self.mds_dict.keys() if self.mds_dict[caption]['author'] in authors ])

    def search_exact(self, search_string):
        return sorted([caption for caption in self.mds_dict.keys() if search_string.lower() in caption.lower()])

        

def main():
    mds = TelegramMusicCollection('bots/content/music/', id3based=True)
    mds.dump()
    s = ''
    while s:
        s = input('Enter search string: ')
        print(mds.search(s))
        random = mds.random()
        duration = mds.length(random)
        print(random + ' ' + duration)


        
if __name__ == '__main__':
    main()

