import pytest
from .common.infrastructure_deployment import *


@pytest.fixture(scope="session", autouse=True)
def provision_terraform_templates(request):
    master_template = ''
    deployment_info = ''
    common_seen = set()

    for item in request.node.items:
        cls = item.parent._obj
        suffix = execution_id + hashlib.sha1(item.name.encode('utf-8')).hexdigest()[:8]
        name = 'c7n' + suffix

        if cls.common_template not in common_seen:
            master_template += cls.common_template
            common_seen.add(cls.common_template)
        master_template += cls.get_module(cls, name)

        # Using test name & template name to ensure infrastructure is deployed only from main worker
        deployment_info += item.name + cls.template

    infrastructure_deployed_file = os.path.join(
        os.path.dirname(__file__),
        hashlib.sha1(deployment_info.encode('utf-8')).hexdigest()[:8])

    if is_infra_deployment_node(request.config):
        tmpdir = tempfile.mkdtemp()
        with open(os.path.join(tmpdir, 'main.tf'), 'wt') as f:
            f.write(master_template)

        terraform = Terraform(working_dir=tmpdir)
        if not deploy(terraform):
            infrastructure_deployed(infrastructure_deployed_file, False)
            assert False

        infrastructure_deployed(infrastructure_deployed_file)
        yield provision_terraform_templates
        wait_for_completion(request.config, infrastructure_deployed_file)

        cleanup(terraform)

        # Terraform on Windows creates some hardlinks, so they should be removed first
        # for root, dirs, files in os.walk(tmpdir, topdown=False):
        #     for name in dirs:
        #         if os.stat(os.path.join(root, name)).st_size == 0:
        #             os.unlink(os.path.join(root, name))

        shutil.rmtree(os.path.join(tmpdir, '.terraform', 'plugins'))

    else:
        if not wait_for_infrastructure(infrastructure_deployed_file):
            assert False
        yield provision_terraform_templates
        with open(infrastructure_deployed_file + request.config.slaveinput['workerid'], 'wt') as f:
            f.write('Done')
