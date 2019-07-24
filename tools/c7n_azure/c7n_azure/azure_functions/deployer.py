import argparse
import pprint

import yaml
from c7n_azure.function_package import FunctionPackage
from c7n_azure.functionapp_utils import FunctionAppUtilities
from c7n_azure.policy import AzureFunctionMode
from c7n_azure.session import Session
from c7n_azure.utils import StringUtils

from c7n.commands import policy_command
from c7n.config import Config
from c7n.utils import local_session
import logging

pp = pprint.PrettyPrinter()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s: %(name)s:%(levelname)s %(message)s")


def load_policies(policies_files):
    @policy_command
    def _load_policies_internal(options, policies, providers):
        return policies

    config = Config.empty()
    config['configs'] = policies_files
    config['vars'] = {}
    return _load_policies_internal(config)


def get_functionapp_config(provision_options, subscription_id, target_subscription_name):
    # Service plan is parsed first, location might be shared with storage & insights
    service_plan = AzureFunctionMode.extract_properties(
        provision_options,
        'service-plan',
        {
            'name': 'cloud-custodian',
            'location': 'eastus',
            'resource_group_name': 'cloud-custodian',
            'sku_tier': 'Dynamic',  # consumption plan
            'sku_name': 'Y1',
            'auto_scale': {
                'enabled': False,
                'min_capacity': 1,
                'max_capacity': 2,
                'default_capacity': 1
            }
        })

    # Metadata used for automatic naming
    location = service_plan.get('location', 'eastus')
    rg_name = service_plan['resource_group_name']
    function_suffix = StringUtils.naming_hash(
        rg_name + target_subscription_name + service_plan['name'] + service_plan['sku_tier'])
    storage_suffix = StringUtils.naming_hash(rg_name + subscription_id)

    storage_account = AzureFunctionMode.extract_properties(
        provision_options,
        'storageAccount',
        {
            'name': 'custodian' + storage_suffix,
            'location': location,
            'resource_group_name': rg_name
        })

    app_insights = AzureFunctionMode.extract_properties(
        provision_options,
        'appInsights',
        {
            'name': service_plan['name'],
            'location': location,
            'resource_group_name': rg_name
        })

    function_app_name = provision_options.get('function-app-prefix',
                                              'custodian') + '-' + function_suffix
    FunctionAppUtilities.validate_function_name(function_app_name)

    params = FunctionAppUtilities.FunctionAppInfrastructureParameters(
        app_insights=app_insights,
        service_plan=service_plan,
        storage_account=storage_account,
        function_app_resource_group_name=service_plan['resource_group_name'],
        function_app_name=function_app_name)

    return params


def main():
    session = local_session(Session)

    parser = argparse.ArgumentParser(description='Deploy c7n-azure into Azure Functions.')
    parser.add_argument('--config', '-c', dest='config',
                        help='Path to c7n-azure-deployer configuration file.')

    parser.add_argument('--auth-file', '-a', dest='authentication_file',
                        help='Path to authentication file to use.')
    args = parser.parse_args()

    config_file = args.config
    auth_file = args.authentication_file

    with open(auth_file, 'r') as stream:
        auth_data = stream.read()

    with open(config_file, 'r') as stream:
        config = yaml.safe_load(stream)

    policies = load_policies(config['policies'])

    target_subscription_ids = session.get_function_target_subscription_ids()
    policies = [{'name': p.name,
                 'data': p.data,
                 'queue_name': '',
                 'target_subscription_ids': target_subscription_ids} for p in policies]

    function_app_config = get_functionapp_config(provision_options=config['provision-options'],
                                                 subscription_id=session.get_subscription_id(),
                                                 target_subscription_name=session.get_function_target_subscription_name())

    FunctionAppUtilities.deploy_function_app(function_app_config)

    package = FunctionPackage(auth_data=auth_data)
    package.build(policies,
                  modules=['c7n', 'c7n-azure', 'applicationinsights'],
                  non_binary_packages=['pyyaml', 'pycparser', 'tabulate', 'pyrsistent'],
                  excluded_packages=['azure-cli-core', 'distlib', 'future', 'futures'])
    package.close()

    FunctionAppUtilities.publish_functions_package(function_app_config, package)


if __name__ == '__main__':
    main()
