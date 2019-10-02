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
