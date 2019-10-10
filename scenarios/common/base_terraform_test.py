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

import hashlib
import unittest
from .infrastructure import execution_id


def get_resource_name(test_name):
    suffix = execution_id + hashlib.sha1(test_name.encode('utf-8')).hexdigest()[:8]
    return 'c7n' + suffix


class BaseTerraformTest(unittest.TestCase):

    resource = None
    template = None
    scope = 'function'

    common_template = None

    policies_folder = None
    modules_folder = None

    @staticmethod
    def get_module(template, name):
        raise NotImplementedError
