import shutil
import tempfile
import tensorflow as tf
import unittest

from models import ResNet


@unittest.skip("Fails in Travis")
class TestTrain(unittest.TestCase):
    def setUp(self) -> None:
        image = tf.random.normal((5, 512, 512, 3))
        x = y = tf.data.Dataset.from_tensor_slices(image)
        self.dataset = tf.data.Dataset.zip((x, y)).batch(1)

        self.tempdir = tempfile.TemporaryDirectory()

    def test_resnet(self):
        resnet = ResNet()
        resnet.fit(self.dataset, 1, path=self.tempdir.name)