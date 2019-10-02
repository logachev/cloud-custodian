import unittest


class BaseTerraformTest(unittest.TestCase):

    resource = None
    template = None

    common_template = None
    module_template = None

    def get_module(self, name):
        raise NotImplemented
