"""Some useful helper functions for working with NNs in TensorFlow."""
import glob
import math
import os

import numpy as np
import tensorflow as tf

from dataset import FLAGS

####### VARIABLE CREATION
"""Create a weight variable initalized with a random normal distribution.

The variable name is `weights` (it is assumed the variable is suitably scoped
by a `tf.name_scope`. The variance is chosen using Xavier initialization
modified for ReLU nonlinearities, see e.g. arXiv:1502.01852 [cs.CV].

Arguments:
    shape   the shape of the variable
    dtype   the datatype of the variable (default: `tf.float32`)
    mean    the mean of the distribution (default: `0`)
    stddev  the standard deviation of the distribution (default: `0.1`)

Returns:
    A `tf.Variable` with the above properties.
"""
def weight_variable(shape):
    return tf.get_variable(
            name='weights',
            shape=shape,
            initializer=tf.uniform_unit_scaling_initializer(
                # this factor of ~sqrt(2) in the stddev (i.e. 2 in the variance)
                # has been found to be suitable when relu nonlinearities are used
                # see, e.g. arXiv:1502.01852 [cs.CV]
                factor=1.43,
                dtype=tf.float32)
            )

"""Create a weight variable for a convolution initialized with ReLU Xavier initialization.

Arguments:
    size        the width/height of the kernel (kernel is assumed to be square)
    channels    list of channel sizes in the form `[in, out]`

The variable shape will be `[ksize, ksize, channels_in, channels_out]`.
"""
def conv_weight_variable(size, channels):
    shape = [size, size] + channels
    return weight_variable(shape=shape)

"""Create a weight variable for a fully connected layer initialized with ReLU Xavier initialization.

Arguments:
    size_in     size of previous layer
    size_out    size of current layer

The variable shape will be `[size_in, size_out]`.
"""
def fc_weight_variable(size_in, size_out):
    return weight_variable(shape=[size_in, size_out])

"""Create a bias variable initalized with constants.

The variable name is `bias` (it is assumed the variable is suitably scoped
by a `tf.name_scope`.

Arguments:
    shape   the shape of the variable
    dtype   the datatype of the variable (default: `tf.float32`)
    value   the constant value for initialization

Returns:
    A `tf.Variable` with the above properties.
"""
def bias_variable(shape, value=0.1):
    return tf.get_variable(
            name='bias',
            shape=shape,
            initializer=tf.constant_initializer(
                value=value,
                dtype=tf.float32)
            )


######## NETWORK BUILDING
def conv_op(X, size, channels, name, stride, padding='SAME', relu=True):
    with tf.variable_scope(name):
        weights = conv_weight_variable(size=size, channels=channels)
        bias = bias_variable(shape=channels[-1])
        h_conv = tf.nn.conv2d(X, weights, strides=[1, stride, stride, 1], padding=padding) + bias
        if relu:
            h_out = tf.nn.relu(h_conv)
        else:
            h_out = h_conv
    return h_out

class BadPoolMode(Exception):
    pass

def pool_op(X, size, stride, name, padding='SAME', mode='avg'):
    ksize = [1, size, size, 1]
    strides = [1, stride, stride, 1]
    with tf.variable_scope(name):
        if mode == 'avg':
            h_pool = tf.nn.avg_pool(X, ksize=ksize, strides=strides, padding=padding, name=name)
        elif mode == 'max':
            h_pool = tf.nn.max_pool(X, ksize=ksize, strides=strides, padding=padding, name=name)
        else:
            raise BadPoolMode()
    return h_pool

def fc_op(X, channels_in, channels_out, name, relu=True):
    with tf.variable_scope(name):
        weights = fc_weight_variable(channels_in, channels_out)
        bias = bias_variable(channels_out)
        h_fc = tf.matmul(X, weights) + bias
        if relu:
            h_out = tf.nn.relu(h_fc)
        else:
            h_out = h_fc
    return h_out

######## GRAPH BUILDING
"""Add nodes to the graph to compute cross entropy and write it to summary files."""
def loss_op(logits, labels):
    cross_entropy = tf.nn.sigmoid_cross_entropy_with_logits(logits=logits, labels=labels, name='xentropy')
    cross_entropy_avg = tf.reduce_mean(cross_entropy, name='xentropy_avg')
    tf.summary.scalar('xentropy_avg', cross_entropy_avg)
    return cross_entropy_avg

"""Add nodes to the graph to compute accuracy and write it to summary files."""
def accuracy_op(logits, labels, name=''):
    name = name + ('_' if name else '') + 'accuracy'
    activation = tf.nn.sigmoid(logits)
    correct_prediction = tf.equal(tf.greater(activation, 0.5), tf.greater(labels, 0.5))
    accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32), name=name)
    tf.summary.scalar(name=name, tensor=accuracy)
    return accuracy

"""Add nodes to the graph to do training and track the overall training step."""
def train_op(loss, learning_rate):
    global_step = tf.Variable(0, name='global_step', trainable=False)
    return tf.train.AdamOptimizer(learning_rate).minimize(loss, global_step=global_step)

"""Evaluate operation `op` over a number of batches.

Arguments:
    sess            the TensorFlow session
    op              the desired operation
    num_examples    total number of examples over which to average

Number of batches is `ceil(num_examples / BATCH_SIZE)
"""
def avg_op(sess, op, num_examples=10000):
    num_batches = int(math.ceil(num_examples / FLAGS['BATCH_SIZE']))
    acc = np.zeros(op.get_shape())
    for i in range(num_batches):
        acc += sess.run(op)
    return acc / num_batches


######## DIRECTORIES
def get_dir(main, name, pattern):
    return os.path.join(FLAGS[main+'_DIR'], name, '*' if pattern else '')

def log_dir(name, pattern=False):
    return get_dir('LOG', name, pattern=pattern)

def checkpoint_dir(name, pattern=False):
    return get_dir('CHECKPOINT', name, pattern=pattern)

def prediction_file(name):
    return os.path.join(FLAGS['DATA_DIR'], name + '.csv')

def create_if_needed(path):
    # TODO should really check if `path` is an ordinary file and raise an Exception
    if not os.path.isdir(path):
        os.makedirs(path)

######## TRAINING AND EVALUATION
"""Reset graph and remove temporary files, including logs, checkpoints and Kaggle predictions."""
def run_cleanup(name, do_training):
    tf.reset_default_graph()

    if do_training:
        for file in glob.glob(log_dir(name, pattern=True)):
            os.remove(file)
        for file in glob.glob(checkpoint_dir(name, pattern=True)):
            os.remove(file)
    if os.path.isfile(prediction_file(name)):
        os.remove(prediction_file(name))

"""Create log and checkpoint subdirectories."""
def run_setup(name):
    create_if_needed(log_dir(name))
    create_if_needed(checkpoint_dir(name))

"""Run some operation inside a session, starting threads as needed."""
def run_in_tf(func, after, name, checkpoint=None, loop=True, **func_args):
    init_op = tf.group(tf.global_variables_initializer(), tf.local_variables_initializer())
    saver = tf.train.Saver(max_to_keep=10, keep_checkpoint_every_n_hours=1)
    sess = tf.Session(config=tf.ConfigProto(log_device_placement=True))

    summary_op = tf.summary.merge_all()
    log_writer = tf.summary.FileWriter(logdir=os.path.join(FLAGS['LOG_DIR'], name), graph=sess.graph)

    sess.run(init_op)
    if checkpoint:
        saver.restore(sess, checkpoint.model_checkpoint_path)

    coord = tf.train.Coordinator()
    threads = tf.train.start_queue_runners(sess=sess, coord=coord)

    step = 0

    kwargs = {
            'sess': sess,
            'saver': saver,
            'log_writer': log_writer,
            'summary_op': summary_op,
            'name': name,
            }

    def after_func(step):
        after(step=step, **func_args, **kwargs)

    if loop:
        try:
            while not coord.should_stop():
                func(step=step, **func_args, **kwargs)
                step += 1
        except tf.errors.OutOfRangeError:
            after_func(step=step)
        finally:
            coord.request_stop()
    else:
        after_func(step=step)
        coord.request_stop()

    coord.join(threads)
    sess.close()

"""Run training, write summaries and do evaluation, given computed logits and labels.

Arguments:
    logits              the computed logits
    labels              the known training labels
    valid_accuracy_op   operation to compute model accuracy on validation set
                        (if set to `None`, validation accuracy is not calcuated)
    test_accuracy_op    operation to compute model accuracy on test set
                        (if set to `None`, test accuracy is not calcuated)
    name                the name of the model, used for log and checkpoint directories
    learning_rate       the learning rate to use for training
"""
def run_training(logits, labels, train_accuracy_op, valid_accuracy_op, test_accuracy_op, name, learning_rate):
    loss = loss_op(logits, labels)
    train = train_op(loss, learning_rate=learning_rate)

    run_in_tf(func=_training_func,
              after=_training_after,
              name=name,
              loss=loss,
              train=train,
              train_accuracy_op=train_accuracy_op,
              valid_accuracy_op=valid_accuracy_op,
              test_accuracy_op=test_accuracy_op)

def _print_accuracy(sess, accuracy_op, label):
    if accuracy_op is not None:
        accuracy = avg_op(sess, accuracy_op)
        print('{} accuracy: {:.1%}'.format(label, accuracy))

def _training_func(loss, train, log_writer, summary_op, train_accuracy_op, valid_accuracy_op, sess, saver, step ,name, **kwargs_unused):
    if step % 1000 == 0:
        _run_eval(sess=sess, train_accuracy_op=train_accuracy_op, valid_accuracy_op=valid_accuracy_op, test_accuracy_op=None)

    if step % 250 == 0:
        summary, xentropy = sess.run([summary_op, loss])
        saver.save(sess, os.path.join(FLAGS['CHECKPOINT_DIR'], name, name), global_step=step)
        log_writer.add_summary(summary, global_step=step)
        print('Cross Entropy: {xentropy:.2n}'.format(xentropy=xentropy))

    if step % 100 == 0:
        summary = sess.run(summary_op)
        log_writer.add_summary(summary, global_step=step)

    sess.run(train)

def _training_after(train_accuracy_op, valid_accuracy_op, test_accuracy_op, sess, saver, step, name, **kwargs_unused):
    print('Done training for {} steps.'.format(step))
    saver.save(sess, os.path.join(FLAGS['CHECKPOINT_DIR'], name, name), global_step=step)
    _run_eval(
            sess=sess,
            train_accuracy_op=train_accuracy_op,
            valid_accuracy_op=valid_accuracy_op,
            test_accuracy_op=test_accuracy_op
            )

"""Make predictions given a logit node in the graph, using the model at its current state of training."""
def run_prediction(logits, name):
    outfile = open(prediction_file(name), 'wb')
    outfile.write(b'id,label\n')

    activation_op = tf.nn.sigmoid(logits)
    checkpoint = tf.train.get_checkpoint_state(checkpoint_dir(name))

    run_in_tf(func=_prediction_func, after=_prediction_after, outfile=outfile, activation_op=activation_op, checkpoint=checkpoint, name=name)

    outfile.close()

# helper ops for run_prediction
def _prediction_func(outfile, activation_op, sess, saver, step, name, **kwargs_unused):
    dog_prob = sess.run(activation_op).reshape([-1, 1])
    id_column = np.arange(FLAGS['BATCH_SIZE']).reshape([-1, 1]) + step * FLAGS['BATCH_SIZE'] + 1

    np.savetxt(fname=outfile, X=np.append(id_column, dog_prob, 1), fmt=['%i', '%.2f'], delimiter=',')
    outfile.flush()

def _prediction_after(step, name, **kwargs):
    print('Wrote {} predictions to {}'.format(step * FLAGS['BATCH_SIZE'], prediction_file(name)))

def run_eval(name, train_accuracy_op, valid_accuracy_op, test_accuracy_op):
    checkpoint = tf.train.get_checkpoint_state(checkpoint_dir(name))
    run_in_tf(func=None, after=_run_eval, name='eval', checkpoint=checkpoint, loop=False, train_accuracy_op=train_accuracy_op, valid_accuracy_op=valid_accuracy_op, test_accuracy_op=test_accuracy_op)
    pass

def _run_eval(sess, train_accuracy_op, valid_accuracy_op, test_accuracy_op, **kwargs):
    _print_accuracy(sess=sess, accuracy_op=train_accuracy_op, label='Train')
    _print_accuracy(sess=sess, accuracy_op=valid_accuracy_op, label='Validation')
    _print_accuracy(sess=sess, accuracy_op=test_accuracy_op, label='Test')

"""Run all operations.

Arguments:
    inference_op    function returning the inference operation (essentially the network graph)
    inputs          function returning input batches
    total_epochs    number of epochs of training data for which to train
    learning_rate   learning rate hyperparameter passed to the optimizer
    name            the name of the network (used as a sub directory for logs, checkpoints, etc)
"""
def run_all(inference_op, inputs, total_epochs, learning_rate, name, do_training=True):
    run_cleanup(name=name, do_training=do_training)
    run_setup(name=name)

    ## create graph nodes for prediction on train, validation and test sets

    images, labels = inputs(name='train', num_epochs=total_epochs)
    logits = inference_op(images, train=True)

    # train images again for evaluation purposes
    train_images, train_labels = inputs(name='train', num_epochs=None)
    train_logits = inference_op(train_images, train=False)
    train_accuracy_op = accuracy_op(train_logits, train_labels, name='train')

    valid_images, valid_labels = inputs(name='validation', num_epochs=None)
    valid_logits = inference_op(valid_images, train=False)
    valid_accuracy_op = accuracy_op(valid_logits, valid_labels, name='validation')

    test_images, test_labels = inputs(name='test', num_epochs=None)
    test_logits = inference_op(test_images, train=False)
    test_accuracy_op = accuracy_op(test_logits, test_labels, name='test')

    kwargs = {
            'train_accuracy_op': train_accuracy_op,
            'valid_accuracy_op': valid_accuracy_op,
            'test_accuracy_op':  test_accuracy_op,
            'name': name,
            }

    # if desired, do training (with evaluation)
    if do_training:
        run_training(logits=logits, labels=labels, learning_rate=learning_rate, **kwargs)
    else: # otherwise just evaluate
        run_eval(**kwargs)

    # and do prediction on Kaggle test images
    kaggle_images = inputs(name='kaggle', num_epochs=1, predict=True)
    kaggle_logits = inference_op(kaggle_images, train=False)

    run_prediction(logits=kaggle_logits, name=name)
