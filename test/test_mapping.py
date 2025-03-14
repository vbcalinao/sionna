#
# SPDX-FileCopyrightText: Copyright (c) 2021-2022 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
try:
    import sionna
except ImportError as e:
    import sys
    sys.path.append("../")
import pytest
import unittest
import numpy as np
import tensorflow as tf
gpus = tf.config.list_physical_devices('GPU')
print('Number of GPUs available :', len(gpus))
if gpus:
    gpu_num = 0 # Number of the GPU to be used
    try:
        tf.config.set_visible_devices(gpus[gpu_num], 'GPU')
        print('Only GPU number', gpu_num, 'used.')
        tf.config.experimental.set_memory_growth(gpus[gpu_num], True)
    except RuntimeError as e:
        print(e)
from scipy.special import logsumexp
from sionna.mapping import Constellation, Mapper, Demapper, DemapperWithPrior
from sionna.mapping import SymbolDemapperWithPrior, SymbolDemapper
from sionna.utils import BinarySource
from sionna.channel import AWGN

class TestMapper(unittest.TestCase):

    def test_dimensions(self):
        num_bits_per_symbol = 4
        batch_size = 100
        num_symbols = 100
        binary_source = BinarySource()
        m = Mapper("qam", num_bits_per_symbol)

        x = m(binary_source([batch_size, num_symbols*num_bits_per_symbol]))
        self.assertEqual(x.shape, [batch_size, num_symbols])

        x = m(binary_source([batch_size,2,3,num_symbols*num_bits_per_symbol]))
        self.assertEqual(x.shape, [batch_size,2,3,num_symbols])

        x = m(binary_source([batch_size,2,3,num_symbols*num_bits_per_symbol]))
        self.assertEqual(x.shape, [batch_size,2,3,num_symbols])

        with self.assertRaises(tf.errors.InvalidArgumentError):
            x = m(binary_source([batch_size, num_symbols*num_bits_per_symbol-1]))

        with self.assertRaises(tf.errors.InvalidArgumentError):
            x = m(binary_source([num_symbols*num_bits_per_symbol]))

    def test_mappings(self):
        num_bits_per_symbol = 8
        b = np.zeros([2**num_bits_per_symbol, num_bits_per_symbol])
        for i in range(0, 2**num_bits_per_symbol):
            b[i] = np.array(list(np.binary_repr(i,num_bits_per_symbol)), dtype=np.int16)
        m = Mapper("qam", num_bits_per_symbol)
        x = m(b)
        for i, s in enumerate(x.numpy()):
            self.assertEqual(s, m.constellation.points[i])

    def test_graph_mode(self):
        binary_source = BinarySource()
        mapper = Mapper("qam", 4)
        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            return mapper(b)
        self.assertEqual(run(100).shape, [100, 3, 100])
        self.assertEqual(run(400).shape, [400, 3, 100])

    def test_graph_mode_jit(self):
        binary_source = BinarySource()
        mapper = Mapper("qam", 4)
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            return mapper(b)
        self.assertEqual(run(100).shape, [100, 3, 100])
        self.assertEqual(run(400).shape, [400, 3, 100])

    def test_model_mode(self):
        binary_source = BinarySource()
        constellation = Constellation("qam", 4)
        inputs = tf.keras.Input(shape=(3, 400), dtype=tf.float32)
        x = Mapper(constellation=constellation)(inputs)
        model = tf.keras.Model(inputs=inputs, outputs=x)
        model.compile()
        self.assertEqual(model(binary_source([100, 3, 400])).shape, [100, 3, 100])
        self.assertEqual(model(binary_source([400, 3, 400])).shape, [400, 3, 100])

class TestDemapper(unittest.TestCase):
    def test_assert_demapping_method(self):
        c = Constellation("qam", 6)
        with self.assertRaises(AssertionError):
            Demapper("asdfiu", c)

    def test_assert_non_broadcastable_dimensions(self):
        c = Constellation("custom", 4)
        m = Mapper(constellation=c)
        d = Demapper("app", constellation=c)
        b = tf.random.uniform([100, 50, 200], minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([100, 50])
            llr = d([x, no])
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([100, 1])
            llr = d([x, no])


    def test_output_dimensions1(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            c = Constellation("custom", num_bits_per_symbol)
            m = Mapper(constellation=c)
            d = Demapper("app", constellation=c)
            batch_size = 99
            dim1 = 10
            dim2 = 12
            b = tf.random.uniform([batch_size, dim1, dim2*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            llr = d([x, 1.])
            self.assertEqual(llr.shape, [batch_size, dim1, dim2*num_bits_per_symbol])

    def test_output_dimensions2(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            c = Constellation("custom", num_bits_per_symbol)
            m = Mapper(constellation=c)
            d = Demapper("app", constellation=c)
            batch_size = 99
            b = tf.random.uniform([batch_size, num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            llr = d([x, 1.])
            self.assertEqual(llr.shape, [batch_size, num_bits_per_symbol])

    def test_no_inputs(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            c = Constellation("custom", num_bits_per_symbol)
            m = Mapper(constellation=c)
            d = Demapper("app", constellation=c)
            b = tf.random.uniform([100, 10, 50*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            No = np.ones_like(x, dtype=np.float32)
            llr = d([x, No])
            self.assertEqual(llr.shape, [100, 10, 50*num_bits_per_symbol])

            No = np.ones_like(x, dtype=np.float32)
            llr = d([x, No])
            self.assertEqual(llr.shape, [100, 10, 50*num_bits_per_symbol])

            with self.assertRaises(tf.errors.InvalidArgumentError):
                d = Demapper("app", constellation=c)
                No = tf.constant(np.ones(x.shape[:-1]), dtype=tf.float32)
                llr = d([x, No])

    def test_per_symbol_noise_variance(self):
        "Test LLRs with per symbol noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        m = Mapper("qam", num_bits_per_symbol)
        d_app = Demapper("app", "qam", num_bits_per_symbol)
        d_maxlog = Demapper("maxlog", "qam", num_bits_per_symbol)
        b = tf.random.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = tf.random.uniform(x.shape, minval=0.01, maxval=100, dtype=np.float32)
        llr_app = d_app([x, No])
        llr_maxlog = d_maxlog([x, No])
        p = d_app.constellation.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - p)**2
                exp = -dist/No[l,i]

                llrnp_app = logsumexp(np.take(exp, d_app._c1),axis=0) - logsumexp(np.take(exp, d_app._c0),axis=0)
                llrtarget_app = llr_app[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_app, llrtarget_app, atol=1e-5))

                llrnp_maxlog = np.max(np.take(exp, d_maxlog._c1),axis=0) - np.max(np.take(exp, d_maxlog._c0),axis=0)
                llrtarget_maxlog = llr_maxlog[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_maxlog, llrtarget_maxlog, atol=1e-5))

    def test_broadcastable_noise_variance(self):
        "Test LLRs with broadcastable noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        m = Mapper("qam", num_bits_per_symbol)
        d_app = Demapper("app", "qam", num_bits_per_symbol)
        d_maxlog = Demapper("maxlog", "qam", num_bits_per_symbol)
        b = tf.random.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = tf.random.uniform([1, 10], minval=0.01, maxval=100, dtype=np.float32)
        llr_app = d_app([x, No])
        llr_maxlog = d_maxlog([x, No])
        p = m.constellation.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - p)**2
                exp = -dist/No[0,i]

                llrnp_app = logsumexp(np.take(exp, d_app._c1),axis=0) - logsumexp(np.take(exp, d_app._c0),axis=0)
                llrtarget_app = llr_app[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_app, llrtarget_app, atol=1e-5))

                llrnp_maxlog = np.max(np.take(exp, d_maxlog._c1),axis=0) - np.max(np.take(exp, d_maxlog._c0),axis=0)
                llrtarget_maxlog = llr_maxlog[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_maxlog, llrtarget_maxlog, atol=1e-5))

    def test_graph_mode(self):
        num_bits_per_symbol = 4
        binary_source = BinarySource()
        mapper = Mapper("qam", num_bits_per_symbol)
        awgn = AWGN()
        demapper = Demapper("app", "qam", num_bits_per_symbol)
        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = tf.random.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=np.float32)
            y = awgn([x, no])
            return demapper([y, no])
        self.assertEqual(run(100).shape, [100, 3, 400])
        self.assertEqual(run(400).shape, [400, 3, 400])

    def test_graph_mode_jit(self):
        binary_source = BinarySource()
        constellation = Constellation("qam", 4)
        mapper = Mapper(constellation=constellation)
        awgn = AWGN()
        demapper = Demapper("app", constellation=constellation)
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = tf.random.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=np.float32)
            y = awgn([x, no])
            return demapper([y, no])
        self.assertEqual(run(100).shape, [100, 3, 400])
        self.assertEqual(run(400).shape, [400, 3, 400])

    def test_model_mode(self):
        binary_source = BinarySource()
        constellation = Constellation("qam", 4)
        mapper = Mapper(constellation=constellation)
        awgn = AWGN()
        demapper = Demapper("app", constellation=constellation)
        b = tf.keras.Input(shape=(3, 400), dtype=tf.float32)
        no = tf.keras.Input(shape=(3, 100), dtype=tf.float32)
        x = mapper(b)
        y = awgn([x, no])
        llr = demapper([y, no])
        model = tf.keras.Model(inputs=[b, no], outputs=llr)
        model.compile()
        in1 = binary_source([100, 3, 400])
        in2 = tf.random.uniform([100, 3, 100], minval=0.01, maxval=100, dtype=np.float32)
        self.assertEqual(model([in1, in2]).shape, [100, 3, 400])
        in1 = binary_source([400, 3, 400])
        in2 = tf.random.uniform([400, 3, 100], minval=0.01, maxval=100, dtype=np.float32)
        self.assertEqual(model([in1, in2]).shape, [400, 3, 400])

class TestDemapperWithPrior(unittest.TestCase):
    def test_assert_demapping_method(self):
        c = Constellation("qam", 6)
        with self.assertRaises(AssertionError):
            DemapperWithPrior("asdfiu", c)

    def test_assert_non_broadcastable_dimensions(self):
        c = Constellation("custom", 4)
        m = Mapper(constellation=c)
        d = DemapperWithPrior("app", constellation=c)
        b = tf.random.uniform([16, 50, 200], minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        # Noise
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([16, 50])
            p = tf.random.uniform([4])
            llr = d([x, p, no])
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([16, 1])
            p = tf.random.uniform([4])
            llr = d([x, p, no])
        # prior
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = tf.random.uniform([16, 50, 4])
            llr = d([x, p, 1.0])
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = tf.random.uniform([16, 50, 200])
            llr = d([x, p, 1.0])
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = tf.random.uniform([16, 1])
            llr = d([x, p, 1.0])

    def test_output_dimensions1(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            c = Constellation("custom", num_bits_per_symbol)
            m = Mapper(constellation=c)
            d = DemapperWithPrior("app", constellation=c)
            batch_size = 99
            dim1 = 10
            dim2 = 12
            b = tf.random.uniform([batch_size, dim1, dim2*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            p = tf.random.uniform([num_bits_per_symbol])
            llr = d([x, p, 1.])
            self.assertEqual(llr.shape, [batch_size, dim1, dim2*num_bits_per_symbol])

    def test_output_dimensions2(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            c = Constellation("custom", num_bits_per_symbol)
            m = Mapper(constellation=c)
            d = DemapperWithPrior("app", constellation=c)
            batch_size = 99
            b = tf.random.uniform([batch_size, num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            p = tf.random.uniform([num_bits_per_symbol])
            llr = d([x, p, 1.])
            self.assertEqual(llr.shape, [batch_size, num_bits_per_symbol])

    def test_no_inputs(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            c = Constellation("custom", num_bits_per_symbol)
            m = Mapper(constellation=c)
            d = DemapperWithPrior("app", constellation=c)
            b = tf.random.uniform([100, 10, 50*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            No = np.ones_like(x, dtype=np.float32)
            p = tf.random.uniform([num_bits_per_symbol])
            llr = d([x, p, No])
            self.assertEqual(llr.shape, [100, 10, 50*num_bits_per_symbol])

            with self.assertRaises(tf.errors.InvalidArgumentError):
                No = tf.constant(np.ones(x.shape[:-1]), dtype=tf.float32)
                p = tf.random.uniform([num_bits_per_symbol])
                llr = d([x, p, No])

    def test_prior_inputs(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            c = Constellation("custom", num_bits_per_symbol)
            m = Mapper(constellation=c)
            d = DemapperWithPrior("app", constellation=c)
            b = tf.random.uniform([100, 10, 50*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            No = np.ones_like(x, dtype=np.float32)
            p = tf.random.uniform([100, 10, 50, num_bits_per_symbol])
            llr = d([x, p, No])
            self.assertEqual(llr.shape, [100, 10, 50*num_bits_per_symbol])

            with self.assertRaises(tf.errors.InvalidArgumentError):
                p = tf.random.uniform([100, 10, 49, num_bits_per_symbol])
                llr = d([x, p, No])

    def test_per_symbol_noise_variance_and_prior(self):
        "Test LLRs with per symbol noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        num_points = 2**num_bits_per_symbol
        m = Mapper("qam", num_bits_per_symbol)
        d_app = DemapperWithPrior("app", "qam", num_bits_per_symbol)
        d_maxlog = DemapperWithPrior("maxlog", "qam", num_bits_per_symbol)
        b = tf.random.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = tf.random.uniform(x.shape, minval=0.01, maxval=100, dtype=np.float32)
        # Precompute priors and probabilities on symbols
        prior = tf.random.normal(tf.concat([x.shape, [num_bits_per_symbol]], axis=0))
        a = np.zeros([num_points, num_bits_per_symbol])
        for i in range(0, num_points):
            a[i,:] = np.array(list(np.binary_repr(i, num_bits_per_symbol)),
                              dtype=np.int16)
        a = 2*a-1
        a = np.expand_dims(a, axis=(0, 1))
        ps_exp = a*np.expand_dims(prior, axis=-2)
        ps_exp = ps_exp - np.log(1+np.exp(ps_exp)) # log(sigmoid(ps_exp))
        ps_exp = np.sum(ps_exp, axis=-1) # [batch size, block length, num points]
        #
        llr_app = d_app([x, prior, No])
        llr_maxlog = d_maxlog([x, prior, No])
        p = d_app.constellation.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - p)**2
                exp = -dist/No[l,i]
                ps_exp_ = ps_exp[l,i]

                llrnp_app = logsumexp(np.take(exp, d_app._c1) + np.take(ps_exp_, d_app._c1),axis=0)\
                    - logsumexp(np.take(exp, d_app._c0) + np.take(ps_exp_, d_app._c0),axis=0)
                llrtarget_app = llr_app[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_app, llrtarget_app, atol=1e-5))

                llrnp_maxlog = np.max(np.take(exp, d_maxlog._c1) + np.take(ps_exp_, d_app._c1),axis=0)\
                    - np.max(np.take(exp, d_maxlog._c0) + np.take(ps_exp_, d_app._c0),axis=0)
                llrtarget_maxlog = llr_maxlog[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_maxlog, llrtarget_maxlog, atol=1e-5))

    def test_broadcastable_noise_variance_and_prior(self):
        "Test LLRs with broadcastable noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        num_points = 2**num_bits_per_symbol
        m = Mapper("qam", num_bits_per_symbol)
        d_app = DemapperWithPrior("app", "qam", num_bits_per_symbol)
        d_maxlog = DemapperWithPrior("maxlog", "qam", num_bits_per_symbol)
        b = tf.random.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = tf.random.uniform([1, 10], minval=0.01, maxval=100, dtype=np.float32)
        # Precompute priors and probabilities on symbols
        prior = tf.random.normal([num_bits_per_symbol])
        a = np.zeros([num_points, num_bits_per_symbol])
        for i in range(0, num_points):
            a[i,:] = np.array(list(np.binary_repr(i, num_bits_per_symbol)),
                              dtype=np.int16)
        a = 2*a-1
        ps_exp = a*np.expand_dims(prior, axis=0)
        ps_exp = ps_exp - np.log(1+np.exp(ps_exp)) # log(sigmoid(ps_exp))
        ps_exp = np.sum(ps_exp, axis=-1) # [num points]
        #
        llr_app = d_app([x, prior, No])
        llr_maxlog = d_maxlog([x, prior, No])
        p = m.constellation.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - p)**2
                exp = -dist/No[0,i]

                llrnp_app = logsumexp(np.take(exp, d_app._c1) + np.take(ps_exp, d_app._c1),axis=0)\
                    - logsumexp(np.take(exp, d_app._c0) + np.take(ps_exp, d_app._c0),axis=0)
                llrtarget_app = llr_app[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_app, llrtarget_app, atol=1e-5))

                llrnp_maxlog = np.max(np.take(exp, d_maxlog._c1) + np.take(ps_exp, d_app._c1),axis=0)\
                    - np.max(np.take(exp, d_maxlog._c0) + np.take(ps_exp, d_app._c0),axis=0)
                llrtarget_maxlog = llr_maxlog[l,i*num_bits_per_symbol:(i+1)*num_bits_per_symbol].numpy()
                self.assertTrue(np.allclose(llrnp_maxlog, llrtarget_maxlog, atol=1e-5))

    def test_graph_mode(self):
        num_bits_per_symbol = 4
        binary_source = BinarySource()
        mapper = Mapper("qam", num_bits_per_symbol)
        awgn = AWGN()
        demapper = DemapperWithPrior("app", "qam", num_bits_per_symbol)
        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = tf.random.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=np.float32)
            prior = tf.random.normal([num_bits_per_symbol])
            y = awgn([x, no])
            return demapper([y, prior, no])
        self.assertEqual(run(100).shape, [100, 3, 400])
        self.assertEqual(run(400).shape, [400, 3, 400])

    def test_graph_mode_jit(self):
        binary_source = BinarySource()
        constellation = Constellation("qam", 4)
        mapper = Mapper(constellation=constellation)
        awgn = AWGN()
        demapper = DemapperWithPrior("app", constellation=constellation)
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = tf.random.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=np.float32)
            prior = tf.random.normal([4])
            y = awgn([x, no])
            return demapper([y, prior, no])
        self.assertEqual(run(100).shape, [100, 3, 400])
        self.assertEqual(run(400).shape, [400, 3, 400])

    def test_model_mode(self):
        binary_source = BinarySource()
        constellation = Constellation("qam", 4)
        mapper = Mapper(constellation=constellation)
        awgn = AWGN()
        demapper = DemapperWithPrior("app", constellation=constellation)
        b = tf.keras.Input(shape=(3, 400), dtype=tf.float32)
        no = tf.keras.Input(shape=(3, 100), dtype=tf.float32)
        prior = tf.keras.Input(shape=(4), dtype=tf.float32)
        x = mapper(b)
        y = awgn([x, no])
        llr = demapper([y, prior, no])
        model = tf.keras.Model(inputs=[b, prior, no], outputs=llr)
        model.compile()
        in1 = binary_source([100, 3, 400])
        in2 = tf.random.normal([4])
        in3 = tf.random.uniform([100, 3, 100], minval=0.01, maxval=100, dtype=np.float32)
        self.assertEqual(model([in1, in2, in3]).shape, [100, 3, 400])
        in1 = binary_source([400, 3, 400])
        in2 = tf.random.normal([4])
        in3 = tf.random.uniform([400, 3, 100], minval=0.01, maxval=100, dtype=np.float32)
        self.assertEqual(model([in1, in2, in3]).shape, [400, 3, 400])

class TestSymbolDemapperWithPrior(unittest.TestCase):

    def test_assert_non_broadcastable_dimensions(self):
        c = Constellation("custom", 4)
        m = Mapper(constellation=c)
        d = SymbolDemapperWithPrior(constellation=c)
        b = tf.random.uniform([64, 10, 200], minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        # Noise
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([64, 9])
            p = tf.random.uniform([16])
            logits = d([x, p, no])
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([32, 10])
            p = tf.random.uniform([16])
            logits = d([x, p, no])
        # prior
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = tf.random.uniform([64, 10, 16])
            logits = d([x, p, 1.0])
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = tf.random.uniform([64, 10, 50])
            logits = d([x, p, 1.0])
        with self.assertRaises(tf.errors.InvalidArgumentError):
            p = tf.random.uniform([64])
            logits = d([x, p, 1.0])

    def test_output_dimensions1(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            num_points = 2**num_bits_per_symbol
            c = Constellation("custom", num_bits_per_symbol)
            m = Mapper(constellation=c)
            d = SymbolDemapperWithPrior(constellation=c)
            batch_size = 32
            dim1 = 10
            dim2 = 12
            b = tf.random.uniform([batch_size, dim1, dim2*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            p = tf.random.uniform([num_points])
            logits = d([x, p, 1.])
            self.assertEqual(logits.shape, [batch_size, dim1, dim2, num_points])

    def test_output_dimensions2(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            num_points = 2**num_bits_per_symbol
            c = Constellation("custom", num_bits_per_symbol)
            m = Mapper(constellation=c)
            d = SymbolDemapperWithPrior(constellation=c)
            batch_size = 32
            b = tf.random.uniform([batch_size, num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            p = tf.random.uniform([num_points])
            logits = d([x, p, 1.])
            self.assertEqual(logits.shape, [batch_size, 1, num_points])

    def test_no_inputs(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            num_points = 2**num_bits_per_symbol
            c = Constellation("custom", num_bits_per_symbol)
            m = Mapper(constellation=c)
            d = SymbolDemapperWithPrior(constellation=c)
            b = tf.random.uniform([100, 10, 50*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            No = np.ones_like(x, dtype=np.float32)
            p = tf.random.uniform([num_points])
            logits = d([x, p, No])
            self.assertEqual(logits.shape, [100, 10, 50, num_points])

            with self.assertRaises(tf.errors.InvalidArgumentError):
                No = tf.constant(np.ones(x.shape[1:]), dtype=tf.float32)
                p = tf.random.uniform([num_points])
                logits = d([x, p, No])

    def test_prior_inputs(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            num_points = 2**num_bits_per_symbol
            c = Constellation("custom", num_bits_per_symbol)
            m = Mapper(constellation=c)
            d = SymbolDemapperWithPrior(constellation=c)
            b = tf.random.uniform([100, 10, 50*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            No = np.ones_like(x, dtype=np.float32)
            p = tf.random.uniform([100, 10, 50, num_points])
            logits = d([x, p, No])
            self.assertEqual(logits.shape, [100, 10, 50, num_points])

            with self.assertRaises(tf.errors.InvalidArgumentError):
                p = tf.random.uniform([100, 10, 49, num_points])
                logits = d([x, p, No])

    def test_per_symbol_noise_variance_and_prior(self):
        "Test LLRs with per symbol noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        num_points = 2**num_bits_per_symbol
        c = Constellation("qam", num_bits_per_symbol)
        m = Mapper(constellation=c)
        d = SymbolDemapperWithPrior(constellation=c)
        b = tf.random.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = tf.random.uniform(x.shape, minval=0.01, maxval=100, dtype=np.float32)
        # Precompute priors and probabilities on symbols
        prior = tf.random.normal(tf.concat([x.shape, [num_points]], axis=0))
        #
        logits = d([x, prior, No])
        points = c.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - points)**2
                exp = -dist/No[l,i]

                logits_ref = exp + prior[l,i]
                logits_ref = logits_ref.numpy()
                logits_ref = logits_ref - np.log(np.sum(np.exp(logits_ref)))  # log(sigmoid(.))
                logits_target = logits[l,i].numpy()
                self.assertTrue(np.allclose(logits_ref, logits_target, atol=1e-5))

    def test_broadcastable_noise_variance_and_prior(self):
        "Test LLRs with broadcastable noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        num_points = 2**num_bits_per_symbol
        c = Constellation("qam", num_bits_per_symbol)
        m = Mapper(constellation=c)
        d = SymbolDemapperWithPrior(constellation=c)
        b = tf.random.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = tf.random.uniform([1, 10], minval=0.01, maxval=100, dtype=np.float32)
        # Precompute priors and probabilities on symbols
        prior = tf.random.normal([num_points])
        #
        logits = d([x, prior, No])
        points = m.constellation.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - points)**2
                exp = -dist/No[0,i]

                logits_ref = exp + prior
                logits_ref = logits_ref.numpy()
                logits_ref = logits_ref - np.log(np.sum(np.exp(logits_ref)))  # log(sigmoid(.))
                logits_target = logits[l,i].numpy()
                self.assertTrue(np.allclose(logits_ref, logits_target, atol=1e-5))

    def test_graph_mode(self):
        num_bits_per_symbol = 4
        num_points = 2**num_bits_per_symbol
        binary_source = BinarySource()
        c = Constellation("qam", num_bits_per_symbol)
        mapper = Mapper(constellation=c)
        awgn = AWGN()
        demapper = SymbolDemapperWithPrior(constellation=c)
        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = tf.random.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=np.float32)
            prior = tf.random.normal([num_points])
            y = awgn([x, no])
            return demapper([y, prior, no])
        self.assertEqual(run(100).shape, [100, 3, 100, 16])
        self.assertEqual(run(400).shape, [400, 3, 100, 16])

    def test_graph_mode_jit(self):
        num_bits_per_symbol = 4
        num_points = 2**num_bits_per_symbol
        binary_source = BinarySource()
        c = Constellation("qam", num_bits_per_symbol)
        mapper = Mapper(constellation=c)
        awgn = AWGN()
        demapper = SymbolDemapperWithPrior(constellation=c)
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = tf.random.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=np.float32)
            prior = tf.random.normal([num_points])
            y = awgn([x, no])
            return demapper([y, prior, no])
        self.assertEqual(run(100).shape, [100, 3, 100, 16])
        self.assertEqual(run(400).shape, [400, 3, 100, 16])

    def test_model_mode(self):
        num_bits_per_symbol = 4
        num_points = 2**num_bits_per_symbol
        binary_source = BinarySource()
        constellation = Constellation("qam", num_bits_per_symbol)
        mapper = Mapper(constellation=constellation)
        awgn = AWGN()
        demapper = SymbolDemapperWithPrior(constellation=constellation)
        b = tf.keras.Input(shape=(3, 400), dtype=tf.float32)
        no = tf.keras.Input(shape=(3, 100), dtype=tf.float32)
        prior = tf.keras.Input(shape=(num_points), dtype=tf.float32)
        x = mapper(b)
        y = awgn([x, no])
        llr = demapper([y, prior, no])
        model = tf.keras.Model(inputs=[b, prior, no], outputs=llr)
        model.compile()
        in1 = binary_source([100, 3, 400])
        in2 = tf.random.normal([num_points])
        in3 = tf.random.uniform([100, 3, 100], minval=0.01, maxval=100, dtype=np.float32)
        self.assertEqual(model([in1, in2, in3]).shape, [100, 3, 100, num_points])
        in1 = binary_source([400, 3, 400])
        in2 = tf.random.normal([num_points])
        in3 = tf.random.uniform([400, 3, 100], minval=0.01, maxval=100, dtype=np.float32)
        self.assertEqual(model([in1, in2, in3]).shape, [400, 3, 100, num_points])

class TestSymbolDemapper(unittest.TestCase):

    def test_assert_non_broadcastable_dimensions(self):
        c = Constellation("custom", 4)
        m = Mapper(constellation=c)
        d = SymbolDemapper(constellation=c)
        b = tf.random.uniform([64, 10, 200], minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        # Noise
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([64, 9])
            logits = d([x, no])
        with self.assertRaises(tf.errors.InvalidArgumentError):
            no = tf.ones([32, 10])
            p = tf.random.uniform([16])
            logits = d([x, no])

    def test_output_dimensions1(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            num_points = 2**num_bits_per_symbol
            c = Constellation("custom", num_bits_per_symbol)
            m = Mapper(constellation=c)
            d = SymbolDemapper(constellation=c)
            batch_size = 32
            dim1 = 10
            dim2 = 12
            b = tf.random.uniform([batch_size, dim1, dim2*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            logits = d([x, 1.])
            self.assertEqual(logits.shape, [batch_size, dim1, dim2, num_points])

    def test_output_dimensions2(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            num_points = 2**num_bits_per_symbol
            c = Constellation("custom", num_bits_per_symbol)
            m = Mapper(constellation=c)
            d = SymbolDemapper(constellation=c)
            batch_size = 32
            b = tf.random.uniform([batch_size, num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            logits = d([x, 1.])
            self.assertEqual(logits.shape, [batch_size, 1, num_points])

    def test_no_inputs(self):
        for num_bits_per_symbol in [1, 2, 4, 6]:
            num_points = 2**num_bits_per_symbol
            c = Constellation("custom", num_bits_per_symbol)
            m = Mapper(constellation=c)
            d = SymbolDemapper(constellation=c)
            b = tf.random.uniform([100, 10, 50*num_bits_per_symbol],
                                minval=0, maxval=2, dtype=tf.dtypes.int32)
            x = m(b)
            No = np.ones_like(x, dtype=np.float32)
            logits = d([x, No])
            self.assertEqual(logits.shape, [100, 10, 50, num_points])

            with self.assertRaises(tf.errors.InvalidArgumentError):
                No = tf.constant(np.ones(x.shape[1:]), dtype=tf.float32)
                logits = d([x, No])

    def test_per_symbol_noise_variance(self):
        "Test LLRs with per symbol noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        c = Constellation("qam", num_bits_per_symbol)
        m = Mapper(constellation=c)
        d = SymbolDemapper(constellation=c)
        b = tf.random.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = tf.random.uniform(x.shape, minval=0.01, maxval=100, dtype=np.float32)
        #
        logits = d([x, No])
        points = c.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - points)**2
                exp = -dist/No[l,i]

                logits_ref = exp.numpy()
                logits_ref = logits_ref - np.log(np.sum(np.exp(logits_ref))) # log(sigmoid(.))
                logits_target = logits[l,i].numpy()
                self.assertTrue(np.allclose(logits_ref, logits_target, atol=1e-5))

    def test_broadcastable_noise_variance(self):
        "Test LLRs with broadcastable noise variance for APP/MAXLOG"
        num_bits_per_symbol = 6
        c = Constellation("qam", num_bits_per_symbol)
        m = Mapper(constellation=c)
        d = SymbolDemapper(constellation=c)
        b = tf.random.uniform([100, 10*num_bits_per_symbol],
                                        minval=0, maxval=2, dtype=tf.dtypes.int32)
        x = m(b)
        No = tf.random.uniform([1, 10], minval=0.01, maxval=100, dtype=np.float32)
        #
        logits = d([x, No])
        points = m.constellation.points
        for l in range(0, x.shape[0]):
            for i, y in enumerate(x[l]):
                dist = np.abs(y - points)**2
                exp = -dist/No[0,i]

                logits_ref = exp.numpy()
                logits_ref = logits_ref - np.log(np.sum(np.exp(logits_ref)))  # log(sigmoid(.))
                logits_target = logits[l,i].numpy()
                self.assertTrue(np.allclose(logits_ref, logits_target, atol=1e-5))

    def test_graph_mode(self):
        num_bits_per_symbol = 4
        binary_source = BinarySource()
        c = Constellation("qam", num_bits_per_symbol)
        mapper = Mapper(constellation=c)
        awgn = AWGN()
        demapper = SymbolDemapper(constellation=c)
        @tf.function
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = tf.random.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=np.float32)
            y = awgn([x, no])
            return demapper([y, no])
        self.assertEqual(run(100).shape, [100, 3, 100, 16])
        self.assertEqual(run(400).shape, [400, 3, 100, 16])

    def test_graph_mode_jit(self):
        num_bits_per_symbol = 4
        binary_source = BinarySource()
        c = Constellation("qam", num_bits_per_symbol)
        mapper = Mapper(constellation=c)
        awgn = AWGN()
        demapper = SymbolDemapper(constellation=c)
        @tf.function(jit_compile=True)
        def run(batch_size):
            b = binary_source([batch_size, 3, 400])
            x = mapper(b)
            no = tf.random.uniform(tf.shape(x), minval=0.01, maxval=100, dtype=np.float32)
            y = awgn([x, no])
            return demapper([y, no])
        self.assertEqual(run(100).shape, [100, 3, 100, 16])
        self.assertEqual(run(400).shape, [400, 3, 100, 16])

    def test_model_mode(self):
        num_bits_per_symbol = 4
        num_points = 2**num_bits_per_symbol
        binary_source = BinarySource()
        constellation = Constellation("qam", num_bits_per_symbol)
        mapper = Mapper(constellation=constellation)
        awgn = AWGN()
        demapper = SymbolDemapper(constellation=constellation)
        b = tf.keras.Input(shape=(3, 400), dtype=tf.float32)
        no = tf.keras.Input(shape=(3, 100), dtype=tf.float32)
        x = mapper(b)
        y = awgn([x, no])
        llr = demapper([y, no])
        model = tf.keras.Model(inputs=[b, no], outputs=llr)
        model.compile()
        in1 = binary_source([100, 3, 400])
        in2 = tf.random.uniform([100, 3, 100], minval=0.01, maxval=100, dtype=np.float32)
        self.assertEqual(model([in1, in2]).shape, [100, 3, 100, num_points])
        in1 = binary_source([400, 3, 400])
        in2 = tf.random.uniform([400, 3, 100], minval=0.01, maxval=100, dtype=np.float32)
        self.assertEqual(model([in1, in2]).shape, [400, 3, 100, num_points])
