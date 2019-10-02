import os
import tempfile

import pytest

from .common.infrastructure_deployment import is_infra_deployment_node, terraform_apply, \
    terraform_destroy, wait_for_infrastructure, wait_for_tests_finished, tests_finished, \
    build_master_template


@pytest.fixture(scope="session", autouse=True)
def provision_terraform_templates_master(request):

    if not is_infra_deployment_node(request.config):
        yield provision_terraform_templates_master
        return

    master_template, deployment_hash = build_master_template(request)

    tmpdir = tempfile.mkdtemp()
    with open(os.path.join(tmpdir, 'main.tf'), 'wt') as f:
        f.write(master_template)

    terraform_apply(tmpdir, deployment_hash)

    yield provision_terraform_templates_master

    wait_for_tests_finished(request.config, deployment_hash)
    terraform_destroy(tmpdir)


@pytest.fixture(scope="session", autouse=True)
def provision_terraform_templates_worker(request):

    if is_infra_deployment_node(request.config):
        yield provision_terraform_templates_worker
        return

    master_template, deployment_hash = build_master_template(request)

    if not wait_for_infrastructure(deployment_hash):
        assert False
    yield provision_terraform_templates_worker
    tests_finished(deployment_hash, request.config.slaveinput['workerid'])
