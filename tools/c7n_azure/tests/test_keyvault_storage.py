# Copyright 2019 Microsoft Corporation
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

import azure.keyvault.http_bearer_challenge_cache as kv_cache
from azure_common import BaseTest, arm_template, cassette_name


class KeyVaultStorageTest(BaseTest):

    def tearDown(self, *args, **kwargs):
        super(KeyVaultStorageTest, self).tearDown(*args, **kwargs)
        kv_cache._cache = {}

    def test_key_vault_storage_schema_validate(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-storage',
        }, validate=True)
        self.assertTrue(p)

    @arm_template('keyvault.json')
    def test_key_vault_storage_query(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-storage',
            'filters': [
                {
                    'type': 'parent',
                    'filter': {
                        'type': 'value',
                        'key': 'name',
                        'op': 'glob',
                        'value': 'cckeyvault1*'
                    }
                },
            ]
        }, validate=True, cache=True)
        resources = p.run()
        self.assertEqual(len(resources), 2)

    @arm_template('keyvault.json')
    @cassette_name('filter')
    def test_key_vault_storage_filter_auto_regenerate(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-storage',
            'filters': [
                {
                    'type': 'parent',
                    'filter': {
                        'type': 'value',
                        'key': 'name',
                        'op': 'glob',
                        'value': 'cckeyvault1*'
                    }
                },
                {
                    'type': 'auto-regenerate',
                    'value': False
                }
            ]
        }, validate=True, cache=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('keyvault.json')
    @cassette_name('filter')
    def test_key_vault_storage_filter_regeneration_period(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-storage',
            'filters': [
                {
                    'type': 'parent',
                    'filter': {
                        'type': 'value',
                        'key': 'name',
                        'op': 'glob',
                        'value': 'cckeyvault1*'
                    }
                },
                {
                    'type': 'regeneration-period',
                    'value': 'P90D'
                }
            ]
        }, validate=True, cache=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('keyvault.json')
    @cassette_name('filter')
    def test_key_vault_storage_filter_active_key_name(self):
        p = self.load_policy({
            'name': 'test-key-vault',
            'resource': 'azure.keyvault-storage',
            'filters': [
                {
                    'type': 'parent',
                    'filter': {
                        'type': 'value',
                        'key': 'name',
                        'op': 'glob',
                        'value': 'cckeyvault1*'
                    }
                },
                {
                    'type': 'active-key-name',
                    'value': 'key1'
                }
            ]
        }, validate=True, cache=True)
        resources = p.run()
        self.assertEqual(len(resources), 1)
