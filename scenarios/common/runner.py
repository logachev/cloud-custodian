import os
import tempfile
from functools import wraps

import yaml

from c7n import policy
from c7n.config import Config
from .base_terraform_test import get_resource_name

output_dir = tempfile.mkdtemp()


def policy_file(name, variables={}):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cls = args[0]
            with open(os.path.join(cls.policies_folder, name), 'r') as f:
                data = yaml.load(f)

            data['policies'][0]['resource'] = cls.resource

            resource_name = get_resource_name(func.__name__)
            local_variables = {**variables,
                               **{'name': resource_name}}

            conf = Config.empty(**{'output_dir': output_dir})

            p = policy.Policy(data['policies'][0], conf)
            p.expand_variables(local_variables)
            p.validate()
            p.run()

            return func(*(cls, p.resource_manager.get_client(), resource_name), **kwargs)
        return wrapper
    return decorator
