from c7n.utils import local_session
from c7n_azure.session import Session
from c7n_azure.functionapp_utils import FunctionAppUtilities
from c7n_azure.function_package import FunctionPackage

function_apps = {}
policies_map = {}


def add_function(policy_name, policy_data, queue_name, function_app_params):

    target_subscription_ids = local_session(Session).get_function_target_subscription_ids()
    function_apps.setdefault(function_app_params.function_app_name, function_app_params)
    policies_map.setdefault(function_app_params.function_app_name, []).append(
        {
            'name': policy_name,
            'data': policy_data,
            'queue_name': queue_name,
            'target_subscription_ids': target_subscription_ids if not queue_name else [None]
        }
    )


def _provision_function_apps():
    for _, f in function_apps.items():
        FunctionAppUtilities.deploy_function_app(f)


def _deploy_policies_to_function_app(function_app_name):
    policies = policies_map[function_app_name]

    package = FunctionPackage()
    package.build(policies,
                  modules=['c7n', 'c7n-azure', 'applicationinsights'],
                  non_binary_packages=['pyyaml', 'pycparser', 'tabulate', 'pyrsistent'],
                  excluded_packages=['azure-cli-core', 'distlib', 'future', 'futures'])
    package.close()

    FunctionAppUtilities.publish_functions_package(function_apps[function_app_name], package)


def deploy():
    _provision_function_apps()

    for f in policies_map.keys():
        _deploy_policies_to_function_app(f)


