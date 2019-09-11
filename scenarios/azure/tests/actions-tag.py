import unittest
import pytest
from parameterized import parameterized


class BaseScenarioTest(unittest.TestCase):

    def setUp(self) -> None:
        print('Deploying terraform template...')
        self.resource_group = 'c7n-test-'
        self.resource_name = 'test'

    def run_policy(self, policy, variables):
        print('run policy {0} {1}'.format(policy, variables))

    def tearDown(self) -> None:
        print('Destroying terraform template...')


scenarios = [
    [{'resource': 'azure.resourcegroup',
      'template': 'templates/resource-group/main.tf',
      'policy': 'tag.yml'}],
    [{'resource': 'azure.storage',
      'template': 'templates/storage/main.tf',
      'policy': 'tag.yml'}],
    ]


class TestActionsTag(BaseScenarioTest):

    @parameterized.expand(scenarios)
    def test_execute_policy(self, scenario):
        variables = {
            'name': self.resource_name,
            'resource': scenario['resource'],
            'tag-name': 'randomtag',
            'tag-value': 'randomvalue'
        }
        self.run_policy(scenario['policy'], variables)

        print('Verifying policy...')
        self.assertFalse(True)
