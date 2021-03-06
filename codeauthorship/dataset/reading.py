import json

from collections import deque, Counter

import keyword
import builtins

from tqdm import tqdm

from codeauthorship.utils.logging import *


def get_reserved_words():
    reserved_words = []
    reserved_words += keyword.kwlist
    reserved_words += dir(builtins)
    return set(reserved_words)


def indexify(value2idx, lst):
    def func():
        for x in lst:
            if isinstance(x, (list, tuple)):
                yield [value2idx[xx] for xx in x]
            else:
                yield value2idx[x]
    return list(func())


class DatasetReader(object):
    def __init__(self, options):
        super(DatasetReader, self).__init__()
        self.options = options

        self.path_py = options.path_py
        self.path_c = options.path_c
        self.path_cpp = options.path_cpp

        self.dataset_py = PyDataset(options)
        self.dataset_c = CDataset(options)
        self.dataset_cpp = CPPDataset(options)

    def readfile(self, path):
        def func():
            with open(path) as f:
                for line in tqdm(f, desc='read', disable=not self.options.show_progress):
                    ex = json.loads(line)
                    if len(ex['tokens']) == 0:
                        continue
                    yield ex
        return list(func())

    def read(self):
        datasets = []

        if self.path_py is not None:
            records = self.readfile(self.path_py)
            datasets.append(self.dataset_py.build(records))
        if self.path_c is not None:
            records = self.readfile(self.path_c)
            datasets.append(self.dataset_c.build(records))
        if self.path_cpp is not None:
            records = self.readfile(self.path_cpp)
            datasets.append(self.dataset_cpp.build(records))

        datasets = ConsolidateDatasets().build(datasets)

        return datasets


class ConsolidateDatasets(object):
    def consolidate_mappings(self, mapping_lst):
        master_mapping = {}
        inverse_mapping_lst = []
        for x2y in mapping_lst:
            old2master = {}
            for x, y in x2y.items():
                if x not in inverse_mapping_lst:
                    master_mapping[x] = len(master_mapping)
                old2master[y] = master_mapping[x]
            inverse_mapping_lst.append(old2master)
        return master_mapping, inverse_mapping_lst

    def reindex(self, data, inverse_mapping):
        def fn(s):
            if isinstance(s, (list, tuple)):
                return [inverse_mapping[idx] for idx in s]
            else:
                return inverse_mapping[s]
        def queue(lst):
            q = deque(lst)
            while len(q) > 0:
                yield q.popleft()
        return [fn(s) for s in queue(data)]

    def build(self, datasets):
        """
        - Align labels between multiple datasets.
        - Creates one large dataset.
        """

        label2idx_lst = [x['metadata']['label2idx'] for x in datasets]
        label2idx_master, inverse_mapping_lst = self.consolidate_mappings(label2idx_lst)

        for dset, inverse_mapping in zip(datasets, inverse_mapping_lst):
            dset['secondary']['labels'] = self.reindex(dset['secondary']['labels'], inverse_mapping)
            dset['metadata']['label2idx'] = label2idx_master

        return datasets


class Dataset(object):
    language = None

    def __init__(self, options):
        super(Dataset, self).__init__()
        self.options = options

    def get_author_usage(self, records):
        author_usage = {}
        for rec in records:
            tokens = rec['tokens']
            label = rec['username']

            for x in tokens:
                author_usage.setdefault(x['val'], set()).add(label)
        return author_usage

    def build(self, records):
        logger = get_logger()

        include_type = set([x for x in self.options.include_type.split(',') if len(x)>0])
        exclude_type = set([x for x in self.options.exclude_type.split(',') if len(x)>0])
        reserved_words = get_reserved_words()

        dataset = {}

        # Primary data.
        seq = []

        # Secondary data. len(seq) == len(extra[key])
        extra = {}
        labels = []
        example_ids = []
        if self.options.extra_type:
            seq_types = []

        # Metadata. Information about the dataset.
        metadata = {}

        if self.options.author_usage is not None:
            author_usage = self.get_author_usage(records)
        
        for i, ex in tqdm(enumerate(records), desc='build', disable=not self.options.show_progress):
            tokens = ex['tokens']
            if len(exclude_type) > 0:
                token_types = [x['type'] for x in tokens]
                tokens = [tokens[i] for i in range(len(tokens))
                          if token_types[i] not in exclude_type]

            if len(include_type) > 0:
                token_types = [x['type'] for x in tokens]
                tokens = [tokens[i] for i in range(len(tokens))
                          if token_types[i] in include_type]

            if self.options.reserved:
                tokens = [x for x in tokens if x['val'] in reserved_words]
            if self.options.notreserved:
                tokens = [x for x in tokens if x['val'] not in reserved_words]
            if self.options.author_usage is not None:
                tokens = [x for x in tokens if len(author_usage[x['val']]) >= self.options.author_usage]

            seq.append([x['val'].lower() for x in tokens]) # NOTE: Case is ignored.
            labels.append(ex['username'])
            example_ids.append(ex['example_id'])

            if self.options.extra_type:
                seq_types.append([x['type'] for x in tokens])

        # Indexify if needed.
        labels, label2idx = self.build_label_vocab(labels)

        # Record everything.
        extra['example_ids'] = example_ids
        extra['labels'] = labels
        extra['lang'] = [self.language] * len(example_ids)

        if self.options.extra_type:
            extra['seq_types'] = seq_types

            types_set = Counter()
            for xs in seq_types:
                types_set.update(xs)
            logger.info('TYPES: {}'.format(types_set))

        metadata['label2idx'] = label2idx
        metadata['language'] = self.language

        dataset['primary'] = seq
        dataset['secondary'] = extra
        dataset['metadata'] = metadata

        return dataset

    def build_label_vocab(self, labels):
        label_vocab = set(labels)
        label2idx = {k: i for i, k in enumerate(sorted(label_vocab))}
        labels = indexify(label2idx, labels)
        return labels, label2idx


class PyDataset(Dataset):
    language = 'python'


class CDataset(Dataset):
    language = 'c'


class CPPDataset(Dataset):
    language = 'cpp'
        