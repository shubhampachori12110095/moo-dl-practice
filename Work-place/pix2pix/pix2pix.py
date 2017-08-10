# from: https://github.com/affinelayer/pix2pix-tensorflow

import tensorflow as tf
import numpy as np
import matplotlib.pyplot as plt
import os

from helper import Dataset

def model_inputs(input_height, input_width, input_channel):
    gen_inputs = tf.placeholder(tf.float32, [None, input_height, input_width, input_channel], name='gen_inputs')
    dis_inputs = tf.placeholder(tf.float32, [None, input_height, input_width, input_channel], name='dis_inputs')
    dis_targets = tf.placeholder(tf.float32, [None, input_height, input_width, input_channel], name='dis_targets')

    return gen_inputs, dis_inputs, dis_targets

def generator(inputs, out_channels, n_first_layer_filter=64, alpha=0.2, reuse=False, is_training=True):
    with tf.variable_scope('generator', reuse=reuse):
        # for convolution weights initializer
        w_init = tf.random_normal_initializer(mean=0.0, stddev=0.02)

        # prepare to stack layers
        layers = []

        # encoders
        # encoder_1: [batch, 256, 256, 3] => [batch, 128, 128, 64]
        layer1 = tf.layers.conv2d(inputs, filters=n_first_layer_filter, kernel_size=4, strides=2, padding='same',
                                  kernel_initializer=w_init, use_bias=False)
        layers.append(layer1)

        layer_specs = [
            n_first_layer_filter * 2,  # encoder_2: [batch, 128, 128, 64] => [batch, 64, 64, 128]
            n_first_layer_filter * 4,  # encoder_3: [batch, 64, 64, 128] => [batch, 32, 32, 256]
            n_first_layer_filter * 8,  # encoder_4: [batch, 32, 32, 256] => [batch, 16, 16, 512]
            n_first_layer_filter * 8,  # encoder_5: [batch, 16, 16, 512] => [batch, 8, 8, 512]
            n_first_layer_filter * 8,  # encoder_6: [batch, 8, 8, 512] => [batch, 4, 4, 512]
            n_first_layer_filter * 8,  # encoder_7: [batch, 4, 4, 512] => [batch, 2, 2, 512]
            n_first_layer_filter * 8,  # encoder_8: [batch, 2, 2, 512] => [batch, 1, 1, 512]
        ]
        for n_filters in layer_specs:
            layer = tf.maximum(alpha * layers[-1], layers[-1])
            layer = tf.layers.conv2d(layer, filters=n_filters, kernel_size=4, strides=2, padding='same',
                                     kernel_initializer=w_init, use_bias=False)
            layer = tf.layers.batch_normalization(inputs=layer, training=is_training)
            layers.append(layer)

        # decoders
        num_encoder_layers = len(layers)
        layer_specs = [
            (n_first_layer_filter * 8, 0.5),  # decoder_8: [batch, 1, 1, 512] => [batch, 2, 2, 512]
            (n_first_layer_filter * 8, 0.5),  # decoder_7: [batch, 2, 2, 512] => [batch, 4, 4, 512]
            (n_first_layer_filter * 8, 0.5),  # decoder_6: [batch, 4, 4, 512] => [batch, 8, 8, 512]
            (n_first_layer_filter * 8, 0.0),  # decoder_5: [batch, 8, 8, 512] => [batch, 16, 16, 512]
            (n_first_layer_filter * 4, 0.0),  # decoder_4: [batch, 16, 16, 512] => [batch, 32, 32, 256]
            (n_first_layer_filter * 2, 0.0),  # decoder_3: [batch, 32, 32, 256] => [batch, 64, 64, 128]
            (n_first_layer_filter, 0.0),  # decoder_2: [batch, 64, 64, 128] => [batch, 128, 128, 64]
        ]
        for decoder_layer, (n_filters, dropout) in enumerate(layer_specs):
            # handle skip layer
            skip_layer = num_encoder_layers - decoder_layer - 1
            if decoder_layer == 0:
                # first decoder layer doesn't have skip connections
                # since it is directly connected to the skip_layer
                inputs = layers[-1]
            else:
                inputs = tf.concat([layers[-1], layers[skip_layer]], axis=3)
            layer = tf.maximum(alpha * inputs, inputs)
            layer = tf.layers.conv2d_transpose(inputs=layer, filters=n_filters, kernel_size=4, strides=2, padding='same')
            layer = tf.layers.batch_normalization(inputs=layer, training=is_training)

            # handle dropout
            if dropout > 0.0:
               layer = tf.layers.dropout(layer, rate=dropout)

            # stack
            layers.append(layer)

        # decoder_1: [batch, 128, 128, 64] => [batch, 256, 256, out_channels]
        last_layer = tf.maximum(alpha * layers[-1], layers[-1])
        last_layer = tf.layers.conv2d_transpose(inputs=last_layer, filters=out_channels, kernel_size=4, strides=2,
                                                padding='same')
        out = tf.tanh(last_layer)
        layers.append(last_layer)

        return out

def discriminator(inputs, targets, n_first_layer_filter=64, alpha=0.2, reuse=False, is_training=True):
    with tf.variable_scope('discriminator', reuse=reuse):
        # for convolution weights initializer
        w_init = tf.random_normal_initializer(mean=0.0, stddev=0.02)

        # concatenate inputs
        # M: batch size
        # Mx256x256x3 + Mx256x256x3 => Mx256x256x6
        concat_inputs = tf.concat(values=[inputs, targets], axis=3)

        # layer_1: [batch, 256, 256, 6] => [batch, 128, 128, 64], without batchnorm
        l1 = tf.layers.conv2d(concat_inputs, filters=n_first_layer_filter, kernel_size=4, strides=2, padding='same',
                              kernel_initializer=w_init, use_bias=False)
        l1 = tf.maximum(alpha * l1, l1)

        # layer_2: [batch, 128, 128, 64] => [batch, 64, 64, 128], with batchnorm
        n_filter = n_first_layer_filter * 2
        l2 = tf.layers.conv2d(l1, filters=n_filter, kernel_size=4, strides=2, padding='same',
                              kernel_initializer=w_init, use_bias=False)
        l2 = tf.layers.batch_normalization(inputs=l2, training=is_training)
        l2 = tf.maximum(alpha * l2, l2)

        # layer_3: [batch, 64, 64, 128] => [batch, 32, 32, 256], with batchnorm
        n_filter = n_first_layer_filter * 4
        l3 = tf.layers.conv2d(l2, filters=n_filter, kernel_size=4, strides=2, padding='same',
                              kernel_initializer=w_init, use_bias=False)
        l3 = tf.layers.batch_normalization(inputs=l3, training=is_training)
        l3 = tf.maximum(alpha * l3, l3)

        # layer_4: [batch, 32, 32, 256] => [batch, 31, 31, 512], with batchnorm
        n_filter = n_first_layer_filter * 8
        l4 = tf.layers.conv2d(l3, filters=n_filter, kernel_size=2, strides=1, padding='valid',
                              kernel_initializer=w_init, use_bias=False)
        l4 = tf.layers.batch_normalization(inputs=l4, training=is_training)
        l4 = tf.maximum(alpha * l4, l4)

        # layer_5: [batch, 31, 31, 512] => [batch, 30, 30, 1], without batchnorm
        n_filter = 1
        l5 = tf.layers.conv2d(l4, filters=n_filter, kernel_size=2, strides=1, padding='valid',
                              kernel_initializer=w_init, use_bias=False)
        out = tf.sigmoid(l5)

        return out

def model_loss(gen_inputs, dis_inputs, dis_targets, out_channels, gan_weight=1.0, l1_weight=100.0):
    # get each model outputs
    gen_output = generator(gen_inputs, out_channels, reuse=False, is_training=True)
    predict_real = discriminator(dis_inputs, dis_targets, reuse=False, is_training=True)
    predict_fake = discriminator(dis_inputs, gen_output, reuse=True, is_training=True)

    # compute loss
    # minimizing -tf.log will try to get inputs to 1
    # predict_real => 1
    # predict_fake => 0
    eps = 1e-12
    d_loss = tf.reduce_mean(-(tf.log(predict_real + eps) + tf.log(1 - predict_fake + eps)))

    # predict_fake => 1
    # abs(targets - outputs) => 0
    gen_loss_GAN = tf.reduce_mean(-tf.log(predict_fake + eps))
    gen_loss_L1 = tf.reduce_mean(tf.abs(dis_targets - gen_output))
    g_loss = gen_loss_GAN * gan_weight + gen_loss_L1 * l1_weight

    return d_loss, gen_loss_GAN, gen_loss_L1, g_loss

def model_opt(d_loss, gen_loss_GAN, gen_loss_L1, g_loss, learning_rate, beta1):
    # Get weights and bias to update
    t_vars = tf.trainable_variables()
    d_vars = [var for var in t_vars if var.name.startswith('discriminator')]
    g_vars = [var for var in t_vars if var.name.startswith('generator')]

    # Optimize
    d_train_opt = tf.train.AdamOptimizer(learning_rate, beta1=beta1).minimize(d_loss, var_list=d_vars)
    with tf.control_dependencies(tf.get_collection(tf.GraphKeys.UPDATE_OPS)):
        g_train_opt = tf.train.AdamOptimizer(learning_rate, beta1=beta1).minimize(g_loss, var_list=g_vars)

    return d_train_opt, g_train_opt

# def model_opt(d_loss, gen_loss_GAN, gen_loss_L1, g_loss, learning_rate, beta1):
#     discrim_tvars = [var for var in tf.trainable_variables() if var.name.startswith("discriminator")]
#     discrim_optim = tf.train.AdamOptimizer(learning_rate, beta1)
#     discrim_grads_and_vars = discrim_optim.compute_gradients(d_loss, var_list=discrim_tvars)
#     d_train_opt = discrim_optim.apply_gradients(discrim_grads_and_vars)
#
#     with tf.control_dependencies([d_train_opt]):
#         gen_tvars = [var for var in tf.trainable_variables() if var.name.startswith("generator")]
#         gen_optim = tf.train.AdamOptimizer(learning_rate, beta1)
#         gen_grads_and_vars = gen_optim.compute_gradients(g_loss, var_list=gen_tvars)
#         g_train_opt = gen_optim.apply_gradients(gen_grads_and_vars)
#
#     ema = tf.train.ExponentialMovingAverage(decay=0.99)
#     update_losses = ema.apply([d_loss, gen_loss_GAN, gen_loss_L1])

def train(net, epochs, batch_size, train_input_image_dir, test_input_image_dir, print_every=30):
    losses = []
    steps = 0

    # prepare dataset
    train_dataset = Dataset(train_input_image_dir)
    test_dataset = Dataset(test_input_image_dir)

    with tf.Session() as sess:
        sess.run(tf.global_variables_initializer())
        for e in range(epochs):
            for ii in range(train_dataset.n_images//batch_size):
                steps += 1

                # will return list of tuples [ (inputs, targets), (inputs, targets), ... , (inputs, targets)]
                batch_images_tuple = train_dataset.get_next_batch(batch_size)

                a = [x for x, y in batch_images_tuple]
                b = [y for x, y in batch_images_tuple]
                a = np.array(a)
                b = np.array(b)

                fd = {
                    net.dis_inputs: a,
                    net.dis_targets: b,
                    net.gen_inputs: a
                }
                d_opt_out = sess.run(net.d_train_opt, feed_dict=fd)
                g_opt_out = sess.run(net.g_train_opt, feed_dict=fd)

                if steps % print_every == 0:
                    # At the end of each epoch, get the losses and print them out
                    train_loss_d = net.d_loss.eval(fd)
                    train_loss_g = net.g_loss.eval(fd)
                    train_loss_GAN = net.gen_loss_GAN.eval(fd)
                    train_loss_L1 = net.gen_loss_L1.eval(fd)

                    print("Epoch {}/{}...".format(e + 1, epochs),
                          "Discriminator Loss: {:.4f}...".format(train_loss_d),
                          "Generator Loss GAN: {:.4f}".format(train_loss_GAN),
                          "Generator Loss L1: {:.4f}".format(train_loss_L1),
                          "Generator Loss: {:.4f}".format(train_loss_g))
                    # Save losses to view after training
                    losses.append((train_loss_d, train_loss_g))

            # save generated images on every epochs
            image_fn = './assets/epoch_{:d}_tf.png'.format(e)
            image_title = 'epoch {:d}'.format(e)
            test_image = test_dataset.get_next_batch(1)
            test_a = [x for x, y in test_image]
            test_a = np.array(test_a)

            gen_image = sess.run(generator(net.gen_inputs, net.input_channel, reuse=True, is_training=False),
                                 feed_dict={net.gen_inputs: test_a})

            fig, ax = plt.subplots()
            gen_image = np.squeeze(gen_image, axis=0)

            # de-normalize
            # Scale to 0-255
            gen_image = (((gen_image - gen_image.min()) * 255) / (gen_image.max() - gen_image.min())).astype(np.uint8)
            ax.imshow(gen_image)
            plt.suptitle(image_title)
            plt.savefig(image_fn)
            plt.close(fig)

    return losses



class Pix2Pix(object):
    def __init__(self, learning_rate):
        self.input_height, self.input_width, self.input_channel = 256, 256, 3
        self.gan_weight, self.l1_weight = 1.0, 100.0
        self.beta1 = 0.5
        self.learning_rate = learning_rate

        # build model
        tf.reset_default_graph()
        self.gen_inputs, self.dis_inputs, self.dis_targets = model_inputs(self.input_height,
                                                                          self.input_width,
                                                                          self.input_channel)
        self.d_loss, self.gen_loss_GAN, self.gen_loss_L1, self.g_loss = model_loss(self.gen_inputs,
                                                                                   self.dis_inputs,
                                                                                   self.dis_targets,
                                                                                   self.input_channel,
                                                                                   self.gan_weight,
                                                                                   self.l1_weight)
        self.d_train_opt, self.g_train_opt = model_opt(self.d_loss,
                                                       self.gen_loss_GAN,
                                                       self.gen_loss_L1,
                                                       self.g_loss,
                                                       self.learning_rate,
                                                       self.beta1)

def main():
    assets_dir = './assets/'
    if not os.path.isdir(assets_dir):
        os.mkdir(assets_dir)

    # hyper parameters
    learning_rate = 0.0002
    n_epochs = 200
    batch_size = 2
    pix2pix = Pix2Pix(learning_rate)

    train_input_image_dir = '../Data_sets/facades/train/'
    test_input_image_dir = '../Data_sets/facades/test/'
    losses = train(pix2pix, n_epochs, batch_size, train_input_image_dir, test_input_image_dir)

    fig, ax = plt.subplots()
    losses = np.array(losses)
    plt.plot(losses.T[0], label='Discriminator', alpha=0.5)
    plt.plot(losses.T[1], label='Generator', alpha=0.5)
    plt.title("Training Losses")
    plt.legend()
    plt.savefig('./assets/losses_tf.png')

    return 0

def test():
    # sess = tf.InteractiveSession()
    # t = tf.zeros([64, 64, 64, 128], dtype=tf.float32)
    #
    # w_init = tf.random_normal_initializer(mean=0.0, stddev=0.02)
    # # l1 = tf.layers.conv2d(t, filters=512, kernel_size=4, strides=2, padding='same', kernel_initializer=w_init, use_bias=False)
    # l1 = tf.layers.conv2d_transpose(t, filters=64, kernel_size=4, strides=2, padding='same', kernel_initializer=w_init,
    #                                 use_bias=False)
    #
    # print(l1.shape)
    #
    # sess.close()

    batch_size = 2
    train_input_image_dir = '../Data_sets/facades/train/'
    my_dataset = Dataset(train_input_image_dir)
    # batch_images_tuple = my_dataset.get_next_batch(batch_size)
    #
    # a = [x for x, y in batch_images_tuple]
    # b = [y for x, y in batch_images_tuple]
    # a = np.array(a)
    # b = np.array(b)
    # print(a.shape)
    # print(b.shape)

    steps = 0

    for ii in range(my_dataset.n_images // batch_size):
        steps += 1

        # will return list of tuples [ (inputs, targets), (inputs, targets), ... , (inputs, targets)]
        batch_images_tuple = my_dataset.get_next_batch(batch_size)

        a = [x for x, y in batch_images_tuple]
        b = [y for x, y in batch_images_tuple]
        a = np.array(a)
        b = np.array(b)
        print('a: ', a.shape)
        print('b: ', b.shape)

if __name__ == '__main__':
    main()
    # test()


