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

import importlib
import os
import shutil

from python_terraform import Terraform


class Configuration:
    execution_id = None


def build_tests_map(ids):
    tests = {}
    for id in ids:
        s = id.split('::')
        module_name = s[0].replace('/', '.')[:-3]
        class_name = s[1]
        test_name = s[2]
        if module_name not in tests:
            tests[module_name] = {}

        if class_name not in tests[module_name]:
            tests[module_name][class_name] = []
        tests[module_name][class_name].append(test_name)
    return tests


def generate_template(working_dir, tests_map):
    common_seen = set()
    master_template = ''

    for m in tests_map.keys():
        module = importlib.import_module(m)
        for k in tests_map[m].keys():
            klass = getattr(module, k)

            if klass.common_template not in common_seen:
                master_template += klass.common_template
                common_seen.add(klass.common_template)

            if klass.scope == 'function':
                for t in tests_map[m][k]:
                    master_template += klass.get_module(klass.template, t)
            elif klass.scope == 'class':
                pass

    with open(os.path.join(working_dir, 'main.tf'), 'wt') as f:
        f.write(master_template)


def deploy(working_dir):
    terraform = Terraform(working_dir=working_dir)
    return_code, stdout, stderr = terraform.init()
    if return_code != 0:
        print(stdout)
        print(stderr)
        assert False

    return_code, stdout, stderr = terraform.apply(skip_plan=True)
    if return_code != 0:
        print(stdout)
        print(stderr)
        assert False


def cleanup(working_dir):
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
