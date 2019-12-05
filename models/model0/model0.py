from __future__ import absolute_import, division, print_function, unicode_literals

import tensorflow as tf

import os
import time
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from IPython.display import clear_output

import glob
from random import shuffle

from itertools import compress

from models.pix2pix import pix2pix_preprocessing as preprocessing


class Model0:
    """
    Variación de pix2pix con un paso doble en el entrenamiento
    """
    def __init__(self, *, img_width = 512, img_height = 256, epochs = 200, save_path = None):
        self.img_width = img_width
        preprocessing.IMG_WIDTH = img_width
        self.img_height = img_height
        preprocessing.IMG_HEIGHT = img_height
        
        self.epochs = epochs        
        
        self.LAMBDA = 100
        self.SECOND_PASS_LAMBDA = 1.25
        
        self.generator_optimizer = tf.keras.optimizers.Adam(2e-4, beta_1=0.5)
        self.discriminator_optimizer = tf.keras.optimizers.Adam(2e-4, beta_1=0.5)
        
        self.loss_object = tf.keras.losses.BinaryCrossentropy(from_logits=True)
        
        self.generator = self.generator()
        self.discriminator = self.discriminator()
        
        self.save_path = save_path
        if self.save_path != None:
            if not os.path.exists(self.save_path):
                os.makedirs(self.save_path)
        
        # Metricas para el display
        # Train
        self.train_loss_disc = tf.keras.metrics.Mean(name = 'train_loss_disc')
        self.train_loss_gen = tf.keras.metrics.Mean(name = 'train_loss_gen')
        
        self.train_acc_real = tf.keras.metrics.BinaryAccuracy(name = 'train_acc_real', threshold = 0.2)
        self.train_acc_generated = tf.keras.metrics.BinaryAccuracy(name = 'train_acc_generated', threshold = 0.2)
        
        self.stats = pd.DataFrame(columns = ['train loss disc', 'train loss gen', 'train acc real', 'train acc generated'])
        
#         self.plot_train_loss_disc = []
#         self.plot_train_loss_gen = []
#         self.plot_train_acc_real = []
#         self.plot_train_acc_generated = []
        
        # Test
        self.test_loss = tf.keras.metrics.Mean(name = 'test_loss')
        
        self.test_acc_real = tf.keras.metrics.BinaryAccuracy(name = 'test_acc_real', threshold = 0.2)
        self.test_acc_generated = tf.keras.metrics.BinaryAccuracy(name = 'test_acc_generated', threshold = 0.2)
     
        
        
        
    # dataset creation function
    def gen_dataset(self, *, input_path, real_path, repeat_real = 1):
        BUFFER_SIZE = len(input_path)
        BATCH_SIZE = 1
        
        test_mask = ([False] * (len(real_path)//100 * 8) + [True] * (len(real_path)//100 * 2)) * 10
        train_mask = ([True] * (len(real_path)//100 * 8) + [False] * (len(real_path)//100 * 2)) * 10
        
        train_input = list(compress(input_path, train_mask * repeat_real))
        train_real = list(compress(real_path, train_mask))

        test_input = list(compress(input_path, test_mask * repeat_real))
        test_real = list(compress(real_path, test_mask))
        
        # train
        input_dataset = tf.data.Dataset.list_files(train_input, shuffle=False)
        real_datset = tf.data.Dataset.list_files(train_real, shuffle=False)
        real_datset = real_datset.repeat(repeat_real)

        train_dataset = tf.data.Dataset.zip((input_dataset, real_datset))
        train_dataset = train_dataset.map(preprocessing.load_images_train).shuffle(BUFFER_SIZE).batch(BATCH_SIZE)
        
        # test
        test_input_ds = tf.data.Dataset.list_files(test_input, shuffle = False)
        test_real_ds = tf.data.Dataset.list_files(test_real, shuffle = False)
        test_real_ds = test_real_ds.repeat(repeat_real)

        test_dataset = tf.data.Dataset.zip((test_input_ds, test_real_ds))
        test_dataset = test_dataset.map(preprocessing.load_images_test).batch(BATCH_SIZE)
        
        return train_dataset, test_dataset
    
    
    # Creación de la red
    class buildingblocks:
        def downsample(filters, size, apply_batchnorm = True):
            initializer = tf.random_normal_initializer(0., 0.02)

            result = tf.keras.Sequential()
            result.add(tf.keras.layers.Conv2D(filters, size, strides=2, padding='same',
                                              kernel_initializer = initializer, use_bias=False))

            if apply_batchnorm:
                result.add(tf.keras.layers.BatchNormalization())

            result.add(tf.keras.layers.LeakyReLU())

            return result

        def upsample(filters, size, apply_dropout=False):
            initializer = tf.random_normal_initializer(0., 0.02)

            result = tf.keras.Sequential()
            result.add(tf.keras.layers.Conv2DTranspose(filters, size, strides=2, padding='same',
                                                       kernel_initializer=initializer, use_bias=False))

            result.add(tf.keras.layers.BatchNormalization())

            if apply_dropout:
                result.add(tf.keras.layers.Dropout(0.5))

            result.add(tf.keras.layers.ReLU())

            return result
    
    def generator(self):
        down_stack = [
            # (256, 512)
            self.buildingblocks.downsample(64, 4, apply_batchnorm=False), # 128, 256
            self.buildingblocks.downsample(128, 4), # 64, 128
            self.buildingblocks.downsample(256, 4), # 32, 64
            self.buildingblocks.downsample(512, 4), # 16, 32
            self.buildingblocks.downsample(512, 4), # 8, 16
            self.buildingblocks.downsample(512, 4), # 4, 8
            self.buildingblocks.downsample(512, 4), # 2, 4
            self.buildingblocks.downsample(512, 4)
        ]

        up_stack = [
            self.buildingblocks.upsample(512, 4, apply_dropout=True), 
            self.buildingblocks.upsample(512, 4, apply_dropout=True), 
            self.buildingblocks.upsample(512, 4, apply_dropout=True), 
            self.buildingblocks.upsample(512, 4), 
            self.buildingblocks.upsample(256, 4), 
            self.buildingblocks.upsample(128, 4), 
            self.buildingblocks.upsample(64, 4), 
        ]

        initializer = tf.random_normal_initializer(0., 0.02)
        last = tf.keras.layers.Conv2DTranspose(3, 4, strides=2, padding='same',
                                               kernel_initializer=initializer, activation='tanh')

        concat = tf.keras.layers.Concatenate()

        inputs = tf.keras.layers.Input(shape=[None, None, 3])
        x = inputs

        # downsampling
        skips = []
        for down in down_stack:
            x = down(x)
            skips.append(x)

        skips = reversed(skips[:-1])

        # upsampling and connecting
        for up, skip in zip(up_stack, skips):
            x = up(x)
            x = concat([x, skip])

        x = last(x)

        return tf.keras.Model(inputs=inputs, outputs=x)
    

    def discriminator(self):
        initializer = tf.random_normal_initializer(0., 0.02)

        inp = tf.keras.layers.Input(shape=[None, None, 3], name='input_image')
        tar = tf.keras.layers.Input(shape=[None, None, 3], name='target_image')

        x = tf.keras.layers.concatenate([inp, tar]) # (bs, 256, 256, channels*2)

        down1 = self.buildingblocks.downsample(64, 4, apply_batchnorm=False)(inp) # (bs, 128, 128, 64)
        down2 = self.buildingblocks.downsample(128, 4)(down1) # (bs, 64, 64, 128)
        down3 = self.buildingblocks.downsample(256, 4)(down2) # (bs, 32, 32, 256)

        zero_pad1 = tf.keras.layers.ZeroPadding2D()(down3) # (bs, 34, 34, 256)
        conv = tf.keras.layers.Conv2D(512, 4, strides=1,
                                kernel_initializer=initializer,
                                use_bias=False)(zero_pad1) # (bs, 31, 31, 512)

        batchnorm1 = tf.keras.layers.BatchNormalization()(conv)

        leaky_relu = tf.keras.layers.LeakyReLU()(batchnorm1)

        zero_pad2 = tf.keras.layers.ZeroPadding2D()(leaky_relu) # (bs, 33, 33, 512)

        last = tf.keras.layers.Conv2D(1, 4, strides=1,
                                kernel_initializer=initializer)(zero_pad2) # (bs, 30, 30, 1)

        return tf.keras.Model(inputs=inp, outputs=last)
    
    # Metricas
    def discriminator_loss(self, disc_real_output, disc_generated_output):
        real_loss = self.loss_object(tf.ones_like(disc_real_output), disc_real_output)

        generated_loss = self.loss_object(tf.zeros_like(disc_generated_output), disc_generated_output)

        total_disc_loss = real_loss + generated_loss

        return total_disc_loss
        
    def generator_loss(self, disc_generated_output, gen_output, target):
        gan_loss = self.loss_object(tf.ones_like(disc_generated_output), disc_generated_output)

        # mean absolute error
        l1_loss = tf.reduce_mean(tf.abs(target - gen_output))

        total_gen_loss = gan_loss + (self.LAMBDA * l1_loss)

        return total_gen_loss
    
    # Funciones de entrenamiento
    @tf.function
    def train_step(self, input_image, target):
        with tf.GradientTape() as gen_tape, tf.GradientTape() as disc_tape:
            
            # Primer ciclo
            gen_output_first_pass = self.generator(input_image, training=True)
            
            disc_real_output_first_pass = self.discriminator([input_image, target], training=True)
            disc_generated_output_first_pass = self.discriminator([input_image, gen_output_first_pass], training=True)
           
            gen_loss_first_pass = self.generator_loss(disc_generated_output_first_pass, gen_output_first_pass, target)
            disc_loss_first_pass = self.discriminator_loss(disc_real_output_first_pass, disc_generated_output_first_pass)
            
            # Segundo ciclo
            gen_output_second_pass = self.generator(gen_output_first_pass, training = True)
            
            # disc_real_output_second_pass es igual al del primer ciclo
            disc_generated_output_second_pass = self.discriminator([input_image, gen_output_second_pass], training = True)
            
            gen_loss_second_pass = self.generator_loss(disc_generated_output_second_pass, gen_output_second_pass, target)
            disc_loss_second_pass = self.discriminator_loss(disc_real_output_first_pass, disc_generated_output_second_pass)
            
            gen_loss = gen_loss_first_pass + self.SECOND_PASS_LAMBDA * gen_loss_second_pass
            disc_loss = disc_loss_first_pass + disc_loss_second_pass
            
        generator_gradients = gen_tape.gradient(gen_loss, self.generator.trainable_variables)
        discriminator_gradients = disc_tape.gradient(disc_loss, self.discriminator.trainable_variables)

        self.generator_optimizer.apply_gradients(zip(generator_gradients, self.generator.trainable_variables))
        self.discriminator_optimizer.apply_gradients(zip(discriminator_gradients, self.discriminator.trainable_variables))
        
        # Actualización de métricas
        self.train_loss_disc(disc_loss)
        self.train_loss_gen(gen_loss)
        
        self.train_acc_real(tf.ones_like(disc_real_output_first_pass), disc_real_output_first_pass)
        self.train_acc_generated(tf.zeros_like(disc_generated_output_second_pass), disc_generated_output_second_pass)

    def fit(self, train_ds, test_ds):
        # Se toman imagenes para apreciar la evolucion del modelo
        for (train_input, train_target), (test_input, test_target) in zip(train_ds.take(1), test_ds.take(1)):
            plot_train_input = train_input
            plot_train_target = train_target
            plot_test_input = test_input
            plot_test_target = test_target
        
        for epoch in range(self.epochs):
            start = time.time()
            # Train
            for input_image, target in train_ds:
                self.train_step(input_image, target)

            clear_output(wait=True)
            
            # Metricas
            template = 'Epoch {}\ntrain loss disc: {}, train loss gen: {}\ntrain acc real: {:.2f}, train acc generated: {:.2f}\ntime taken: {:.2f}'
            print(template.format(epoch + 1,
                                  self.train_loss_disc.result(),
                                  self.train_loss_gen.result(),
                                  self.train_acc_real.result()*100,
                                  self.train_acc_generated.result()*100,
                                  time.time()-start))
            
            self.stats = self.stats.append(pd.DataFrame([[self.train_loss_disc.result(), self.train_loss_gen.result(), self.train_acc_real.result()*100, self.train_acc_generated.result()*100]], columns = self.stats.columns), ignore_index = True)
            
            self.train_loss_disc.reset_states()
            self.train_loss_gen.reset_states()
        
            self.train_acc_real.reset_states()
            self.train_acc_generated.reset_states()
            
            # Imagenes
            if ((epoch + 1) % 5 == 0 or epoch == 0) and self.save_path != None:
                self.generate_images(self.generator, plot_train_input, plot_train_target, plot_test_input, plot_test_target, epoch + 1)
        
        self.stats.to_csv('stats_model0.csv', index = False)

    # Generación de imágenes
    def generate_images(self, model, train_inp, train_tar, test_inp, test_tar, epoch):

        train_images = [train_inp, train_tar, model(train_inp, training = False)]
        test_images = [test_inp, test_tar, model(test_inp, training = False)]
        plot_images = [train_images, test_images]

        title = ['{} input Image', '{} ground truth', '{} predicted image']

        fig, ax = plt.subplots(len(plot_images), len(plot_images[0]), figsize  = (30, 10))
        for i, image_list in enumerate(plot_images):
            for j, image in enumerate(image_list):

                ax[i, j].imshow(image[0, :, :, :] * 0.5 + 0.5)
                ax[i, j].axis('off')

                if i == 0:
                    ax[i, j].set_title(title[j].format('Train'))
                else:
                    ax[i, j].set_title(title[j].format('Test'))
        plt.axis('off')

        clear_output(wait=True)
        plt.savefig(f'{self.save_path}/image_epoch{epoch}.png', pad_inches = None, bbox_inches = 'tight')
        plt.show()