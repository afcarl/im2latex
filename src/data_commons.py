#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
    Copyright 2017 Sumeet S Singh

    This file is part of im2latex solution by Sumeet S Singh.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the Affero GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    Affero GNU General Public License for more details.

    You should have received a copy of the Affero GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

Created on Mon Jul 17 19:58:00 2017

@author: Sumeet S Singh
"""
import os
import logging
# from six.moves import cPickle as pickle
import dill as pickle
import numpy as np
import h5py
from pprint import pprint, pformat

dict_id2word = None
i2w_ufunc = None
logger = logging

def setLogLevel(logger_, level):
    logging_levels = (logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG)
    logger_.setLevel(logging_levels[level - 1])

def makeFormatter():
    return logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

def makeLogger(logging_level=3, name='default'):
    logger_ = logging.Logger(name)
    ch = logging.StreamHandler()
    ch.setFormatter(makeFormatter())
    logger_.addHandler(ch)
    setLogLevel(logger_, logging_level)
    return logger_

def initialize(data_dir, params):
    global i2w_ufunc, dict_id2word
    # if logger is None:
    #     logger = params.logger
    if i2w_ufunc is None:
        dict_id2word = load(data_dir, 'dict_id2word.pkl')
        K = len(dict_id2word.keys())
        if params.CTCBlankTokenID is not None:
            assert params.CTCBlankTokenID == K
        dict_id2word[K] = u'<>' ## CTC Blank Token
        dict_id2word[-1] = u'<-1>' ## Catch -1s that beamsearch emits after EOS.
        def i2w(id):
            try:
                return dict_id2word[id]
            except KeyError as e:
                logger.critical('i2w: KeyError: %s', e)
                return '<%d>'%(id,)
        i2w_ufunc = np.frompyfunc(i2w, 1, 1)
    return i2w_ufunc

def seq2str(arr, label, separator=None):
    """
    Converts a matrix of id-sequences - shaped (B,T) - to an array of strings shaped (B,).
    Uses the supplied dict_id2word to map ids to words. The dictionary must map dtype of
    <arr> to string.
    """
    assert i2w_ufunc is not None, "i2w_ufunc is None. Please call initialize first in order to setup i2w_ufunc."
    str_arr = i2w_ufunc(arr) # (B, T)
    if separator is None:
        func1d = lambda vec: label + u" " + u"".join(vec)
    else:
        func1d = lambda vec: label + u" " + unicode(separator).join(vec)
    return [func1d(vec) for vec in str_arr]

def join(*paths):
    return os.path.join(*paths)

def dump(ar, *paths):
    path = join(*paths)
    assert not os.path.exists(path), 'A file already exists at path %s'%path
    with open(path, 'wb') as f:
        pickle.dump(ar, f, pickle.HIGHEST_PROTOCOL)

def load(*paths):
    with open(join(*paths), 'rb') as f:
        return pickle.load(f)

class Storer(object):
    def __init__(self, args, prefix, step):
        self._path = os.path.join(args.storedir, '%s_%d.h5'%(prefix, step))
        self._h5 = h5py.File(self._path, "w", swmr=False)

    def __enter__(self):
        return self

    def __exit__(self, *err):
        self.close()

    def flush(self):
        self._h5.flush()

    def close(self):
        self._h5.close()

    def write(self, key, ar, dtype=None, batch_axis=0, doUnwrap=True):
        if (isinstance(ar, tuple) or isinstance(ar, list)) and doUnwrap:
            return self._write(key, ar, dtype, batch_axis)
        else:
            return self._write(key, [ar], dtype, batch_axis)

    def _write(self, key, np_ar_list, dtype, batch_axis):
        """
        Stacks the tensors in the list along axis=batch_axis and writes them to disk.
        Dimensions along axis=batch_axis are summed up. Other dimensions are padded to the maximum size
        with a dtype-suitable value (np.nan for float, -2 for integer)
        """
        ## Assuming all arrays have same rank, find the max dims
        shapes = [ar.shape for ar in np_ar_list]
        dims = zip(*shapes)
        max_shape = [max(d) for d in dims]
        ## We'll concatenate all arrays along axis=batch_axis
        max_shape[batch_axis] = sum(dims[batch_axis])
        if dtype == np.unicode_:
            dt = h5py.special_dtype(vlen=unicode)
            dataset = self._h5.create_dataset(key, max_shape, dtype=dt)
        else:
            dataset = self._h5.create_dataset(key, max_shape, dtype=dtype, fillvalue=-2 if np.issubdtype(dtype, np.integer) else np.nan)

        def make_slice(row, shape, batch_axis):
            """
            Create a slice to place shape into the receiving dataset starting at rownum along axis=batch_axis,
            and starting at 0 along all other axes
            """
            s = [slice(0,d) for d in shape]
            s[batch_axis] = slice(row, row+shape[batch_axis])
            return tuple(s), row+shape[batch_axis]

        row = 0
        for ar in np_ar_list:
            s, row = make_slice(row, ar.shape, batch_axis)
            # logger.info('row=%d, slice=%s', row, s)
            dataset[s] = ar

def makeLogfileName(logdir, name):
    prefix, ext = os.path.splitext(os.path.basename(name))
    filenames = os.listdir(logdir)
    if not (prefix + ext) in filenames:
        return os.path.join(logdir, prefix + ext)
    else:
        for i in xrange(2,101):
            if '%s_%d%s'%(prefix,i,ext) not in filenames:
                return os.path.join(logdir, '%s_%d%s'%(prefix,i,ext))

    raise Exception('logfile number limit (100) reached.')

def exists(*paths):
    return os.path.exists(os.path.join(*paths))

def makeLogDir(root, dirname):
    dirpath = makeLogfileName(root, dirname)
    os.makedirs(dirpath)
    return dirpath
