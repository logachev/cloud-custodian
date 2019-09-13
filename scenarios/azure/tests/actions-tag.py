import unittest
import pytest
from parameterized import parameterized_class
from python_terraform import *


class BaseScenarioTest(unittest.TestCase):

    t = Terraform()

    def setUp(self) -> None:
        print('Deploying terraform template...{0}'.format(self.template))
        self.resource_group = 'c7n-test-'
        self.resource_name = 'test'

        return_code, stdout, stderr = self.t.apply('s:\\github\\cloud-custodian\\scenarios\\azure\\templates\\' + self.template)
        print(return_code)
        print(stdout)
        print(stderr)

    def run_policy(self, policy, variables):
        print('run policy {0} {1}'.format(policy, variables))

    def tearDown(self) -> None:
        print('Destroying terraform template...')


scenarios = [
    {'resource': 'azure.resourcegroup',
     'template': 'resource-group',
     'policy': 'tag.yml'},
    # [{'resource': 'azure.storage',
    #   'template': 'templates/storage/main.tf',
    #   'policy': 'tag.yml'}],
    ]


@parameterized_class(scenarios)
class TestActionsTag(BaseScenarioTest):

    def test_execute_policy(self):
        variables = {
            'name': self.resource_name,
            'resource': self.resource,
            'tag-name': 'randomtag',
            'tag-value': 'randomvalue'
        }
        self.run_policy(self.policy, variables)

        print('Verifying policy...')
        self.assertFalse(True)
