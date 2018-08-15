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

from c7n.actions import BaseAction
from c7n.filters.core import ValueFilter, type_schema
from c7n.filters.related import RelatedResourceFilter

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.session import Session

from azure.graphrbac import GraphRbacManagementClient
from azure.graphrbac.models import GetObjectsParameters

@resources.register('keyvault')
class KeyVault(ArmResourceManager):

    class resource_type(ArmResourceManager.resource_type):
        service = 'azure.mgmt.keyvault'
        client = 'KeyVaultManagementClient'
        enum_spec = ('vaults', 'list', None)


@KeyVault.filter_registry.register('whitelist')
class WhiteListFilter(ValueFilter):
    schema = type_schema('whitelist', rinherit=ValueFilter.schema)
    graph_client = None

    def __call__(self, i):
        if 'access_policies' not in i:
            client = self.manager.get_client()
            vault = client.vaults.get(i['resourceGroup'], i['name'])

            # Retrieve access policies for the keyvaults
            access_policies = []
            for policy in vault.properties.access_policies:
                access_policies.append({
                    'tenant_id': policy.tenant_id,
                    'object_id': policy.object_id,
                    'application_id': policy.application_id,
                    'permissions': {
                        'keys': policy.permissions.keys,
                        'secrets': policy.permissions.secrets,
                        'certificates': policy.permissions.certificates
                    }
                })

            # Enhance access policies with display_name, object_type and principal_name before continue
            i['access_policies'] = self.enhance_policies(access_policies)

        return super(WhiteListFilter, self).__call__(i)

    def enhance_policies(self, access_policies):
        if self.graph_client is None:
            s = Session(resource='https://graph.windows.net')
            self.graph_client = GraphRbacManagementClient(s.get_credentials(), s.get_tenant_id())

        # Retrieve graph objects for all object_id
        object_ids = [p['object_id'] for p in access_policies]
        object_params = GetObjectsParameters(
            include_directory_object_references=True,
            object_ids=object_ids)

        aad_objects = self.graph_client.objects.get_objects_by_object_ids(object_params)
        principal_dics = {aad_object.object_id: aad_object for aad_object in aad_objects}

        for policy in access_policies:
            # Ensure there is a graph object. SP can be removed from graph, but it still has an access.
            if policy['object_id'] not in principal_dics.keys():
                policy['display_name'] = None
                policy['object_type'] = None
                policy['principal_name'] = None
                continue
            aad_object = principal_dics[policy['object_id']]
            policy['display_name'] = aad_object.display_name
            policy['object_type'] = aad_object.object_type
            policy['principal_name'] = self.get_principal_name(aad_object)

        return access_policies

    @staticmethod
    def get_principal_name(graph_object):
        if graph_object.user_principal_name:
            return graph_object.user_principal_name
        elif graph_object.service_principal_names:
            return graph_object.service_principal_names[0]
        return graph_object.display_name or ''
