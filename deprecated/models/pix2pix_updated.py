from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
import tensorflow as tf


class InstanceNormalization(tf.keras.layers.Layer):
    def __init__(self, epsilon=1e-5, **kwargs):
        super().__init__(**kwargs)
        self.epsilon = epsilon
        self.scale = None
        self.offset = None

    def build(self, input_shape):
        self.scale = self.add_weight(
            name='scale',
            shape=input_shape[-1:],
            initializer=tf.random_normal_initializer(1., 0.02),
            trainable=True
        )

        self.offset = self.add_weight(
            name='offset',
            shape=input_shape[-1:],
            initializer='zeros',
            trainable=True
        )

    def call(self, x, **kwargs):
        mean, variance = tf.nn.moments(x, axes=[1, 2], keepdims=True)
        inv = tf.math.sqrt(variance + self.epsilon)
        normalized = (x - mean) * inv
        return self.scale * normalized + self.offset


def downsample(filters: int, size: int, apply_norm=True, norm_type='batchnorm'):
    """Convenience function for the creation of a downsampling block made of a 2D Convolutional layer, an optional
    Batch Normalization or Instance Normalization layer and a Leaky ReLU activation function.

    :param filters: int. Determines the number of filters in the Conv2D layer.
    :param size: int. Determines the size of said filters.
    :param apply_norm: Whether or not to apply a BatchNormalization layer to the activations.
    :param norm_type: Normalization to apply. Either batchnorm or instancenorm.
    :return: A sequential model consisting of a Conv2D, an optional BatchNormalization and a LeakyReLU
    """
    initializer = tf.random_normal_initializer(0., 0.02)

    result = tf.keras.Sequential()
    result.add(tf.keras.layers.Conv2D(filters, size, strides=2, padding='same',
                                      kernel_initializer=initializer, use_bias=False))

    if apply_norm:
        if norm_type == 'batchnorm':
            result.add(tf.keras.layers.BatchNormalization())
        elif norm_type == 'instancenorm':
            result.add(InstanceNormalization())

    result.add(tf.keras.layers.LeakyReLU())

    return result


def upsample(filters: int, size: int, apply_dropout=False, norm_type='batchnorm'):
    """Convenience function for the creation of an umpsampling block made of a Transposed 2D Convolutional layer,
    a Batch Normalization layer, an optional Dropout layer and a Leaky ReLU activation function.

    :param filters: int. Determines the number of filters in the Conv2DTranspose layer.
    :param size: int. Determines the size of said filters.
    :param apply_dropout: Whether or not to apply a Dropout to the activations.
    :param norm_type: Normalization to apply. Either batchnorm or instancenorm.
    :return: A sequential model consisting of a Conv2D, an optional BatchNormalization and a LeakyReLU
    """
    initializer = tf.random_normal_initializer(0., 0.02)

    result = tf.keras.Sequential()
    result.add(tf.keras.layers.Conv2DTranspose(filters, size, strides=2, padding='same',
                                               kernel_initializer=initializer, use_bias=False))

    if norm_type == 'batchnorm':
        result.add(tf.keras.layers.BatchNormalization())
    elif norm_type == 'instancenorm':
        result.add(InstanceNormalization())

    if apply_dropout:
        result.add(tf.keras.layers.Dropout(0.5))

    result.add(tf.keras.layers.ReLU())

    return result


def generator(input_shape: list = None, heads=1, out_dims=3, activation='tanh'):
    if input_shape is None:
        input_shape = [None, None, 3]

    down_stack = [
        downsample(64, 4, apply_norm=False),
        downsample(128, 4),
        downsample(256, 4),
        downsample(512, 4),
        downsample(512, 4),
        downsample(512, 4),
        downsample(512, 4),
        downsample(512, 4)
    ]

    up_stack = [
        upsample(512, 4, apply_dropout=True),
        upsample(512, 4, apply_dropout=True),
        upsample(512, 4, apply_dropout=True),
        upsample(512, 4),
        upsample(256, 4),
        upsample(128, 4),
        upsample(64, 4),
    ]

    input_layers = []
    for n in range(heads):
        input_layers.append(tf.keras.layers.Input(shape=input_shape))

    if heads > 1:
        x = tf.keras.layers.concatenate(input_layers)
    else:
        x = input_layers[0]

    # downsampling
    skips = []
    for down in down_stack:
        x = down(x)
        skips.append(x)

    skips = reversed(skips[:-1])

    # upsampling and connecting
    for up, skip in zip(up_stack, skips):
        x = up(x)
        x = tf.keras.layers.Concatenate()([x, skip])

    initializer = tf.random_normal_initializer(0., 0.02)
    last = tf.keras.layers.Conv2DTranspose(out_dims, 4, strides=2, padding='same',
                                           kernel_initializer=initializer, activation=activation)
    x = last(x)

    return tf.keras.Model(inputs=input_layers, outputs=x)


def discriminator(input_shape=None, initial_units=64, layers=4):
    if input_shape is None:
        input_shape = [None, None, 3]

    initializer = tf.random_normal_initializer(0., 0.02)

    inp = tf.keras.layers.Input(shape=input_shape, name='input_image')
    target_image = tf.keras.layers.Input(shape=input_shape, name='target_image')
    x = tf.keras.layers.concatenate([inp, target_image])

    multiplier = 1
    for layer in range(layers):
        if layer == 1:
            x = downsample(initial_units * multiplier, 4, apply_norm=False)(x)
            multiplier *= 2
        else:
            x = downsample(initial_units * multiplier, 4)(x)
            if multiplier < 8:
                multiplier *= 2

    last = tf.keras.layers.Conv2D(1, 4, strides=1, kernel_initializer=initializer, activation='sigmoid')(x)

    return tf.keras.Model(inputs=[inp, target_image], outputs=last)

# ----------------------------------------------------------------------------------------------------------------------


class Pix2Pix:
    def __init__(self, gen=None, disc=None):
        if gen is None:
            self.generator = generator()
        else:
            self.generator = gen
        if disc is None:
            self.discriminator = discriminator()
        else:
            self.discriminator = disc

        self.loss_object = tf.keras.losses.BinaryCrossentropy(from_logits=True)
        self.optimizer_g = tf.keras.optimizers.Adam(2e-4, beta_1=0.5)
        self.optimizer_d = tf.keras.optimizers.Adam(2e-4, beta_1=0.5)

    def _loss_d(self, d_y, d_g_x):
        loss_y = self.loss_object(tf.ones_like(d_y), d_y)
        loss_g_x = self.loss_object(tf.zeros_like(d_g_x), d_g_x)
        loss_total = 0.5 * (loss_y + loss_g_x)
        return loss_total

    def _loss_g(self, d_g_x, **kwargs):
        """Base generator loss function.

        :param d_g_x: discriminator output for the generator's output.
        :param kwargs: for the base class, accepted kwargs are y (expected output) and g_x (generator output)
        :return: generator loss
        """
        loss_d_g_x = self.loss_object(tf.ones_like(d_g_x), d_g_x)
        loss_l1 = tf.reduce_mean(tf.abs(kwargs['y'] - kwargs['g_x']))
        loss_total = loss_d_g_x + kwargs['multiplier'] * loss_l1
        return loss_total, loss_l1

    @tf.function
    def _step(self, train_x, train_y, epoch, training=True, writer=None):
        with tf.GradientTape(persistent=True) as tape:
            g_x = self.generator(train_x, training=training)

            d_g_x = self.discriminator([train_x, g_x], training=training)
            d_y = self.discriminator([train_x, train_y], training=training)

            g_loss, l1_loss = self._loss_g(d_g_x, y=train_y, g_x=g_x, multiplier=100)
            d_loss = self._loss_d(d_y, d_g_x)

        if training:
            self._gradient_update(tape, g_loss, self.generator, self.optimizer_g)
            self._gradient_update(tape, d_loss, self.discriminator, self.optimizer_d)

        if writer is not None:
            with writer.as_default():
                tf.summary.scalar('g_loss', g_loss, step=epoch)
                tf.summary.scalar('g_loss_l1', l1_loss, step=epoch)
                tf.summary.scalar('d_loss', d_loss, step=epoch)

    @staticmethod
    def _gradient_update(tape, loss, model, optimizer):
        gradients = tape.gradient(loss, model.trainable_variables)
        optimizer.apply_gradients(zip(gradients, model.trainable_variables))

    @staticmethod
    def _write_metrics(writer, metrics_names, metrics, epoch):
        if writer is not None:
            with writer.as_default():
                for name, metric in zip(metrics_names, metrics):
                    tf.summary.scalar(name, metric, step=epoch)

    def fit(self, train, validation, epochs=1, log_dir=None):
        writer_train, writer_val = None, None
        if log_dir is not None:
            writer_train, writer_val = self._get_writers(log_dir)

        for epoch in range(epochs):
            for train_x, train_y in train:
                self._step(train_x, train_y, epoch, training=True, writer=writer_train)
            self._log_images(train, writer_train, epoch)

            for val_x, val_y in validation:
                self._step(val_x, val_y, epoch, training=False, writer=writer_val)
            self._log_images(validation, writer_val, epoch)

    def _log_images(self, dataset, writer, epoch):
        if writer is not None:
            x, _ = next(dataset.take(1).__iter__())
            g_x = self.generator(x, training=False)
            stack = tf.stack([x, g_x], axis=0) * 0.5 + 0.5
            stack = tf.squeeze(stack)
            with writer.as_default():
                tf.summary.image('prediction', stack, step=epoch, max_outputs=2)

    @staticmethod
    def _get_writers(log_dir):
        time = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        log_path = f'{log_dir}/{time}/'
        writer_train = tf.summary.create_file_writer(log_path + 'train')
        writer_val = tf.summary.create_file_writer(log_path + 'validation')

        return writer_train, writer_val
