#!/usr/bin/env python3

import os
import sys
import shutil
import subprocess
import zipfile

import chardet
from entrypoint2 import entrypoint


def safepath(path):
    nr = 1
    while os.path.exists(path if nr == 1 else '_'.join([path, str(nr)])):
        nr += 1
    if nr != 1:
        return '_'.join([path, str(nr)])
    return path


def mktmp(path):
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass
    try:
        os.mkdir(path)
    except FileExistsError:
        pass


@entrypoint
def main(source_dir, tmp_dir):
    """Extract ZIP and RAR archives inside a directory recursively while trying to convert ZIP filenames to UTF-8 (using chardetect).
    WARING: Successfully extracted archives are *deleted* afterwards; if you want to keep them, make a copy first.
    source_dir: Directory containing archives to be extracted
    tmp_dir: Directory to use for temporary files (will be created, should not exist beforehand)"""

    if not shutil.which('unrar') or not shutil.which('unzip'):
        print("This script relies on the 'unrar' and 'unzip' utilities. Please make sure they are properly installed and inside your PATH.", file=sys.stderr)
        return 1

    for root, _, files in os.walk(source_dir):
        for archive in files:
            if archive.lower().endswith('.rar'):
                mktmp(tmp_dir)
                src = os.path.join(root, archive)
                print(f'Extracting RAR: {src}')
                # straightforward unrar
                try:
                    subprocess.check_call(['unrar', 'x', src, tmp_dir], stdout=subprocess.DEVNULL)
                except:
                    print('Rar couldn\'t be extracted, may be corrupt or not supported by unrar', file=sys.stderr)
            elif archive.lower().endswith('.zip'):
                mktmp(tmp_dir)
                src = os.path.join(root, archive)
                print(f'Extracting ZIP: {src}')
                try:
                    with zipfile.ZipFile(src, 'r') as zip:
                        # ZipFile decodes EVERYTHING that's not utf-8 as cp437
                        # so you can get back the original bytes by encoding by that...
                        det = chardet.detect(b''.join([n.encode('cp437', 'ignore') for n in zip.namelist()]))
                        enc = det['encoding'] if det['encoding'] else 'shift_jis'  # try shit-jizz in case chardetect has no idea
                        converted = 0
                        for info in zip.filelist:
                            filename = info.filename
                            if info.flag_bits & 0x800 == 0:  # 0x800 indicated utf-8 filenames
                                converted += 1
                                filename = info.filename.encode('cp437', 'ignore').decode(enc, 'ignore')
                            with zip.open(info, 'r') as zipped_file:
                                outpath = os.path.join(tmp_dir, filename)
                                outdir = os.path.dirname(outpath)
                                if not os.path.exists(outdir):
                                    os.makedirs(outdir)
                                if os.path.isdir(outpath):
                                    continue
                                with open(outpath, 'wb') as out:
                                    while True:
                                        chunk = zipped_file.read(1024 ** 2)
                                        if not chunk:
                                            break
                                        out.write(chunk)
                        if converted > 0:
                            print(f'Converted {converted} filenames from {enc} to UTF-8')
                except zipfile.BadZipFile:
                    print('ZIP couldn\'t be extracted, may be corrupt', file=sys.stderr)
            else:
                continue

            # move files from tmp dir to destination
            extr_files = os.listdir(tmp_dir)
            if len(extr_files) == 1:
                dest = safepath(os.path.join(root, extr_files[0]))
                os.rename(os.path.join(tmp_dir, extr_files[0]), dest)
            elif len(extr_files) > 1:
                dest = safepath(os.path.join(root, os.path.splitext(archive)[0]))
                os.rename(tmp_dir, dest)
            else:
                continue

            # remove original archive
            try:
                rm = os.path.join(root, archive)
                os.unlink(rm)
                print(f'Deleted {rm}')
            except:
                pass

        try:
            shutil.rmtree(tmp_dir)
            print(f'Deleted {tmp_dir}')
        except:
            pass
