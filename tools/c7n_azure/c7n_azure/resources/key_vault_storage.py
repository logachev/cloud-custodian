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
# limitations under the License.from c7n_azure.provider import resources

import logging

from azure.keyvault.key_vault_id import StorageAccountId
from c7n_azure import constants
from c7n_azure.provider import resources
from c7n_azure.query import ChildResourceManager, ChildTypeInfo
from c7n_azure.utils import ThreadHelper, generate_key_vault_url

from c7n.filters import ValueFilter
from c7n.utils import get_annotation_prefix as gap
from c7n.utils import type_schema

log = logging.getLogger('custodian.azure.keyvault.storage')


@resources.register('keyvault-storage')
class KeyVaultStorage(ChildResourceManager):
    """Key Vault Managed Storage Account Resource

    :example:

    List all Key Vault managed Storage Accounts

    .. code-block:: yaml

        policies:
          - name: keyvault-storage
            resource: azure.keyvault-storage

    """

    class resource_type(ChildTypeInfo):
        doc_groups = ['Security']

        resource = constants.RESOURCE_VAULT
        service = 'azure.keyvault'
        client = 'KeyVaultClient'
        enum_spec = (None, 'get_storage_accounts', None)

        parent_manager_name = 'keyvault'
        raise_on_exception = False

        @classmethod
        def extra_args(cls, parent_resource):
            return {'vault_base_url': generate_key_vault_url(parent_resource['name'])}


class KeyVaultStorageFilterBase(ValueFilter):

    extra_fields = ['autoRegenerateKey', 'regenerationPeriod', 'activeKeyName']

    def process(self, resources, event=None):
        self.client = self.manager.get_client()
        resources, _ = ThreadHelper.execute_in_parallel(
            resources=resources,
            event=event,
            execution_method=self._process_resource_set,
            executor_factory=self.executor_factory,
            log=log
        )
        return resources

    def _extend(self, resource):
        if gap('extra') in resource:
            return resource

        sid = StorageAccountId(resource['id'])
        data = self.client.get_storage_account(sid.vault, sid.name).serialize(True)

        resource[gap('extra')] = {k: v for k, v in data.items() if k in self.extra_fields}

    def _process_resource_set(self, resources, event):
        for resource in resources:
            try:
                self._extend(resource)
            except Exception as error:
                log.warning(error)

        return [r for r in resources if self.match(r)]


@KeyVaultStorage.filter_registry.register('auto-regenerate')
class KeyVaultStorageAutoRegenerateFilter(KeyVaultStorageFilterBase):
    """Filter Key Vault Managed Storage Account Resource on Auto Regenerate property.

    This is ``Value`` based filter, you can provide boolean ``value`` property.

    :example:

    List all Key Vault managed Storage Accounts with disabled automatic keys regeneration

    .. code-block:: yaml

        policies:
          - name: keyvault-storage-auto-regenerate
            resource: azure.keyvault-storage
            filters:
              - type: auto-regenerate
                value: False

    """
    schema = type_schema(
        'auto-regenerate',
        rinherit=ValueFilter.schema,
        **{
            'key': None,
            'op': None,
            'value_type': None,
            'value': {'type': 'boolean'}
        }
    )

    def __init__(self, *args, **kwargs):
        super(KeyVaultStorageAutoRegenerateFilter, self).__init__(*args, **kwargs)
        self.data['key'] = '"{0}".autoRegenerateKey'.format(gap('extra'))
        self.data['op'] = 'eq'


@KeyVaultStorage.filter_registry.register('regeneration-period')
class KeyVaultStorageRegenerationPeriodFilter(KeyVaultStorageFilterBase):
    """Filter Key Vault Managed Storage Account Resource on Regeneration Period property.

    This is ``Value`` based filter, you can provide any ``value`` and ``op`` properties.

    :example:

    List all Key Vault managed Storage Accounts with regeneration period not equal to P90D

    .. code-block:: yaml


        policies:
          - name: keyvault-storage-regeneration-period
            resource: azure.keyvault-storage
            filters:
              - type: regeneration-period
                op: ne
                value: P90D

    """
    schema = type_schema(
        'regeneration-period',
        rinherit=ValueFilter.schema,
        ** {
           'key': None,
           'value_type': None
        }
    )

    def __init__(self, *args, **kwargs):
        super(KeyVaultStorageRegenerationPeriodFilter, self).__init__(*args, **kwargs)
        self.data['key'] = '"{0}".regenerationPeriod'.format(gap('extra'))
        self.data['op'] = 'eq'


@KeyVaultStorage.filter_registry.register('active-key-name')
class KeyVaultStorageActiveKeyNameFilter(KeyVaultStorageFilterBase):
    """Filter Key Vault Managed Storage Account Resource on Active Key Name property.

    This is ``Value`` based filter, you can provide string ``value`` property.

    ``value_type`` is always ``normalize``.

    :example:

    List all Key Vault managed Storage Accounts with Active Key Name key1

    .. code-block:: yaml

        policies:
          - name: keyvault-storage-active-key-name
            resource: azure.keyvault-storage
            filters:
              - type: active-key-name
                value: key1

    """
    schema = type_schema(
        'active-key-name',
        rinherit=ValueFilter.schema,
        required=['value'],
        **{
            'key': None,
            'op': None,
            'value_type': None,
            'value': {'type': 'string'}
        }
    )

    def __init__(self, *args, **kwargs):
        super(KeyVaultStorageActiveKeyNameFilter, self).__init__(*args, **kwargs)
        self.data['key'] = '"{0}".activeKeyName'.format(gap('extra'))
        self.data['op'] = 'eq'
        self.data['value_type'] = 'normalize'
