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

from retrying import retry

from .base_terraform_azure import BaseAzureTerraformTest
from ..common.runner import policy_file


class TestRGActions(BaseAzureTerraformTest):

    template = 'resource-group'
    resource = 'azure.resourcegroup'

    variables = {
        'tag-name': 'rgtag',
        'tag-value': 'rgvalue'
    }

    @policy_file('tag.yml', variables)
    @retry(stop_max_delay=60000, wait_exponential_multiplier=1000, wait_exponential_max=10000)
    def test_tag(self, client, name):
        rg = client.resource_groups.get(name)
        self.assertEqual('rgvalue', rg.tags.get('rgtag'))

    @policy_file('delete.yml')
    @retry(stop_max_delay=60000, wait_exponential_multiplier=1000, wait_exponential_max=10000)
    def test_delete(self, client, name):
        with self.assertRaises(Exception):
            client.resource_groups.get(name)
