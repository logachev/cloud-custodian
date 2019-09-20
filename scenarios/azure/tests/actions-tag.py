import unittest
import pytest
from parameterized import parameterized_class
from python_terraform import *
from collections import namedtuple
import os
from c7n import policy
from c7n.schema import generate, validate as schema_validate
from c7n.ctx import ExecutionContext
from c7n.utils import reset_session_cache
from c7n.config import Bag, Config
from c7n.commands import run
import yaml
import shutil
from c7n_azure.session import Session
from c7n.resources import load_resources
from c7n.policy import get_resource_class
import pytest

load_resources()

ScenarioConfiguration = namedtuple('ScenarioConfiguration', 'resource,template,policy,parameters')


class BaseScenarioTest(unittest.TestCase):

    test_context = ExecutionContext(
        Session,
        Bag(name="xyz", provider_name='azure'),
        Config.empty()
    )

    t = Terraform()
    base_folder = os.path.join(os.path.dirname(__file__), '..', 'templates')

    def setUp(self) -> None:
        print('Deploying terraform template...{0}'.format(self.template))
        self.resource_group = 'c7n-test-'
        self.resource_name = 'test'

        self.t = Terraform(working_dir=os.path.join(BaseScenarioTest.base_folder, self.template))

        return_code, stdout, stderr = self.t.init()
        return_code, stdout, stderr = self.t.apply(skip_plan=True, var={'rg_name': self.resource_group,
                                                                        'name': self.resource_name})
        if return_code != 0:
            print(stdout)
            print(stderr)
            self.assertEqual(0, return_code)

    def run_policy(self, policy, variables):
        out_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, out_dir)
        if self.mode == 'Pull':
            runner = PullRunner()
            runner.run_policy(policy, variables, out_dir)

    def get_client(self):
        return get_resource_class(self.resource)(self.test_context, {'name': 'test',
                                                                     'resource': self.resource}).get_client()

    def tearDown(self) -> None:
        return_code, stdout, stderr = self.t.destroy(force=True, var={'rg_name': self.resource_group,
                                                                        'name': self.resource_name})


class PolicyRunner:
    def run_policy(self, policy_file):
        raise NotImplemented


class PullRunner(PolicyRunner):

    base_folder = os.path.join(os.path.dirname(__file__), '..', 'policies')

    def run_policy(self, policy_file, variables, out_dir):
        with open(os.path.join(PullRunner.base_folder, policy_file), 'r') as f:
            data = yaml.load(f)
        data['policies'][0]['resource'] = variables['resource']
        p = self.load_policy(data['policies'][0], variables, out_dir)
        p.run()

    def load_policy(self, data, variables, out_dir):
        conf = Config.empty(**{'output_dir': out_dir})
        p = policy.Policy(data, conf)
        p.expand_variables(variables)
        p.validate()
        p.resource_manager.get_client()
        return p


scenarios = [
    ScenarioConfiguration(resource='azure.resourcegroup',
                          template='resource-group',
                          policy='tag.yml',
                          parameters={})
    ]


@parameterized_class([s._asdict() for s in scenarios])
class TestActionsTag(BaseScenarioTest):

    mode = 'Pull'

    def test_execute_policy(self):
        variables = {
            'name': self.resource_name,
            'resource': self.resource,
            'tag-name': 'randomtag',
            'tag-value': 'randomvalue'
        }
        self.run_policy(self.policy, variables)

        client = self.get_client()
        result = client.resource_groups.get(self.resource_name)
        self.assertEqual({'randomtag': 'randomvalue'}, result.tags)
