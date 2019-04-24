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

from azure.mgmt.storage.models import StorageAccountUpdateParameters, DefaultAction, IPRule, \
    VirtualNetworkRule
from azure_common import BaseTest, arm_template
from c7n_azure.resources.storage import StorageSetNetworkRulesAction
from c7n_azure.session import Session
from mock import MagicMock

from c7n.utils import local_session

rg_name = 'test_storage'


class StorageTestFirewall(BaseTest):

    @arm_template('storage.json')
    def test_network_ip_rules_action(self):
        subscription_id = local_session(Session).get_subscription_id()
        subnet_id = '/subscriptions/{0}/' \
                    'resourceGroups/{1}/' \
                    'providers/Microsoft.Network/' \
                    'virtualNetworks/{2}/subnets/{3}'
        id1 = subnet_id.format(subscription_id, 'test_storage', 'cctstoragevnet1', 'testsubnet1')
        id2 = subnet_id.format(subscription_id, 'test_storage', 'cctstoragevnet2', 'testsubnet2')
        self.addCleanup(self._cleanup)

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
                 'bypass': ['Metrics'],
                 'ip-rules': [
                     {'ip-address-or-range': '11.12.13.14'},
                     {'ip-address-or-range': '21.22.23.24'}
                 ],
                 'virtual-network-rules': [
                     {'virtual-network-resource-id': id1},
                     {'virtual-network-resource-id': id2}
                 ]}
            ]
        })

        p_add.run()

        resources = self._get_resources()
        self.assertEqual(len(resources), 1)

        action = resources[0]['properties']['networkAcls']['defaultAction']
        self.assertEqual(action, 'Deny')

        bypass = resources[0]['properties']['networkAcls']['bypass']
        self.assertEqual(bypass, 'Metrics')

        ip_rules = resources[0]['properties']['networkAcls']['ipRules']
        self.assertEqual(len(ip_rules), 2)
        self.assertEqual(ip_rules[0]['value'], '11.12.13.14')
        self.assertEqual(ip_rules[1]['value'], '21.22.23.24')
        self.assertEqual(ip_rules[0]['action'], 'Allow')
        self.assertEqual(ip_rules[1]['action'], 'Allow')

        rules = resources[0]['properties']['networkAcls']['virtualNetworkRules']
        self.assertEqual(len(rules), 2)
        self.assertEqual(rules[0]['id'], id1)
        self.assertEqual(rules[1]['id'], id2)
        self.assertEqual(rules[0]['action'], 'Allow')
        self.assertEqual(rules[1]['action'], 'Allow')

    def test_deny_action(self):
        data = {'type': 'set-network-rules',
                'default-action': 'Allow'}
        rules = self._emulate_set_network_rules_action(data)

        self.assertEqual(rules.default_action, 'Allow')
        self.assertEqual(rules.bypass, 'None')

    def test_bypass(self):
        data = {'type': 'set-network-rules',
                'default-action': 'Deny',
                'bypass': ['Logging', 'Metrics']}
        rules = self._emulate_set_network_rules_action(data)

        self.assertEqual(rules.default_action, 'Deny')
        self.assertEqual(rules.bypass, 'Logging,Metrics')

    def test_ip_rules(self):
        data = {'type': 'set-network-rules',
                'default-action': 'Deny',
                'ip-rules': [
                    {'ip-address-or-range': '127.0.0.1'},
                    {'ip-address-or-range': '127.0.0.1-127.0.0.2'}]
                }
        rules = self._emulate_set_network_rules_action(data)

        self.assertEqual(rules.default_action, 'Deny')
        self.assertEqual(len(rules.ip_rules), 2)
        self.assertEqual(rules.ip_rules[0],
                         IPRule(ip_address_or_range='127.0.0.1', action='Allow'))
        self.assertEqual(rules.ip_rules[1],
                         IPRule(ip_address_or_range='127.0.0.1-127.0.0.2', action='Allow'))

    def test_virtual_network_rules(self):
        data = {'type': 'set-network-rules',
                'default-action': 'Deny',
                'virtual-network-rules': [
                    {'virtual-network-resource-id': 'id_1'},
                    {'virtual-network-resource-id': 'id_2'}]
                }
        rules = self._emulate_set_network_rules_action(data)

        self.assertEqual(rules.default_action, 'Deny')
        self.assertEqual(len(rules.virtual_network_rules), 2)
        self.assertEqual(rules.virtual_network_rules[0],
                         VirtualNetworkRule(virtual_network_resource_id='id_1', action='Allow'))
        self.assertEqual(rules.virtual_network_rules[1],
                         VirtualNetworkRule(virtual_network_resource_id='id_2', action='Allow'))

    def _get_resources(self):
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

        return resources

    def _cleanup(self):
        client = local_session(Session).client('azure.mgmt.storage.StorageManagementClient')
        resources = list(client.storage_accounts.list_by_resource_group(rg_name))
        self.assertEqual(len(resources), 1)
        resource = resources[0]
        resource.network_rule_set.ip_rules = []
        resource.network_rule_set.virtual_network_rules = []
        resource.network_rule_set.bypass = 'AzureServices'
        resource.network_rule_set.default_action = DefaultAction.allow
        client.storage_accounts.update(
            rg_name,
            resource.name,
            StorageAccountUpdateParameters(network_rule_set=resource.network_rule_set))

    def _emulate_set_network_rules_action(self, data):
        resource = {'resourceGroup': 'testRG', 'name': 'testName'}
        action = StorageSetNetworkRulesAction(data=data)
        action.client = MagicMock()
        action._process_resource(resource)
        update = action.client.storage_accounts.update

        self.assertEqual(len(update.call_args_list), 1)
        self.assertEqual(len(update.call_args_list[0][0]), 3)
        self.assertEqual(update.call_args_list[0][0][0], 'testRG')
        self.assertEqual(update.call_args_list[0][0][1], 'testName')
        return update.call_args_list[0][0][2].network_rule_set
