"""
header:
,year,round,username,task,solution,file,full_path,flines
"""

import argparse
import os
import json

# data_reader.py
import csv
import io
import sys
import tempfile

import clang.cindex


csv.field_size_limit(sys.maxsize)

def file_getter(filename):
    for fn in filename.split(','):
        fn = os.path.expanduser(fn)
        def func(f):
            for line in f:
                yield line.replace('\0', '')
        print('reading = {}'.format(fn))
        with open(fn, 'r') as f:
            reader = csv.DictReader(list(func(f)))
        for x in reader:
            yield x


def convert_file(path_in, path_out):
    reader = file_getter(path_in)

    example_id = 0

    failed = 0
    skipped = 0
    success = 0

    with open(path_out, 'w') as f:
        for i, row in enumerate(reader):
            year = row['year']
            username = row['username']

            # Only python for now.
            if not row['file'].endswith('.c'):
                # print('Skipping {}'.format(row['file']))
                skipped += 1
                continue

            # Write code to temporary file.
            tempf = tempfile.NamedTemporaryFile(mode='w')
            tempf.write(row['flines'])
            tempf.flush()
            tempfname = tempf.name

            # Tokenize code.
            try:
                idx = clang.cindex.Index.create()
                s = open(tempfname).read()
                tu = idx.parse('tmp.cpp', args=['-std=c++11'],  
                                unsaved_files=[('tmp.cpp', s)],  options=0)

                tokens = []
                for t in tu.get_tokens(extent=tu.cursor.extent):
                    token = {}
                    token['val'] = t.spelling
                    tokens.append(token)

                ex = {}
                ex['year'] = year
                ex['username'] = username
                ex['tokens'] = tokens
                ex['example_id'] = str(example_id)

                f.write('{}\n'.format(json.dumps(ex)))
                example_id += 1
                success += 1
            except:
                failed += 1

            # Cleanup.
            tempf.close()

    print('skipped', skipped)
    print('failed', failed)
    print('success', success)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--path_in', default='~/data/obfuscated_c.csv', type=str)
    parser.add_argument('--path_out', default='~/Downloads/gcj-c-obfuscate.jsonl', type=str)
    parser.add_argument('--preset', default='none', choices=('tigress',))
    options = parser.parse_args()

    if options.preset == 'tigress':
        options.path_in = '~/data/obfuscated_c.csv'
        options.path_out = '~/Downloads/gcj-c-obfuscate.jsonl'

    options.path_out = os.path.expanduser(options.path_out)

    convert_file(options.path_in, options.path_out)
