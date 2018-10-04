# Copyright 2016-2017 Capital One Services, LLC
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
from __future__ import absolute_import, division, print_function, unicode_literals

import json
import os
import logging

from c7n_azure.session import Session
from c7n.utils import local_session

try:
    from c7n_azure.function_package import FunctionPackage
    from c7n_azure.functionapp_utils import FunctionAppUtilities
    from c7n_azure.constants import CONST_DOCKER_VERSION, CONST_FUNCTIONS_EXT_VERSION
except ImportError:
    FunctionPackage = None
    CONST_DOCKER_VERSION = CONST_FUNCTIONS_EXT_VERSION = None
    pass


def provision(config):
    session = local_session(Session)
    log = logging.getLogger('c7n_mailer.azure.deploy')

    function_name = config.get('function_name', 'mailer')
    group_name = config.get('function_servicePlanName', 'cloudcustodian')
    service_plan_name = config.get('function_servicePlanName', 'cloudcustodian')
    storage_name = config.get('function_servicePlanName', 'cloudcustodian')
    webapp_name = (service_plan_name + '-' + function_name).replace(' ', '-').lower()
    schedule=config.get('function_schedule', '0 */10 * * * *')

    app_parameters = FunctionAppUtilities.FunctionAppInfrastructureParameters(
        group_name=group_name,
        location=config.get('function_location', 'West US2'),
        app_insights_location=config.get('function_appInsightsLocation', 'West US2'),
        storage_name=storage_name,
        service_plan_name=service_plan_name,
        sku_name=config.get('function_skuCode', 'B1'),
        sku_tier=config.get('function_sku', 'Basic'),
        webapp_name=webapp_name)

    functionapp_util = FunctionAppUtilities()
    service_plan = functionapp_util.deploy_infrastructure(app_parameters)

    # Check if already existing
    web_client = session.client('azure.mgmt.web.WebSiteManagementClient')
    existing_webapp = web_client.web_apps.get(group_name, webapp_name)

    # Deploy
    if not existing_webapp:
        functionapp_util.deploy_webapp(webapp_name,
                                       group_name, service_plan,
                                       storage_name)
    else:
        log.info("Found existing App %s (%s) in group %s" %
                 (webapp_name, existing_webapp.location, group_name))

    log.info("Building function package for %s" % webapp_name)

    # Build package
    packager = FunctionPackage(
        function_name,
        os.path.join(os.path.dirname(__file__), 'function.py'))

    packager.build(None,
                   entry_point=os.path.join(os.path.dirname(__file__), 'handle.py'),
                   extra_modules={'c7n_mailer', 'ruamel'})

    packager.pkg.add_contents(
        function_name + '/config.json',
        contents=json.dumps(config))

    packager.pkg.add_contents(
        function_name + '/function.json',
        contents=packager.get_function_config({'mode':
                                              {'type': 'azure-periodic',
                                               'schedule': schedule}}))
    # Add mail templates
    template_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '../..', 'msg-templates'))

    for t in os.listdir(template_dir):
        with open(os.path.join(template_dir, t)) as fh:
            packager.pkg.add_contents('msg-templates/%s' % t, fh.read())

    packager.close()

    if packager.wait_for_status(webapp_name):
        packager.publish(webapp_name)
    else:
        log.error("Aborted deployment, ensure Application Service is healthy.")
