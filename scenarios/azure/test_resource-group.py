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
from ..common.infrastructure_deployment import execution_id
from .base_terraform_azure import BaseAzureTerraformTest

load_resources()

ScenarioConfiguration = namedtuple('ScenarioConfiguration', 'resource,template,policy,parameters')

policies_folder = os.path.join(os.path.dirname(__file__), 'policies')
location = 'westus'

outdir = tempfile.mkdtemp()


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


class TestRGActions(BaseAzureTerraformTest):

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
