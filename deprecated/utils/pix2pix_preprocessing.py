import tensorflow as tf

IMG_HEIGHT = 256
IMG_WIDTH = 512
RESIZE_FACTOR = 1.1


def load(input_path, real_path):
    paths = [input_path, real_path]
    images = []
    for path in paths:
        # Loading the image
        image = tf.io.read_file(path)
        image = tf.image.decode_png(image, channels=3)
        image = tf.cast(image, tf.float32)
        images.append(image)
    return images[0], images[1]


def resize(input_image, real_image, height, width):
    input_image = tf.image.resize(input_image, [height, width],
                                  method=tf.image.ResizeMethod.NEAREST_NEIGHBOR)
    real_image = tf.image.resize(real_image, [height, width],
                                 method=tf.image.ResizeMethod.NEAREST_NEIGHBOR)
    return input_image, real_image


def normalize(input_image, real_image):
    input_image = (input_image / 127.5) - 1
    real_image = (real_image / 127.5) - 1

    return input_image, real_image


def random_crop(input_image, real_image):
    stacked_image = tf.stack([input_image, real_image], axis=0)
    cropped_image = tf.image.random_crop(stacked_image, size=[2, IMG_HEIGHT, IMG_WIDTH, 3])

    return cropped_image[0], cropped_image[1]


@tf.function()
def random_jitter(input_image, real_image):
    resized_width = round(IMG_WIDTH * RESIZE_FACTOR)
    resized_height = round(IMG_HEIGHT * RESIZE_FACTOR)

    # Resize
    input_image, real_image = resize(input_image, real_image, resized_height, resized_width)
    # Random crop
    input_image, real_image = random_crop(input_image, real_image)

    if tf.random.uniform(()) > 0.5:
        # random mirroring
        input_image = tf.image.flip_left_right(input_image)
        real_image = tf.image.flip_left_right(real_image)

    return input_image, real_image


def load_images_train(input_path, real_path):
    input_image, real_image = load(input_path, real_path)
    input_image, real_image = random_jitter(input_image, real_image)
    input_image, real_image = normalize(input_image, real_image)

    return input_image, real_image


def load_images_test(input_path, real_path):
    input_image, real_image = load(input_path, real_path)
    input_image, real_image = resize(input_image, real_image, IMG_HEIGHT, IMG_WIDTH)
    input_image, real_image = normalize(input_image, real_image)

    return input_image, real_image


def load_images_predict(path):
    image = tf.io.read_file(path)
    image = tf.image.decode_png(image, channels=3)
    image = tf.cast(image, tf.float32)
    image = tf.image.resize(image, [IMG_HEIGHT, IMG_WIDTH], method=tf.image.ResizeMethod.NEAREST_NEIGHBOR)
    image = (image / 127.5) - 1
    return image


def load_single_image(path):
    # Loading
    image = tf.io.read_file(path)
    image = tf.image.decode_png(image)
    image = tf.cast(image, tf.float32)
    # Resizing
    image = tf.image.resize(image, [IMG_HEIGHT, IMG_WIDTH],
                            method=tf.image.ResizeMethod.NEAREST_NEIGHBOR)
    # Normalizing
    image = (image / 127.5) - 1
    # Adding dims
    image = tf.expand_dims(image, 0)

    return image
