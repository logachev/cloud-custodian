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

from c7n_azure.actions.base import AzureBaseAction
from c7n_azure.provider import resources
from c7n_azure.query import QueryResourceManager

from c7n.utils import type_schema


@resources.register('cost-management-export')
class CostManagementExport(QueryResourceManager):
    """ Cost Management Exports for current subscription (doesn't include Resource Group scopes)

    :example:

    Returns all cost exports for current subscription scope

    .. code-block:: yaml

        policies:
          - name: get-cost--management-exports
            resource: azure.cost-management-export

    """

    class resource_type(QueryResourceManager.resource_type):
        doc_groups = ['Cost']

        service = 'azure.mgmt.costmanagement'
        client = 'CostManagementClient'
        enum_spec = ('exports', 'list', None)
        default_report_fields = (
            'name',
            'location',
            'resourceGroup',
        )
        resource_type = 'Microsoft.Compute/images'

        @classmethod
        def extra_args(cls, resource_manager):
            scope = '/subscriptions/{0}'\
                .format(resource_manager.get_session().get_subscription_id())
            return {'scope': scope}


@CostManagementExport.action_registry.register('execute')
class CostManagementExportActionExecute(AzureBaseAction):
    """ Trigger Cost Management Export execution

    Known issues:

    Error: (400) A valid email claim is required. Email claim is missing in the request header.

    :example:

    Returns all cost exports for current subscription scope

    .. code-block:: yaml

        policies:
          - name: get-cost--management-exports
            resource: azure.cost-management-export
            actions:
              - type: execute

    """
    schema = type_schema('execute')

    def _prepare_processing(self):
        self.client = self.manager.get_client()
        self.scope = 'subscriptions/{0}'.format(self.manager.get_session().get_subscription_id())

    def _process_resource(self, resource):
        self.client.exports.execute(self.scope, resource['name'])
