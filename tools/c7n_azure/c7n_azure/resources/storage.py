# Copyright 2018 Capital One Services, LLC
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

from azure.mgmt.storage.models import IPRule, \
    NetworkRuleSet, StorageAccountUpdateParameters, VirtualNetworkRule
from c7n.filters.core import type_schema
from c7n_azure.actions import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager


@resources.register('storage')
class Storage(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.storage'
        client = 'StorageManagementClient'
        enum_spec = ('storage_accounts', 'list', None)
        diagnostic_settings_enabled = False


@Storage.action_registry.register('setNetworkRules')
class StorageSetNetworkRulesAction(AzureBaseAction):

    schema = type_schema(
        'setNetworkRules',
        required=['defaultAction'],
        **{
            'defaultAction': {'enum': ['Allow', 'Deny']},
            'bypass': {'type': 'string'},
            'ipRules': {
                'type': 'array',
                'items': {'ipAddressOrRange': {'type': 'string'}}
            },
            'virtualNetworkRules': {
                'type': 'array',
                'items': {'virtualNetworkResourceId': {'type': 'string'}}
            }
        }
    )

    def _prepare_processing(self,):
        self.client = self.manager.get_client()

    def _process_resource(self, resource):
        ruleSet = NetworkRuleSet(default_action=self.data['defaultAction'])

        if 'ipRules' in self.data:
            ruleSet.ip_rules = [
                IPRule(ip_address_or_range=r['ipAddressOrRange'], action='Allow')
                for r in self.data['ipRules']]

        if 'virtualNetworkRules' in self.data:
            ruleSet.virtual_network_rules = [
                VirtualNetworkRule(
                    virtual_network_resource_id=r['virtualNetworkResourceId'],
                    action='Allow')
                for r in self.data['virtualNetworkRules']]

        if 'bypass' in self.data:
            ruleSet.bypass = self.data['bypass']

        self.client.storage_accounts.update(
            resource['resourceGroup'],
            resource['name'],
            StorageAccountUpdateParameters(network_rule_set=ruleSet))
