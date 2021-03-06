# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
test_compute
----------------------------------

Functional tests for `shade` image methods.
"""

import filecmp
import os
import tempfile

from shade.tests.functional import base
from shade.tests.functional.util import pick_image


class TestImage(base.BaseFunctionalTestCase):
    def setUp(self):
        super(TestImage, self).setUp()
        self.image = pick_image(self.demo_cloud.nova_client.images.list())

    def test_create_image(self):
        test_image = tempfile.NamedTemporaryFile(delete=False)
        test_image.write('\0' * 1024 * 1024)
        test_image.close()
        image_name = self.getUniqueString('image')
        try:
            self.demo_cloud.create_image(
                name=image_name,
                filename=test_image.name,
                disk_format='raw',
                container_format='bare',
                min_disk=10,
                min_ram=1024,
                wait=True)
        finally:
            self.demo_cloud.delete_image(image_name, wait=True)

    def test_download_image(self):
        test_image = tempfile.NamedTemporaryFile(delete=False)
        self.addCleanup(os.remove, test_image.name)
        test_image.write('\0' * 1024 * 1024)
        test_image.close()
        image_name = self.getUniqueString('image')
        self.demo_cloud.create_image(
            name=image_name,
            filename=test_image.name,
            disk_format='raw',
            container_format='bare',
            min_disk=10,
            min_ram=1024,
            wait=True)
        self.addCleanup(self.demo_cloud.delete_image, image_name, wait=True)
        output = os.path.join(tempfile.gettempdir(), self.getUniqueString())
        self.demo_cloud.download_image(image_name, output)
        self.addCleanup(os.remove, output)
        self.assertTrue(filecmp.cmp(test_image.name, output),
                        "Downloaded contents don't match created image")

    def test_create_image_skip_duplicate(self):
        test_image = tempfile.NamedTemporaryFile(delete=False)
        test_image.write('\0' * 1024 * 1024)
        test_image.close()
        image_name = self.getUniqueString('image')
        try:
            first_image = self.demo_cloud.create_image(
                name=image_name,
                filename=test_image.name,
                disk_format='raw',
                container_format='bare',
                min_disk=10,
                min_ram=1024,
                wait=True)
            second_image = self.demo_cloud.create_image(
                name=image_name,
                filename=test_image.name,
                disk_format='raw',
                container_format='bare',
                min_disk=10,
                min_ram=1024,
                wait=True)
            self.assertEqual(first_image.id, second_image.id)
        finally:
            self.demo_cloud.delete_image(image_name, wait=True)

    def test_create_image_force_duplicate(self):
        test_image = tempfile.NamedTemporaryFile(delete=False)
        test_image.write('\0' * 1024 * 1024)
        test_image.close()
        image_name = self.getUniqueString('image')
        first_image = None
        second_image = None
        try:
            first_image = self.demo_cloud.create_image(
                name=image_name,
                filename=test_image.name,
                disk_format='raw',
                container_format='bare',
                min_disk=10,
                min_ram=1024,
                wait=True)
            second_image = self.demo_cloud.create_image(
                name=image_name,
                filename=test_image.name,
                disk_format='raw',
                container_format='bare',
                min_disk=10,
                min_ram=1024,
                allow_duplicates=True,
                wait=True)
            self.assertNotEqual(first_image.id, second_image.id)
        finally:
            if first_image:
                self.demo_cloud.delete_image(first_image.id, wait=True)
            if second_image:
                self.demo_cloud.delete_image(second_image.id, wait=True)

    def test_create_image_update_properties(self):
        test_image = tempfile.NamedTemporaryFile(delete=False)
        test_image.write('\0' * 1024 * 1024)
        test_image.close()
        image_name = self.getUniqueString('image')
        try:
            image = self.demo_cloud.create_image(
                name=image_name,
                filename=test_image.name,
                disk_format='raw',
                container_format='bare',
                min_disk=10,
                min_ram=1024,
                wait=True)
            self.demo_cloud.update_image_properties(
                image=image,
                name=image_name,
                foo='bar')
            image = self.demo_cloud.get_image(image_name)
            self.assertIn('foo', image.properties)
            self.assertEqual(image.properties['foo'], 'bar')
        finally:
            self.demo_cloud.delete_image(image_name, wait=True)
