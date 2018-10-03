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
from azure.mgmt.web.models import AppServicePlan, SkuDescription


class AzureFunctionMode(ServerlessExecutionMode):
    """A policy that runs/executes in azure functions."""

    schema = {
        'type': 'object',
        'additionalProperties': False,
        'properties': {
            'provision-options': {
                'type': 'object',
                'location': 'string',
                'servicePlanName': 'string',
                'storageName': 'string',
                'resourceGroup': 'string',
                'skuName': 'string',
                'skuTier': 'string'
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
        self.storage_name = provision_options.get('storageName', 'custodianstorageaccount')
        self.location = provision_options.get('location', 'westus2')
        self.service_plan_name = provision_options.get('servicePlanName', 'cloud-custodian-plan')
        self.sku_name = provision_options.get('skuName', 'B1')
        self.sku_tier = provision_options.get('skuTier', 'Standard')

        self.webapp_name = self.service_plan_name + "-" + self.policy_name

    def run(self, event=None, lambda_context=None):
        """Run the actual policy."""
        raise NotImplementedError("subclass responsibility")

    def provision(self):
        self.deploy_infrastructure()
        self.deploy_web_app()

        self.log.info("Building function package for %s" % self.webapp_name)

        archive = FunctionPackage(self.policy_name)
        archive.build(self.policy.data)
        archive.close()

        self.log.info("Function package built, size is %dMB" % (archive.pkg.size / (1024 * 1024)))

        if archive.wait_for_status(self.webapp_name):
            archive.publish(self.webapp_name)
        else:
            self.log.error("Aborted deployment, ensure Application Service is healthy.")

    def deploy_infrastructure(self):
        # Check if RG exists
        rg_client = self.session.client('azure.mgmt.resource.ResourceManagementClient')
        if not rg_client.resource_groups.check_existence(self.group_name):
            rg_client.resource_groups.create_or_update(self.group_name, {'location': self.location})

        # Storage account create function is async, wait for completion after
        # other resources provisioned.
        sm_client = self.session.client('azure.mgmt.storage.StorageManagementClient')
        accounts = sm_client.storage_accounts.list_by_resource_group(self.group_name)
        found = self.storage_name in [a.name for a in accounts]
        account = None
        if not found:
            params = {'sku': {'name': 'Standard_LRS'},
                      'kind': 'Storage',
                      'location': self.location}
            account = sm_client.storage_accounts.create(self.group_name, self.storage_name, params)

        # Deploy app insights if needed
        ai_client = \
            self.session.client(
                'azure.mgmt.applicationinsights.ApplicationInsightsManagementClient')
        try:
            ai_client.get(self.group_name, self.service_plan_name)
        except Exception:
            params = {
                'location': self.location,
                'application_type': self.webapp_name,
                'request_source': 'IbizaWebAppExtensionCreate',
                'kind': 'web'
            }
            ai_client.components.create_or_update(self.group_name, self.service_plan_name, params)

        # Deploy App Service Plan
        self.service_plan = \
            self.web_client.app_service_plans.get(self.group_name, self.service_plan_name)
        if not self.service_plan:
            plan = AppServicePlan(
                app_service_plan_name=self.service_plan_name,
                location=self.location,
                sku=SkuDescription(
                    name=self.sku_name,
                    capacity=1,
                    tier=self.sku_tier),
                kind='linux')

            self.service_plan = \
                self.web_client.app_service_plans.create_or_update(self.group_name,
                                                                   self.service_plan_name,
                                                                   plan).result()
     #       self.service_plan = self.web_client.app_service_plans.get(self.group_name, self.service_plan_name)

        # Wait until SA is provisioned
        if account:
            account.result()

    def deploy_web_app(self):
        existing_webapp = self.web_client.web_apps.get(self.group_name, self.webapp_name)
        if not existing_webapp:
            functionapp_util = FunctionAppUtilities()
            functionapp_util.deploy_webapp(self.webapp_name,
                                           self.group_name, self.service_plan,
                                           self.storage_name)
        else:
            self.log.info("Found existing App %s (%s) in group %s" %
                          (self.webapp_name, existing_webapp.location, self.group_name))

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
