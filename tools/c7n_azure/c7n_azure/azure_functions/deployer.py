import argparse
import json
import logging

import six
import yaml
from azure.mgmt.eventgrid.models import \
    StorageQueueEventSubscriptionDestination, StringInAdvancedFilter, EventSubscriptionFilter
from c7n_azure.azure_events import AzureEvents, AzureEventSubscription
from c7n_azure.function_package import FunctionPackage
from c7n_azure.functionapp_utils import FunctionAppUtilities
from c7n_azure.session import Session
from c7n_azure.storage_utils import StorageUtilities
from c7n_azure.utils import ResourceIdParser, StringUtils

from c7n.commands import policy_command
from c7n.config import Config
from c7n.utils import local_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s: %(name)s:%(levelname)s %(message)s")
log = logging.getLogger('custodian.azure.deployer')
session = local_session(Session)


def load_policies(policies_files):
    @policy_command
    def _load_policies_internal(options, policies):
        return policies

    config = Config.empty()
    config['configs'] = policies_files
    config['vars'] = {}
    return _load_policies_internal(config)


def extract_properties(options, name, properties):
    settings = options.get(name, {})
    result = {}
    # str type implies settings is a resource id
    if isinstance(settings, six.string_types):
        result['id'] = settings
        result['name'] = ResourceIdParser.get_resource_name(settings)
        result['resource_group_name'] = ResourceIdParser.get_resource_group(settings)
    else:
        # get nested keys
        for key in properties.keys():
            d = StringUtils.snake_to_dashes(key)
            if d in settings:
                value = settings[d]
            else:
                value = settings.get(StringUtils.snake_to_camel(key), properties[key])
            if isinstance(value, dict):
                result[key] = \
                    extract_properties({'v': value}, 'v', properties[key])
            else:
                result[key] = value

    return result


def get_queue_name(policy_name):
    return policy_name.replace('_', '-')


def get_functionapp_config(provision_options, subscription_id, target_subscription_name):
    # Service plan is parsed first, location might be shared with storage & insights
    service_plan = extract_properties(
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

    storage_account = extract_properties(
        provision_options,
        'storageAccount',
        {
            'name': 'custodian' + storage_suffix,
            'location': location,
            'resource_group_name': rg_name
        })

    app_insights = extract_properties(
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


def process_policies(policies):
    target_subscription_ids = session.get_function_target_subscription_ids()

    function_policies = []
    event_subscriptions = []

    for p in policies:
        policy_target_subscription_ids = None
        queue_name = None

        if p.data['mode']['type'] == 'azure-event-grid':
            policy_target_subscription_ids = [None]
            queue_name = get_queue_name(p.name)

            event_subscriptions.append({'queue_name': queue_name,
                                        'events': p.data['mode'].get('events'),
                                        'target_subscription_ids': target_subscription_ids})
        elif p.data['mode']['type'] == 'azure-periodic':
            policy_target_subscription_ids = target_subscription_ids
            queue_name = None
        else:
            log.error('Policy has incorrect mode.')
            exit(1)

        function_policies.append({'name': p.name,
                                  'data': p.data,
                                  'queue_name': queue_name,
                                  'target_subscription_ids': policy_target_subscription_ids })

    return function_policies, event_subscriptions


def create_event_subscriptions(storage_account, event_subscriptions):
    storage_client = session.client('azure.mgmt.storage.StorageManagementClient')
    storage_account = storage_client.storage_accounts.get_properties(
        storage_account['resource_group_name'],
        storage_account['name'])

    for e in event_subscriptions:
        queue_name = e['queue_name']
        log.info("Creating storage queue")
        try:
            StorageUtilities.create_queue_from_storage_account(storage_account, queue_name, session)
            log.info("Storage queue creation succeeded")
        except Exception as e:
            log.error('Queue creation failed with error: %s' % e)
            exit(1)

        log.info('Creating event grid subscription for {0} queue.'.format(queue_name))
        destination = StorageQueueEventSubscriptionDestination(resource_id=storage_account.id,
                                                               queue_name=queue_name)

        # filter specific events
        subscribed_events = AzureEvents.get_event_operations(e['events'])
        advance_filter = StringInAdvancedFilter(key='Data.OperationName', values=subscribed_events)
        event_filter = EventSubscriptionFilter(advanced_filters=[advance_filter])

        for subscription_id in e['target_subscription_ids']:
            try:
                AzureEventSubscription.create(destination, queue_name,
                                              subscription_id, session, event_filter)
                log.info('Event grid subscription creation succeeded: subscription_id=%s' %
                         subscription_id)
            except Exception as e:
                log.error('Event Subscription creation failed with error: %s' % e)
                exit(1)


def deploy(function_app_config, policies, auth_data):
    FunctionAppUtilities.deploy_function_app(function_app_config)

    function_policies, event_subscriptions = process_policies(policies)

    create_event_subscriptions(function_app_config.storage_account, event_subscriptions)

    package = FunctionPackage(auth_data=auth_data)
    package.build(function_policies,
                  modules=['c7n', 'c7n-azure', 'applicationinsights'],
                  non_binary_packages=['pyyaml', 'pycparser', 'tabulate', 'pyrsistent'],
                  excluded_packages=['azure-cli-core', 'distlib', 'future', 'futures'])
    package.close()

    FunctionAppUtilities.publish_functions_package(function_app_config, package)


def main():

    parser = argparse.ArgumentParser(description='Deploy c7n-azure into Azure Functions.')
    parser.add_argument('--config', '-c', dest='config',
                        help='Path to c7n-azure-deployer configuration file.')

    parser.add_argument('--auth-file', '-a', dest='authentication_file',
                        help='Path to authentication file to use.')
    args = parser.parse_args()

    config_file = args.config
    auth_file = args.authentication_file

    with open(auth_file, 'r') as stream:
        auth_data = json.load(stream)

    with open(config_file, 'r') as stream:
        config = yaml.safe_load(stream)

    policies = load_policies(config['policies'])

    function_app_config = get_functionapp_config(provision_options=config['provision-options'],
                                                 subscription_id=session.get_subscription_id(),
                                                 target_subscription_name=session.get_function_target_subscription_name())

    deploy(function_app_config, policies, auth_data)


if __name__ == '__main__':
    main()
