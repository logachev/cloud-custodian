# Copyright 2015-2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import, division, print_function, unicode_literals

from azure_common import BaseTest, arm_template, cassette_name


class BaseResourceTest(BaseTest):
    resource = None
    resource_name_prefix = None

    @classmethod
    def setUpClass(cls):
        cls._test_methods = []
        if cls is BaseResourceTest:
            for name in dir(cls):
                if name.startswith('test') and callable(getattr(cls, name)):
                    cls._test_methods.append((name, getattr(cls, name)))
                    setattr(cls, name, lambda self: None)

    @classmethod
    def tearDownClass(cls):
        if cls is BaseResourceTest:
            for name, method in cls._test_methods:
                setattr(cls, name, method)
            cls._test_methods = []

    def validate_schema(self, filters=[], actions=[]):
        self.assertTrue(self._get_policy(filters=filters, actions=actions, validate=True))

    def verify_exists(self):
        p = self._get_policy()
        resources = p.run()
        self.assertEqual(len(resources), 1)

    def _get_policy(self, filters=[], actions=[], validate=False):
        return self.load_policy({
            'name': 'test',
            'resource': self.resource,
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value': self.resource_name_prefix + '*'}] + filters,
            'actions': actions
        }, validate=validate)

#del BaseResourceTest
