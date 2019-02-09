#!/usr/bin/env python3

import os
from typing import Callable
from zipfile import ZipFile

import chardet
from entrypoint2 import entrypoint
from rarfile import RarFile

CHUNKSIZE = 30 * (1024**2)  # read/write in (up to) 30MiB chunks


def safepath(path: str, is_file=False):
    path = path.rstrip('/')
    nr = 1
    if is_file:
        spl = os.path.splitext(path)

    def makepath(path):
        if nr == 1:
            return path
        if is_file:
            return '_'.join([spl[0], str(nr)]) + spl[1]
        else:
            return '_'.join([path, str(nr)])

    while True:
        new = makepath(path)
        if not os.path.exists(new):
            break
        nr += 1
    return new


class Extractor(object):
    def __init__(self, archive_path: str):
        raise NotImplementedError()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        raise NotImplementedError()

    def list_files(self) -> {}:
        raise NotImplementedError()

    def extract(self,
                file_name: str,
                dest_path: str,
                write_hook: Callable[[bytes], bytes] = None):
        raise NotImplementedError()


class RarFileExtractor(Extractor):
    def __init__(self, archive_path: str):
        self.archive_path = archive_path
        self.rarfile = RarFile(self.archive_path)
        self.namelist = {i.filename for i in self.rarfile.infolist() if not i.isdir()}

    def __exit__(self, *args):
        self.rarfile.close()

    def list_files(self) -> {}:
        return self.namelist

    def extract(self,
                file_name: str,
                dest_path: str,
                write_hook: Callable[[bytes], bytes] = None):
        with self.rarfile.open(file_name) as rf, open(dest_path, 'wb') as out:
            while True:
                chunk = rf.read(CHUNKSIZE)
                if not chunk:
                    break
                out.write(write_hook(chunk) if write_hook else chunk)


class ZipFileExtractor(Extractor):
    def __init__(self, archive_path: str):
        self.archive_path = archive_path
        self.zipfile = ZipFile(self.archive_path, 'r')

        # encoding for filenames that aren't utf8
        # if chardet can't come up with anything, we assume it's shift_jis
        # TODO: this can fail for archives with few files/files with short names inside
        names_concat = b''.join([n.encode('cp437', 'ignore') for n in self.zipfile.namelist()])
        self.filename_encoding = chardet.detect(names_concat).get('encoding') or 'shift_jis'

        # maintain a mapping of converted filenames -> original borked names
        self.orig_names = {f.filename.encode('cp437', 'ignore').decode(self.filename_encoding, 'ignore'): f.filename
                           for f in self.zipfile.filelist 
                           if f.flag_bits & 0x800 == 0}

        self.namelist = {f.filename for f in self.zipfile.filelist if f.flag_bits & 0x800 != 0} | set(self.orig_names.keys())
        self.namelist = {n for n in self.namelist if not n.endswith('/')}  # filter out directories

    def __exit__(self, *args):
        self.zipfile.close()

    def list_files(self) -> {}:
        return self.namelist

    def extract(self,
                file_name: str,
                dest_path: str,
                write_hook: Callable[[bytes], bytes] = None):
        with self.zipfile.open(self.orig_names.get(file_name, file_name), 'r') as zf, open(dest_path, 'wb') as out:
            while True:
                chunk = zf.read(CHUNKSIZE)
                if not chunk:
                    break
                out.write(write_hook(chunk) if write_hook else chunk)


def truncate_utf8(string: str, max_len: int) -> str:
    utf8 = string.encode('utf-8')
    if len(utf8) <= max_len:
        return string
    return utf8[:max_len].decode('utf-8', 'ignore')


class DejizzFilter(object):
    def __init__(self, encode: str = 'utf-8', decode_default: str = 'shift_jis'):
        self.detected_encoding = None
        self.encode = encode
        self.decode_default = decode_default.lower()

    def dejizz(self, chunk: bytes):
        if self.detected_encoding is None:
            det = chardet.detect(chunk[:2048])
            self.detected_encoding = (det.get('encoding', None) or self.decode_default).lower()
        if self.detected_encoding == self.encode:
            return chunk
        return chunk.decode(self.detected_encoding, 'ignore').encode(self.encode)


@entrypoint
def main(source,
         dejizz_ext='txt,csv,tsv',
         no_dejizz=False,
         delete_archives=False,
         verbose=False,
         skip=False,
         overwrite=False,
         rename=False,
         filename_length=None):
    """Extract ZIP and RAR archives inside a directory recursively while trying to convert ZIP filenames to UTF-8 (using chardetect).

    source: Directory containing archives to be extracted (or a single archive file)
    dejizz_ext: File extensions to try to convert to UTF-8, case insensitive
    no_dejizz: Don't convert any file contents
    verbose: Log stuff that's happening
    skip: Automatically skip extracting files that already exist
    overwrite: Automatically overwrite existing files
    rename: Automatically rename extracted files if they already exist
    filename_length: max. length in bytes an extracted file's name (*not* path) should be truncated to (assumes utf-8)
    """

    extractors = {
        '.zip': ZipFileExtractor,
        '.rar': RarFileExtractor
    }

    dejizz_ext = {'.'+spl for spl in dejizz_ext.split(',')}

    def filelist(path):
        if os.path.isfile(path):
            return [os.path.split(path)]
        else:
            return [(root, f) for root, _, files in os.walk(path) for f in files]

    # TODO: error out if multiple specified
    conflict = None
    if overwrite: conflict = 'o'
    if rename: conflict = 'r'
    if skip: conflict = 's'

    files = filelist(source)
    for root, name in files:
        splitext = os.path.splitext(name)
        ext = splitext[1].lower()
        if ext not in extractors:
            continue
        with extractors[ext](os.path.join(root, name)) as extractor:
            single_root = False  # archive has a single top-level file or dir
            fl = extractor.list_files()
            if len(fl) == 0:  # empty (possibly corrupt) archive
                continue
            if len(fl) == 1:
                single_root = True
            else:
                # TODO: handle backslashes?
                single_root = len({f.split('/', 1)[0] for f in fl}) <= 1

            extract_root = root if single_root else safepath(os.path.join(root, splitext[0]))

            for f in fl:
                dest = os.path.join(extract_root, f)
                if filename_length:
                    dest = truncate_utf8(dest, int(filename_length))
                if verbose:
                    print(f'extracting {os.path.join(root, name)}:{f} -> {dest}')

                if os.path.exists(dest):
                    choice = conflict
                    if choice is None:
                        print(f'{dest} already exists.')
                    while choice not in ['o', 'r', 's']:
                        choice = input('[S]kip, [o]verwrite, or [r]ename: ')
                        if not choice:
                            choice = 's'
                    if choice == 's':
                        continue
                    elif choice == 'r':
                        dest = safepath(dest)

                try:
                    os.makedirs(os.path.split(dest)[0])
                except FileExistsError:
                    pass

                fext = os.path.splitext(f)[1]
                dj = fext in dejizz_ext
                if dj and not no_dejizz:
                    djfilter = DejizzFilter()
                extractor.extract(f, dest, write_hook=djfilter.dejizz if dj else None)
                if dj and verbose and djfilter.detected_encoding != 'utf-8':
                    print(f'converted from {djfilter.detected_encoding} to UTF-8: {f}')

            if delete_archives:
                del_arch = os.path.join(root, name)
                if verbose:
                    print(f'deleting {del_arch}')
                os.unlink(del_arch)
