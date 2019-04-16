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

from azure_common import BaseTest, arm_template


class StorageTest(BaseTest):
    def setUp(self):
        super(StorageTest, self).setUp()
        self.cleanup_policy = self.load_policy({
            'name': 'test-azure-storage-cleanup',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}],
            'actions': [
                {'type': 'set-network-rules',
                 'default-action': 'Allow',
                 'ip-rules': [],
                 'virtual-network-rules': []}
            ]
        })

    def test_storage_schema_validate(self):
        with self.sign_out_patch():
            p = self.load_policy({
                'name': 'test-storage',
                'resource': 'azure.storage'
            }, validate=True)
            self.assertTrue(p)

    @arm_template('storage.json')
    def test_value_filter(self):
        p = self.load_policy({
            'name': 'test-azure-storage-enum',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}],
        })
        resources = p.run()
        self.assertEqual(len(resources), 1)

    @arm_template('storage.json')
    def test_network_ip_rules_action(self):
        self.cleanup_policy.run()

        p_add = self.load_policy({
            'name': 'test-azure-storage-add-ips',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}],
            'actions': [
                {'type': 'set-network-rules',
                 'default-action': 'Deny',
                 'bypass': ['Logging', 'Metrics'],
                 'ip-rules': [
                     {'ip-address-or-range': '11.12.13.14'},
                     {'ip-address-or-range': '21.22.23.24'}
                 ]}
            ]
        })

        p_add.run()

        p_get = self.load_policy({
            'name': 'test-azure-storage-enum',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}],
        })

        resources = p_get.run()
        self.assertEqual(len(resources), 1)
        ip_rules = resources[0]['properties']['networkAcls']['ipRules']
        self.assertEqual(len(ip_rules), 2)
        self.assertEqual(ip_rules[0]['value'], '11.12.13.14')
        self.assertEqual(ip_rules[1]['value'], '21.22.23.24')
        self.assertEqual(ip_rules[0]['action'], 'Allow')
        self.assertEqual(ip_rules[1]['action'], 'Allow')

        self.cleanup_policy.run()
        resources = p_get.run()
        ip_rules = resources[0]['properties']['networkAcls']['ipRules']
        self.assertEqual(len(ip_rules), 0)

    @arm_template('storage.json')
    def test_virtual_network_rules_action(self):
        resources = self.cleanup_policy.run()

        p_vnet_get = self.load_policy({
            'name': 'test-azure-storage-enum',
            'resource': 'azure.vnet',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstoragevnet*'}],
        })

        vnets = p_vnet_get.run()

        id1 = vnets[0]['properties']['subnets'][0]['id']
        id2 = vnets[1]['properties']['subnets'][0]['id']

        p_add = self.load_policy({
            'name': 'test-azure-storage-add-ips',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}],
            'actions': [
                {'type': 'set-network-rules',
                 'default-action': 'Deny',
                 'bypass': ['Logging', 'Metrics'],
                 'virtual-network-rules': [
                     {'virtual-network-resource-id': id1},
                     {'virtual-network-resource-id': id2}
                 ]}
            ]
        })

        p_add.run()

        p_get = self.load_policy({
            'name': 'test-azure-storage-enum',
            'resource': 'azure.storage',
            'filters': [
                {'type': 'value',
                 'key': 'name',
                 'op': 'glob',
                 'value_type': 'normalize',
                 'value': 'cctstorage*'}],
        })

        resources = p_get.run()
        self.assertEqual(len(resources), 1)
        rules = resources[0]['properties']['networkAcls']['virtualNetworkRules']
        self.assertEqual(len(rules), 2)
        self.assertEqual(rules[0]['id'], id1)
        self.assertEqual(rules[1]['id'], id2)
        self.assertEqual(rules[0]['action'], 'Allow')
        self.assertEqual(rules[1]['action'], 'Allow')

        self.cleanup_policy.run()
        resources = p_get.run()
        rules = resources[0]['properties']['networkAcls']['virtualNetworkRules']
        self.assertEqual(len(rules), 0)
