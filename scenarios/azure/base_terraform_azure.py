import os
import uuid

from ..common.base_terraform_test import BaseTerraformTest
from ..common.base_terraform_test import get_resource_name


class BaseAzureTerraformTest(BaseTerraformTest):

    modules_folder = os.path.join(os.path.dirname(__file__), 'templates')
    policies_folder = os.path.join(os.path.dirname(__file__), 'policies')

    common_template = """
    provider "azurerm" {
        version = "=1.34.0"
    }
    """

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

    def get_module(self, test_name):
        return self.module_template.format(
            'a' + str(uuid.uuid1()),  # needs to start with a letter
            os.path.join(self.modules_folder, self.template).replace('\\', '\\\\'),
            get_resource_name(test_name),
            self.location
        )
