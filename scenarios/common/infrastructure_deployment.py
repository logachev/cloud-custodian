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
import os
import time
import uuid
import shutil

from python_terraform import Terraform

execution_id = str(uuid.uuid1())[:8]


def is_infra_deployment_node(config):
    if hasattr(config, 'slaveinput'):
        return config.slaveinput.get('slaveid') == 'gw0'
    return True


def infrastructure_deployed(deployment_hash, success=True):
    filename = os.path.join(os.path.dirname(__file__), deployment_hash)
    with open(filename, 'wt') as f:
        if success:
            f.write(execution_id)
        else:
            f.write('Failed')


def tests_finished(deployment_hash, id):
    filename = os.path.join(os.path.dirname(__file__), deployment_hash + '.' + id)
    with open(filename, 'wt') as f:
        f.write('Done')


def wait_for_infrastructure(deployment_hash):
    filename = os.path.join(os.path.dirname(__file__), deployment_hash)
    while True:
        if os.path.exists(filename):
            with open(filename, 'rt') as f:
                global execution_id
                execution_id = f.read()
                if execution_id == 'Failed':
                    return False
                return True
        else:
            time.sleep(5)


def wait_for_tests_finished(config, deployment_hash):
    done_files = []
    filename = os.path.join(os.path.dirname(__file__), deployment_hash)

    if hasattr(config, 'slaveinput'):
        done_files = [filename + '.gw' + str(i)
                      for i in range(1, config.slaveinput['workercount'])]

    while True:
        if all(os.path.exists(file) for file in done_files):
            break
        else:
            time.sleep(5)

    os.remove(filename)
    for file in done_files:
        os.remove(file)


def terraform_apply(working_dir, deployment_hash):
    terraform = Terraform(working_dir=working_dir)
    return_code, stdout, stderr = terraform.init()
    if return_code != 0:
        print(stdout)
        print(stderr)
        infrastructure_deployed(deployment_hash, False)
        assert False

    return_code, stdout, stderr = terraform.apply(skip_plan=True)
    if return_code != 0:
        print(stdout)
        print(stderr)
        infrastructure_deployed(deployment_hash, False)
        assert False

    infrastructure_deployed(deployment_hash)



def terraform_destroy(working_dir):
    terraform = Terraform(working_dir=working_dir)
    return_code, stdout, stderr = terraform.destroy(force=True)
    if return_code != 0:
        print(stdout)
        print(stderr)
        assert False

    # Terraform on Windows creates some hardlinks, so they should be removed first
    # for root, dirs, files in os.walk(tmpdir, topdown=False):
    #     for name in dirs:
    #         if os.stat(os.path.join(root, name)).st_size == 0:
    #             os.unlink(os.path.join(root, name))

    shutil.rmtree(os.path.join(working_dir, '.terraform', 'plugins'))


def build_master_template(request):
    common_seen = set()
    master_template = ''
    deployment_info = ''

    for item in request.node.items:
        cls = item.parent._obj

        if cls.common_template not in common_seen:
            master_template += cls.common_template
            common_seen.add(cls.common_template)
        master_template += cls.get_module(cls, item.name)

        # Using test name & template name to ensure infrastructure is deployed only from main worker
        deployment_info += item.name + cls.template
    return master_template, hashlib.sha1(deployment_info.encode('utf-8')).hexdigest()[:8]
