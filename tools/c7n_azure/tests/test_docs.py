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
from __future__ import absolute_import, division, print_function, unicode_literals

import os
import sys

import pytest
from azure_common import BaseTest
from c7n_azure.provider import resources

from c7n.testing import get_doc_policies


class DocsTest(BaseTest):

    skip_condition = not (
        # Okay slightly gross, basically if we're explicitly told via
        # env var to run doc tests do it.
        (os.environ.get("C7N_TEST_DOC") in ('yes', 'true') or
         # Or for ci to avoid some tox pain, we'll auto configure here
         # to run on the py3.6 test runner, as its the only one
         # without additional responsibilities.
         (os.environ.get('C7N_TEST_RUN') and
          sys.version_info.major == 3 and
          sys.version_info.minor == 6)))

    @pytest.mark.skipif(skip_condition,
                        reason="Doc tests must be explicitly enabled with C7N_DOC_TEST")
    def test_policies(self):
        policies, duplicate_names = get_doc_policies(resources) # type: dict, set
        self.load_policy_set({'policies': [v for v in policies.values()]})
        self.assertSetEqual(duplicate_names, set())
