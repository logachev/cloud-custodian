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

from azure_common import BaseTest, arm_template, cassette_name
from base_resource import BaseResourceTest


class ContainerGroupTest(BaseResourceTest):

    resource = 'azure.container-group'
    resource_name_prefix = 'cctest-container'

    def test_schema(self):
        self.validate_schema()

    @arm_template('aci.json')
    @cassette_name('list')
    def test_find_container_by_name(self):
        self.verify_exists()
