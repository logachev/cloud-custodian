# Copyright 2019 Capital One Services, LLC
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
import sys

from c7n.provider import resources
from c7n.testing import get_doc_policies
from .common import BaseTest

try:
    import pytest
    skipif = pytest.mark.skipif
except ImportError:
    skipif = lambda func, reason="": func  # noqa E731


class DocExampleTest(BaseTest):

    skip_condition = not (
        # Okay slightly gross, basically if we're explicitly told via
        # env var to run doc tests do it.
        (os.environ.get("C7N_TEST_DOC") in ('yes', 'true') or
         # Or for ci to avoid some tox pain, we'll auto configure here
         # to run on the py3.6 test runner, as its the only one
         # without additional responsibilities.
         (os.environ.get('C7N_TEST_RUN') and
          sys.version_info.major == 2 and
          sys.version_info.minor == 7)))

    @skipif(skip_condition, reason="Doc tests must be explicitly enabled with C7N_DOC_TEST")
    def test_doc_examples(self):
        policies, duplicate_names = get_doc_policies(resources()) # type: dict, set
        self.load_policy_set({'policies': [v for v in policies.values()]})

        # TODO: This check needs to be enabled when duplicate policy names are cleaned up
        # self.assertSetEqual(duplicate_names, set())

        for p in policies:
            # Note max name size here is 54 if its a lambda policy
            # given our default prefix custodian- to stay under 64
            # char limit on lambda function names.
            if len(p['name']) >= 54 and 'mode' in p:
                raise ValueError(
                    "doc policy exceeds name limit policy:%s" % (p['name']))
