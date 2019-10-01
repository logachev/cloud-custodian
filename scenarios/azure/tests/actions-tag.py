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
import tempfile
import uuid
import hashlib
from functools import wraps
from copy import copy
import time
from retrying import retry

load_resources()

ScenarioConfiguration = namedtuple('ScenarioConfiguration', 'resource,template,policy,parameters')

modules_folder = os.path.join(os.path.dirname(__file__), '..', 'templates')
policies_folder = os.path.join(os.path.dirname(__file__), '..', 'policies')
location = 'westus'


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
execution_id = str(uuid.uuid1())[:8]


def get_module(template, name):

    return module_template.format(
        'a' + str(uuid.uuid1()),
        os.path.join(modules_folder, template).replace('\\', '\\\\'),
        name,
        name,
        location
    )


tmpdir = tempfile.mkdtemp()
outdir = tempfile.mkdtemp()


@pytest.fixture(scope="session", autouse=True)
def provision_terraform_templates(request):

    master_template = common_template
    session = request.node
    for item in session.items:
        cls = item.parent
        suffix = execution_id + hashlib.sha1(item.name.encode('utf-8')).hexdigest()[:8]
        name = 'c7n' + suffix
        master_template += get_module(cls._obj.template, name)

    with open(os.path.join(tmpdir, 'main.tf'), 'wt') as f:
        f.write(master_template)

    t = Terraform(working_dir=tmpdir)
    return_code, stdout, stderr = t.init()
    if return_code != 0:
        print(stdout)
        print(stderr)
        assert False
    return_code, stdout, stderr = t.apply(skip_plan=True)
    if return_code != 0:
        print(stdout)
        print(stderr)
        assert False

    # Cleanup
    yield provision_terraform_templates
    return_code, stdout, stderr = t.destroy(force=True)
    if return_code != 0:
        print(stdout)
        print(stderr)
        assert False

    # Terraform on Windows creates some hardlinks, so they should be removed first
    # for root, dirs, files in os.walk(tmpdir, topdown=False):
    #     for name in dirs:
    #         if os.stat(os.path.join(root, name)).st_size == 0:
    #             os.unlink(os.path.join(root, name))

    shutil.rmtree(os.path.join(tmpdir, '.terraform', 'plugins'))
    pass


def policy_file(name):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cls = args[0]
            with open(os.path.join(policies_folder, name), 'r') as f:
                data = yaml.load(f)

            data['policies'][0]['resource'] = cls.resource

            suffix = execution_id + hashlib.sha1(func.__name__.encode('utf-8')).hexdigest()[:8]
            local_variables = {**cls.variables,
                               **{'name': 'c7n' + suffix}}

            conf = Config.empty(**{'output_dir': outdir})

            p = policy.Policy(data['policies'][0], conf)
            p.expand_variables(local_variables)
            p.validate()
            p.run()

            return func(*(cls, p.resource_manager.get_client(), 'c7n' + suffix), **kwargs)
        return wrapper
    return decorator

class TestRGActions(unittest.TestCase):

    template = 'resource-group'
    resource = 'azure.resourcegroup'

    variables = {
        'tag-name': 'rgtag',
        'tag-value': 'rgvalue'
    }

    @policy_file('tag.yml')
    @retry(stop_max_delay=60000, wait_exponential_multiplier=1000, wait_exponential_max=10000)
    def test_tag(self, client, name):
        rg = client.resource_groups.get(name)
        self.assertEqual('rgvalue', rg.tags.get('rgtag'))

    @policy_file('delete.yml')
    @retry(stop_max_delay=60000, wait_exponential_multiplier=1000, wait_exponential_max=10000)
    def test_delete(self, client, name):
        with self.assertRaises(Exception):
            client.resource_groups.get(name)
