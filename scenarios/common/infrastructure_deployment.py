import hashlib
import os
import shutil
import tempfile
import time
import uuid

import pytest
from python_terraform import *

from c7n.resources import load_resources

load_resources()

policies_folder = os.path.join(os.path.dirname(__file__), '..', 'policies')

execution_id = str(uuid.uuid1())[:8]
outdir = tempfile.mkdtemp()


def is_infra_deployment_node(config):
    if hasattr(config, 'slaveinput'):
        return config.slaveinput.get('slaveid') == 'gw0'
    return True


def infrastructure_deployed(filename, success=True):
    with open(filename, 'wt') as f:
        if success:
            f.write(execution_id)
        else:
            f.write('Failed')


def wait_for_infrastructure(filename):
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


def wait_for_completion(config, filename):
    done_files = []

    if hasattr(config, 'slaveinput'):
        done_files = [filename + 'gw' + str(i)
                      for i in range(1, config.slaveinput['workercount'])]

    while True:
        if all(os.path.exists(file) for file in done_files):
            break
        else:
            time.sleep(5)

    os.remove(filename)
    for file in done_files:
        os.remove(file)


def deploy(terraform):
    return_code, stdout, stderr = terraform.init()
    if return_code != 0:
        print(stdout)
        print(stderr)
        return False

    return_code, stdout, stderr = terraform.apply(skip_plan=True)
    if return_code != 0:
        print(stdout)
        print(stderr)
        return False

    return True


def cleanup(terraform):
    return_code, stdout, stderr = terraform.destroy(force=True)
    if return_code != 0:
        print(stdout)
        print(stderr)
        assert False
