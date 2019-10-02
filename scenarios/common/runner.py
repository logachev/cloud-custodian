# Copyright 2019 Microsoft Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
