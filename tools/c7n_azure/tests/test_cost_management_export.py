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
from mock import patch


class CostManagementExportTest(BaseTest):

    def test_key_vault_storage_schema_validate(self):
        p = self.load_policy({
            'name': 'cost-management-export',
            'resource': 'azure.cost-management-export',
            'filters': [
                {'type': 'last-execution',
                 'age': 30}
            ],
            'actions': [
                {'type': 'execute'}
            ]
        }, validate=True)
        self.assertTrue(p)

