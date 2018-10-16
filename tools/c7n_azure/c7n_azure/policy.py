# Copyright 2015-2018 Capital One Services, LLC
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

import json
import logging
import time

import requests
from azure.mgmt.eventgrid.models import (EventSubscription, EventSubscriptionFilter,
                                         WebHookEventSubscriptionDestination)
from c7n_azure.azure_events import AzureEvents
from c7n_azure.constants import (CONST_AZURE_EVENT_TRIGGER_MODE, CONST_AZURE_TIME_TRIGGER_MODE,
                                 CONST_AZURE_FUNCTION_KEY_URL)
from c7n_azure.function_package import FunctionPackage
from c7n_azure.functionapp_utils import FunctionAppUtilities
from msrestazure.azure_exceptions import CloudError

from c7n import utils
from c7n.actions import EventAction
from c7n.policy import ServerlessExecutionMode, PullMode, execution
from c7n.utils import local_session

from c7n_azure.utils import ResourceIdParser


class AzureFunctionMode(ServerlessExecutionMode):
    """A policy that runs/executes in azure functions."""

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'provision-options': {
                'type': 'object',
                'appInsights': {
                    'type': 'object',
                    'oneOf': [
                        {'type': 'string'},
                        {'type': 'object',
                         'properties': {
                            'name': 'string',
                            'location': 'string',
                            'resourceGroupName': 'string'}
                         }
                    ]
                },
                'storageAccount': {
                    'type': 'object',
                    'oneOf': [
                        {'type': 'string'},
                        {'type': 'object',
                         'properties': {
                            'name': 'string',
                            'location': 'string',
                            'resourceGroupName': 'string'}
                         }
                    ]
                },
                'servicePlan': {
                    'type': 'object',
                    'oneOf': [
                        {'type': 'string'},
                        {'type': 'object',
                         'properties': {
                             'name': 'string',
                             'location': 'string',
                             'resourceGroupName': 'string',
                             'skuTier': 'string',
                             'skuName': 'string'}
                        }
                    ]
                },
            },
            'execution-options': {'type': 'object'}
        }
    }

    POLICY_METRICS = ('ResourceCount', 'ResourceTime', 'ActionTime')

    def __init__(self, policy):
        self.policy = policy
        self.log = logging.getLogger('custodian.azure.AzureFunctionMode')
        self.session = local_session(self.policy.session_factory)
        self.web_client = self.session.client('azure.mgmt.web.WebSiteManagementClient')

        self.policy_name = self.policy.data['name'].replace(' ', '-').lower()

        provision_options = self.policy.data['mode'].get('provision-options', {})
        self.group_name = provision_options.get('resourceGroup', 'cloud-custodian')

        storage_account = provision_options.get('storageAccount', {})
        self.storage_account = {}
        if type(storage_account) is str:
            self.storage_account['id'] = storage_account
            self.storage_account['name'] = ResourceIdParser.get_resource_name(storage_account)
            self.storage_account['resource_group_name'] = ResourceIdParser.get_resource_group(storage_account)
        else:
            self.storage_account['name'] = storage_account.get('name', 'custodianstorageaccount')
            self.storage_account['location'] = storage_account.get('location', 'westus2')
            self.storage_account['resource_group_name'] = storage_account.get('resourceGroupName', 'cloud-custodian')

        service_plan = provision_options.get('servicePlan', {})
        self.service_plan = {}
        if type(service_plan) is str:
            self.service_plan['id'] = service_plan
            self.service_plan['name'] = ResourceIdParser.get_resource_name(service_plan)
            self.service_plan['resource_group_name'] = ResourceIdParser.get_resource_group(service_plan)
        else:
            self.service_plan['name'] = service_plan.get('name', 'cloud-custodian-plan')
            self.service_plan['location'] = service_plan.get('location', 'westus2')
            self.service_plan['resource_group_name'] = service_plan.get('resourceGroupName', 'cloud-custodian')
            self.service_plan['sku_name'] = service_plan.get('skuName', 'B1')
            self.service_plan['sku_tier'] = service_plan.get('skuTier', 'Basic')

        app_insights = provision_options.get('appInsights', {})
        self.app_insights = {}
        if type(app_insights) is str:
            self.app_insights['id'] = app_insights
            self.app_insights['name'] = ResourceIdParser.get_resource_name(app_insights)
            self.app_insights['resource_group_name'] = ResourceIdParser.get_resource_group(app_insights)
        else:
            self.app_insights['name'] = app_insights.get('name', 'cloud-custodian-plan')
            self.app_insights['location'] = app_insights.get('location', 'westus2')
            self.app_insights['resource_group_name'] = app_insights.get('resourceGroupName', 'cloud-custodian')

        self.webapp_name = self.service_plan['name'] + "-" + self.policy_name

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        params = FunctionAppUtilities.FunctionAppInfrastructureParameters(
            appInsights=self.app_insights,
            servicePlan=self.service_plan,
            storageAccount=self.storage_account,
            webapp_name=self.webapp_name)

        FunctionAppUtilities().deploy_webapp(params)

        self.log.info("Building function package for %s" % self.webapp_name)

        archive = FunctionPackage(self.policy_name)
        archive.build(self.policy.data)
        archive.close()

        self.log.info("Function package built, size is %dMB" % (archive.pkg.size / (1024 * 1024)))

        if archive.wait_for_status(self.webapp_name):
            archive.publish(self.webapp_name)
        else:
            self.log.error("Aborted deployment, ensure Application Service is healthy.")

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("subclass responsibility")

    def validate(self):
        """Validate configuration settings for execution mode."""


@execution.register(CONST_AZURE_TIME_TRIGGER_MODE)
class AzurePeriodicMode(AzureFunctionMode, PullMode):
    """A policy that runs/executes in azure functions at specified
    time intervals."""
    schema = utils.type_schema(CONST_AZURE_TIME_TRIGGER_MODE,
                               schedule={'type': 'string'},
                               rinherit=AzureFunctionMode.schema)

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        return PullMode.run(self)

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("error - not implemented")


@execution.register(CONST_AZURE_EVENT_TRIGGER_MODE)
class AzureEventGridMode(AzureFunctionMode):
    """A policy that runs/executes in azure functions from an
    azure event."""

    schema = utils.type_schema(CONST_AZURE_EVENT_TRIGGER_MODE,
                               events={'type': 'array', 'items': {
                                   'oneOf': [
                                       {'type': 'string'},
                                       {'type': 'object',
                                        'required': ['resourceProvider', 'event'],
                                        'properties': {
                                            'resourceProvider': {'type': 'string'},
                                            'event': {'type': 'string'}}}]
                               }},
                               required=['events'],
                               rinherit=AzureFunctionMode.schema)

    def provision(self):
        super(AzureEventGridMode, self).provision()
        key = self._get_webhook_key()
        webhook_url = 'https://%s.azurewebsites.net/api/%s?code=%s' % (self.webapp_name,
                                                                       self.policy_name, key)
        destination = WebHookEventSubscriptionDestination(
            endpoint_url=webhook_url
        )

        self.log.info("Creating Event Grid subscription")
        event_filter = EventSubscriptionFilter()
        event_info = EventSubscription(destination=destination, filter=event_filter)
        scope = '/subscriptions/%s' % self.session.subscription_id

        #: :type: azure.mgmt.eventgrid.EventGridManagementClient
        eventgrid_client = self.session.client('azure.mgmt.eventgrid.EventGridManagementClient')

        status_success = False
        while not status_success:
            try:
                event_subscription = eventgrid_client.event_subscriptions.create_or_update(
                    scope, self.webapp_name, event_info)

                event_subscription.result()
                self.log.info('Event Grid subscription creation succeeded')
                status_success = True
            except CloudError as e:
                self.log.info(e)
                self.log.info('Retrying in 30 seconds')
                time.sleep(30)

    def _get_webhook_key(self):
        self.log.info("Fetching Function's API keys")
        token_headers = {
            'Authorization': 'Bearer %s' % self.session.get_bearer_token()
        }

        key_url = (
            'https://management.azure.com'
            '/subscriptions/{0}/resourceGroups/{1}/'
            'providers/Microsoft.Web/sites/{2}/{3}').format(
            self.session.subscription_id,
            self.group_name,
            self.webapp_name,
            CONST_AZURE_FUNCTION_KEY_URL)

        retrieved_key = False

        while not retrieved_key:
            response = requests.get(key_url, headers=token_headers)
            if response.status_code == 200:
                key = json.loads(response.content)
                return key['value']
            else:
                self.log.info('Function app key unavailable, will retry in 30 seconds')
                time.sleep(30)

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        subscribed_events = AzureEvents.get_event_operations(
            self.policy.data['mode'].get('events'))

        resource_ids = list(set(
            [e['subject'] for e in event if self._is_subscribed_to_event(e, subscribed_events)]))

        resources = self.policy.resource_manager.get_resources(resource_ids)

        if not resources:
            self.policy.log.info(
                "policy: %s resources: %s no resources found" % (
                    self.policy.name, self.policy.resource_type))
            return

        with self.policy.ctx:
            self.policy.ctx.metrics.put_metric(
                'ResourceCount', len(resources), 'Count', Scope="Policy",
                buffer=False)

            self.policy._write_file(
                'resources.json', utils.dumps(resources, indent=2))

            for action in self.policy.resource_manager.actions:
                self.policy.log.info(
                    "policy: %s invoking action: %s resources: %d",
                    self.policy.name, action.name, len(resources))
                if isinstance(action, EventAction):
                    results = action.process(resources, event)
                else:
                    results = action.process(resources)
                self.policy._write_file(
                    "action-%s" % action.name, utils.dumps(results))

        return resources

    def get_logs(self, start, end):
        """Retrieve logs for the policy"""
        raise NotImplementedError("error - not implemented")

    def _is_subscribed_to_event(self, event, subscribed_events):
        subscribed_events = [e.lower() for e in subscribed_events]
        if not event['data']['operationName'].lower() in subscribed_events:
            self.policy.log.info(
                "Event operation %s does not match subscribed events %s" % (
                    event['data']['operationName'], subscribed_events
                )
            )
            return False

        return True
