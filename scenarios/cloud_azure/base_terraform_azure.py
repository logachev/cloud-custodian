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

import os
import uuid

from ..common.base_terraform_test import BaseTerraformTest
from ..common.base_terraform_test import get_resource_name
from ..common.infrastructure import AZURE_PROVIDER_INIT


class BaseAzureTerraformTest(BaseTerraformTest):

    modules_folder = os.path.join(os.path.dirname(__file__), 'templates')
    policies_folder = os.path.join(os.path.dirname(__file__), 'policy')

    common_template = AZURE_PROVIDER_INIT

    module_template = """
    resource "azurerm_resource_group" "{0}" {{
        name     = "{2}"
        location = "{3}"
    }}

    module "{0}" {{
        source = "{1}"
        name = "{2}"
        rg_name = "${{azurerm_resource_group.{0}.name}}"
        location = "{3}"
    }}
    """

    location = 'westus'

    @staticmethod
    def get_module(template, test_name):
        return BaseAzureTerraformTest.module_template.format(
            'a' + str(uuid.uuid1()),  # needs to start with a letter
            os.path.join(BaseAzureTerraformTest.modules_folder, template).replace('\\', '\\\\'),
            get_resource_name(test_name),
            BaseAzureTerraformTest.location
        )
