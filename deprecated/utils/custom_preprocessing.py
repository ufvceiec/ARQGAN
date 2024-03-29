import tensorflow as tf

IMG_WIDTH = 512
IMG_HEIGHT = 384

TGT_WIDTH = 512
TGT_HEIGHT = 256

RESIZE_FACTOR = 1.3

# mask - pink color
r = b = tf.fill((TGT_WIDTH, TGT_HEIGHT), 1.0)
g = tf.fill((TGT_WIDTH, TGT_HEIGHT), 0.0)
mask = tf.stack((r, g, b), axis=2)
mask = tf.cast(mask, dtype='float32')


def load_images_train(*paths):
    images = load(paths)
    images = random_jitter(images)
    images = normalize(images)
    return images


def load_images_val(*paths):
    images = load(paths)
    images = resize(IMG_WIDTH, IMG_HEIGHT, images)
    images = central_crop(images)
    images = normalize(images)
    return images


def central_crop(images):
    stack = tf.stack(images)
    offset_height = (IMG_HEIGHT - TGT_HEIGHT) // 2
    crop = tf.image.crop_to_bounding_box(stack, offset_height=offset_height, offset_width=0, target_height=TGT_HEIGHT,
                                         target_width=TGT_WIDTH)
    crop = tf.unstack(crop, num=len(images))
    return crop


def load(paths):
    images = []
    for path in paths:
        image = tf.io.read_file(tf.squeeze(path))
        image = tf.image.decode_png(image, channels=3)
        image = tf.cast(image, tf.float32)
        images.append(image)
    return images


# @tf.function
def random_jitter(images):
    new_width = round(IMG_WIDTH * RESIZE_FACTOR)
    new_height = round(IMG_HEIGHT * RESIZE_FACTOR)

    images = resize(new_width, new_height, images)
    images = random_crop(images)

    if tf.random.uniform(()) > 0.5:
        flipped_images = []
        for image in images:
            flipped_image = tf.image.flip_left_right(image)
            flipped_images.append(flipped_image)
        return flipped_images
    return images


def resize(width, height, images):
    resized_images = []
    for image in images:
        resized_image = tf.image.resize(image, [height, width],
                                        method=tf.image.ResizeMethod.NEAREST_NEIGHBOR)
        resized_images.append(resized_image)
    return resized_images


def random_crop(images):
    stack = tf.stack(images)
    crop = tf.image.random_crop(stack, size=[len(images), TGT_HEIGHT, TGT_WIDTH, 3])
    crop = tf.unstack(crop, num=len(images))
    return crop


def normalize(images):
    normalized_images = []
    for image in images:
        normalized_image = (image / 127.5) - 1
        normalized_images.append(normalized_image)

    return normalized_images


def load_images_mask_train(*paths):
    images = load(paths)
    images = create_mask(images)
    images = random_jitter(images)
    images = normalize(images)
    return images


def load_images_mask_val(*paths):
    images = load(paths)
    images = create_mask(images)
    images = resize(IMG_WIDTH, IMG_HEIGHT, images)
    images = central_crop(images)
    images = normalize(images)
    return images


def load_images_pink_mask(*paths):
    images = load(paths)
    images = get_mask(images)
    images = random_jitter(images)
    images = normalize(images)
    return images


def get_mask(images):
    # images[0] are the segmented temple ruins
    # images[1] is the segmented temple
    # images[2] is the true color temple
    # compare the two images
    comparison = tf.where(images[0] == images[1], 0, 1)
    # if all the pixel's values are the same, the sum will be 0, eg. [0, 0, 0] vs [1, 0, 1]
    # this gives us a 2D matrix with zeros where the pixels are the same and ones where they are not
    comparison = tf.reduce_sum(comparison, axis=2)
    comparison = tf.expand_dims(comparison, axis=2)
    # we keep the real image where they are the same, and put the mask where they differ
    image = tf.where(comparison == 0, images[2], mask)
    print(images[2].shape, image.shape)
    return images[2], image


def create_mask(images):
    # black pixels will add up to 0 (0, 0, 0)
    added = tf.math.reduce_sum(images[1], 2)
    mask = tf.math.equal(added, 0)
    mask_colored = tf.where(tf.math.not_equal(mask, tf.zeros_like(mask)), 0, 255)
    # mask_colored = tf.expand_dims(mask_colored, 2)
    mask_colored = tf.cast(mask_colored, dtype='float32')
    stack = tf.stack([mask_colored, mask_colored, mask_colored], axis=2)
    images[1] = stack

    return images
