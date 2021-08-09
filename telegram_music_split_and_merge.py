#!/usr/bin/env python
"""
This module contains scripts for re-spliting big audio books
"""

import logging
import re
import subprocess
from mutagen.easyid3 import EasyID3
from telegram_music_collection import TelegramMusicCollection

logging.basicConfig(format='%(asctime)s %(name)s %(funcName)s %(levelname)s %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def merge_mp3_parts(caption, parts):
    """
    args: caption - merged filename, *parts - list of posixpath to parts
    result: parts are merged and named as caption, located in dir of first part, id3 is transferes and corrected, part files are removed
    """
    cmd_template = 'ffmpeg -y -i "{input}" -acodec copy "{output}" -map_metadata 0:1'
    ffoutput = str( parts[0].parent / caption ) + '.mp3'
    ffinput = 'concat:' + '|'.join([str(p) for p in parts])
    
    cmd = cmd_template.format(input=ffinput, output=ffoutput)
    sp_result = subprocess.run(cmd, shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
    
    #raise error if return code is non-zero
    sp_result.check_returncode()

    correct_id3_remove_part(ffoutput)
    
    #removing parts
    [p.unlink() for p in parts]
    
    return ffoutput

def correct_id3_remove_part(mp3filename):
    """
    argument - mp3 file name
    result - id3 title cleaned of template
    returns None
    """
    audio = EasyID3(mp3filename)
    pattern = '\(часть \d+\)|\(глава \d+\)|\(глава \d+\-\d+\)|\(часть \d+, глава \d+\)'
    audio['title'] = re.sub(pattern, '', audio['title'][0], flags=re.IGNORECASE).strip()
    audio.save()

def mp3_bitrate(filename):
    """
    """
    cmd = 'file "%s"' % (str(filename))
    sp_result = subprocess.run(cmd, shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
    
    #raise error if return code is non-zero
    sp_result.check_returncode()
    
    output = sp_result.stdout.decode()
    
    return int(re.search(', (\d+) kbps,', output).group(1))

def split_mp3_parts(ppfile):
    """
    arguments: PosixPath filename of mp3 file
    returns list of PosixPath filenames of mp3 parts
    splits a file into number of parts less then 40 Mb each
    """
    segment_size_kb = 39000
    bitrate_kbit = mp3_bitrate(ppfile)
    segment_time = int( segment_size_kb * 8 / bitrate_kbit )

    print(str(ppfile) + ' bitrate: ' + str(bitrate_kbit) + ' segment time: ' + str(segment_time))

    ffoutput = str(ppfile).rstrip('.mp3') + ' (Часть %01d).mp3'    

    cmd_template = 'ffmpeg -i "{input_file}" -f segment -segment_time {duration} -c copy "{output_filename_template}"'
    cmd = cmd_template.format(input_file=str(ppfile), duration=segment_time, output_filename_template=ffoutput)
    
    sp_result = subprocess.run(cmd, shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
    
    #raise error if return code is non-zero
    sp_result.check_returncode()
    
    #removing big file
    filename.unlink()

    #parsing output
    output = sp_result.stdout.decode()
    new_paths = [ Path(re.search("Opening '([^']+)' for writing", line).group(1)) for line in output.splitlines() if re.search("Opening '[^']+' for writing", line)]

    #adding part suffix to id3 title
    f = lambda p: re.search('( \(Часть \d+\))', str(p)).group(1)
    [correct_id3_add_to_title(p, f(p)) for p in new_paths]

    return new_paths


def correct_id3_add_to_title(mp3filename, suffix):
    """
    arguments: mp3filename - posixPath of mp3 file, suffix - str to be added to title
    returns None
    """
    audio = EasyID3(mp3filename)
    audio['title'] = audio['title'][0] + ' ' +  suffix
    audio.save()


def collect_parts(collection):
    """
    collect_parts searches in mds_dict for pattern, detecting parts. It takes only books with at least one part is larger than 40 Mb
    returns collection  {caption:[path_to_part1, path_to_part2, ..]}
    """
    pattern = '\(часть \d+\)|\(глава \d+\)|\(глава \d+\-\d+\)|\(часть \d+, глава \d+\)'
    size_limit_bytes = 40000000
    captions_with_parts = [x for x in collection.mds_dict.keys() if re.search(pattern, x, flags=re.IGNORECASE)]
    parts = {}
    for caption_with_part in captions_with_parts:
        caption_without_part = re.sub(pattern, '', caption_with_part, flags=re.IGNORECASE).strip()
        if caption_without_part in parts:
            path = collection.mds_dict[caption_with_part]['path']
            parts[caption_without_part].append(path)
        else:
            path = collection.mds_dict[caption_with_part]['path']
            parts[caption_without_part] = [path]
    return {k : sorted(parts[k]) for k in parts.keys() if any([p.stat().st_size > size_limit_bytes for p in parts[k]])}

       
def collect_big_mp3(collection):
    """
    returns a list of PosixPath filenames which size exceed limit
    """
    size_limit_bytes = 40000000
    return [collection.mds_dict[caption]['path'] for caption in collection.mds_dict.keys() if collection.mds_dict[caption]['path'].stat().st_size > size_limit_bytes]

def prepare4telegram(collection):
    """
    Merging titles divided into parts larger then 40 mb
    Splitting files larger then limit
    reindex
    """
    parts = collect_parts(collection)
    logger.info('Merging parts: ' + str(parts))
    [merge_mp3_parts(cap, parts[cap]) for cap in parts.keys()]
    logger.info('Reindexing...')
    collection.reindex()
    big_files = collect_big_mp3(collection)
    logger.info('Splitting big files: ' + str(big_files))
    [split_mp3_parts(f) for f in big_files]
    logger.info('Reindexing...')
    collection.reindex()

    

def main():
    collection = TelegramMusicCollection('audio/')       
    prepare4telegram(collection)

        
if __name__ == '__main__':
    main()

