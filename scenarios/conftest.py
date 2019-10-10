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

import tempfile
import uuid
import pytest

from .common import infrastructure


def is_master(config):
    return not hasattr(config, 'workerinput')


def pytest_configure(config):
    if is_master(config):
        config.tmp_dir = tempfile.mkdtemp()
        config.execution_id = str(uuid.uuid1())[:8]
    else:
        infrastructure.execution_id = config.workerinput['execution_id']


def pytest_unconfigure(config):
    if not is_master(config):
        return

    infrastructure.cleanup(config.tmp_dir)


def pytest_configure_node(node):
    node.workerinput['execution_id'] = node.config.execution_id


def pytest_xdist_node_collection_finished(node, ids):
    # This hook is called on master when each node is done collection the tests.
    # We need to provision infra only once.
    if hasattr(pytest_xdist_node_collection_finished, 'has_run'):
        return
    pytest_xdist_node_collection_finished.has_run = True

    # Provision infrastructure for all tests
    tests = infrastructure.build_tests_map(ids)
    infrastructure.generate_template(node.config.tmp_dir, tests)
    infrastructure.deploy(node.config.tmp_dir)
