import hashlib
import unittest

from ..common.infrastructure_deployment import execution_id


def get_resource_name(test_name):
    suffix = execution_id + hashlib.sha1(test_name.encode('utf-8')).hexdigest()[:8]
    return 'c7n' + suffix


class BaseTerraformTest(unittest.TestCase):

    resource = None
    template = None

    common_template = None

    policies_folder = None
    modules_folder = None

    def get_module(self, name):
        raise NotImplementedError
