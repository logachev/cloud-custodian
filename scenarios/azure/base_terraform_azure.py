from ..common.base_terraform_test import BaseTerraformTest
import uuid
import os


class BaseAzureTerraformTest(BaseTerraformTest):

    common_template = """
    provider "azurerm" {
        version = "=1.34.0"
    }
    """

    module_template = """
    resource "azurerm_resource_group" "{0}" {{
        name     = "{3}"
        location = "{4}"
    }}

    module "{0}" {{
        source = "{1}"
        name = "{2}"
        rg_name = "${{azurerm_resource_group.{0}.name}}"
        location = "{4}"
    }}
    """

    location = 'westus'

    modules_folder = os.path.join(os.path.dirname(__file__), 'templates')

    def get_module(self, name):
        return self.module_template.format(
            'a' + str(uuid.uuid1()),
            os.path.join(self.modules_folder, self.template).replace('\\', '\\\\'),
            name,
            name,
            self.location
        )
