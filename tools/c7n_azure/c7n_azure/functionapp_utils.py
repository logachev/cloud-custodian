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

import os
import logging
from binascii import hexlify

from azure.mgmt.web.models import (Site, SiteConfig, NameValuePair)
from c7n_azure.session import Session
from c7n_azure.constants import CONST_DOCKER_VERSION, CONST_FUNCTIONS_EXT_VERSION

from c7n.utils import local_session

from azure.mgmt.web.models import AppServicePlan, SkuDescription


class FunctionAppUtilities(object):
    def __init__(self):
        self.local_session = local_session(Session)
        self.log = logging.getLogger('custodian.azure.function_app_utils')

    @staticmethod
    def generate_machine_decryption_key():
        # randomly generated decryption key for Functions key
        return str(hexlify(os.urandom(32)).decode()).upper()

    class FunctionAppInfrastructureParameters:
        def __init__(self, group_name, location, storage_name,
                     service_plan_name, sku_name, sku_tier, webapp_name):
            self.group_name = group_name
            self.location = location
            self.storage_name = storage_name
            self.service_plan_name = service_plan_name
            self.sku_name = sku_name
            self.sku_tier = sku_tier
            self.webapp_name = webapp_name

    def deploy_infrastructure(self, parameters):
        # Check if RG exists
        session = self.local_session
        rg_client = session.client('azure.mgmt.resource.ResourceManagementClient')
        if not rg_client.resource_groups.check_existence(parameters.group_name):
            self.log.info("Deploying resource group %s" % (parameters.group_name))
            rg_client.resource_groups.create_or_update(parameters.group_name,
                                                       {'location': parameters.location})
        else:
            self.log.info("Found resource group %s" % (parameters.group_name))

        # Storage account create function is async, wait for completion after
        # other resources provisioned.
        sm_client = session.client('azure.mgmt.storage.StorageManagementClient')
        accounts = sm_client.storage_accounts.list_by_resource_group(parameters.group_name)
        found = parameters.storage_name in [a.name for a in accounts]
        account = None
        if not found:
            self.log.info("Deploying storage account %s in %s resource group" %
                          (parameters.storage_name, parameters.group_name))
            params = {'sku': {'name': 'Standard_LRS'},
                      'kind': 'Storage',
                      'location': parameters.location}
            account = sm_client.storage_accounts.create(parameters.group_name,
                                                        parameters.storage_name,
                                                        params)
        else:
            self.log.info("Found storage account %s in %s resource group" %
                          (parameters.storage_name, parameters.group_name))

        # Deploy app insights if needed
        ai_client = \
            session.client(
                'azure.mgmt.applicationinsights.ApplicationInsightsManagementClient')
        try:
            ai_client.get(parameters.group_name, parameters.service_plan_name)
            self.log.info("Found app insights %s in %s resource group" %
                          (parameters.service_plan_name, parameters.group_name))
        except Exception:
            self.log.info("Deploying app insights %s in %s resource group" %
                          (parameters.service_plan_name, parameters.group_name))
            params = {
                'location': parameters.location,
                'application_type': parameters.webapp_name,
                'request_source': 'IbizaWebAppExtensionCreate',
                'kind': 'web'
            }
            ai_client.components.create_or_update(parameters.group_name,
                                                  parameters.service_plan_name,
                                                  params)

        # Deploy App Service Plan
        web_client = session.client('azure.mgmt.web.WebSiteManagementClient')
        service_plan = \
            web_client.app_service_plans.get(parameters.group_name, parameters.service_plan_name)
        if not service_plan:
            self.log.info("Deploying app service plan %s in %s resource group" %
                (parameters.service_plan_name, parameters.group_name))
            plan = AppServicePlan(
                app_service_plan_name=parameters.service_plan_name,
                location=parameters.location,
                sku=SkuDescription(
                    name=parameters.sku_name,
                    capacity=1,
                    tier=parameters.sku_tier),
                kind='linux',
                target_worker_size_id=0,
                reserved=True)

            service_plan = \
                web_client.app_service_plans.create_or_update(parameters.group_name,
                                                              parameters.service_plan_name,
                                                              plan).result()
        else:
            self.log.info("Found app service plan %s in %s resource group" %
                (parameters.service_plan_name, parameters.group_name))


        # Wait until SA is provisioned
        if account:
            self.log.info("Waiting for %s storage account" %
                (parameters.service_plan_name))
            account.result()
        return service_plan

    def deploy_webapp(self, app_name, group_name, service_plan, storage_account_name):
        self.log.info("Deploying Function App %s (%s) in group %s" %
                      (app_name, service_plan.location, group_name))

        site_config = SiteConfig(app_settings=[])
        functionapp_def = Site(location=service_plan.location, site_config=site_config)

        functionapp_def.kind = 'functionapp,linux'
        functionapp_def.server_farm_id = service_plan.id

        site_config.linux_fx_version = CONST_DOCKER_VERSION
        site_config.always_on = True

        app_insights_key = self.get_application_insights_key(group_name,
                                                             service_plan.app_service_plan_name)

        if app_insights_key:
            site_config.app_settings.append(
                NameValuePair('APPINSIGHTS_INSTRUMENTATIONKEY', app_insights_key))

        con_string = self.get_storage_connection_string(group_name, storage_account_name)
        site_config.app_settings.append(NameValuePair('AzureWebJobsStorage', con_string))
        site_config.app_settings.append(NameValuePair('AzureWebJobsDashboard', con_string))
        site_config.app_settings.append(NameValuePair('FUNCTIONS_EXTENSION_VERSION',
                                                      CONST_FUNCTIONS_EXT_VERSION))
        site_config.app_settings.append(NameValuePair('FUNCTIONS_WORKER_RUNTIME', 'python'))
        site_config.app_settings.append(
            NameValuePair('MACHINEKEY_DecryptionKey',
                          FunctionAppUtilities.generate_machine_decryption_key()))

        #: :type: azure.mgmt.web.WebSiteManagementClient
        web_client = self.local_session.client('azure.mgmt.web.WebSiteManagementClient')
        web_client.web_apps.create_or_update(group_name, app_name, functionapp_def).wait()

    def get_storage_connection_string(self, resource_group_name, storage_account_name):
        #: :type: azure.mgmt.web.WebSiteManagementClient
        storage_client = self.local_session.client('azure.mgmt.storage.StorageManagementClient')

        obj = storage_client.storage_accounts.list_keys(resource_group_name,
                                                        storage_account_name)

        connection_string = 'DefaultEndpointsProtocol={};AccountName={};AccountKey={}'.format(
            'https',
            storage_account_name,
            obj.keys[0].value)

        return connection_string

    def get_application_insights_key(self, resource_group_name, application_insights_name):
        #: :type: azure.mgmt.applicationinsights.ApplicationInsightsManagementClient
        insights_client = self.local_session.client(
            'azure.mgmt.applicationinsights.ApplicationInsightsManagementClient')

        try:
            app_insights = insights_client.components.get(resource_group_name,
                                                          application_insights_name)
            return app_insights.instrumentation_key

        except Exception:
            return False
