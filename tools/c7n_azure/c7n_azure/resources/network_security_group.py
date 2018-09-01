# Copyright 2018 Capital One Services, LLC
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

import re
import uuid

from c7n.actions import BaseAction
from c7n.filters import Filter, FilterValidationError
from c7n.filters.core import PolicyValidationError
from c7n.utils import type_schema

from c7n_azure.provider import resources
from c7n_azure.resources.arm import ArmResourceManager
from c7n_azure.utils import StringUtils, PortsRangeHelper


@resources.register('networksecuritygroup')
class NetworkSecurityGroup(ArmResourceManager):
    class resource_type(object):
        service = 'azure.mgmt.network'
        client = 'NetworkManagementClient'
        enum_spec = ('network_security_groups', 'list_all', None)
        id = 'id'
        name = 'name'
        default_report_fields = (
            'name',
            'location',
            'resourceGroup'
        )


DIRECTION = 'direction'
PORTS = 'ports'
PORTS_OP = 'ports-op'
EXCEPT_PORTS = 'exceptPorts'
IP_PROTOCOL = 'ipProtocol'
ACCESS = 'access'


class SecurityRuleFilter(Filter):
    """
    Filter on Security Rules within a Network Security Group
    """

    schema = {
        'type': 'object',
        'properties': {
            'type': {'enum': []},
            PORTS_OP: {'type': 'string', 'enum': ['all', 'any']},
            PORTS: {'type': 'string'},
            EXCEPT_PORTS: {'type': 'string'},
            IP_PROTOCOL: {'type': 'string', 'enum': ['TCP', 'UDP', '*']},
            ACCESS: {'type': 'string', 'enum': ['Allow', 'Deny']},
        },
        'required': ['type', ACCESS]
    }

    def validate(self):
        # Check that variable values are valid

        pattern = re.compile('^\\d+(-\\d+)?(,\\d+(-\\d+)?)*$')
        if PORTS in self.data:
            if pattern.match(self.data[PORTS]) is None:
                raise FilterValidationError("ports string has wrong format.")

        if EXCEPT_PORTS in self.data:
            if pattern.match(self.data[EXCEPT_PORTS]) is None:
                raise FilterValidationError("exceptPorts string has wrong format.")
        return True

    def process(self, network_security_groups, event=None):
        # Get variables
        self.ip_protocol = self.data.get(IP_PROTOCOL, '*')
        self.access = StringUtils.equal(self.data.get(ACCESS), "Allow")
        self.ports_op = self.data.get(PORTS_OP, 'all')

        # Calculate ports from the settings:
        #   If ports not specified -- assuming the entire range
        #   If except_ports not specifed -- nothing
        ports_set = PortsRangeHelper.get_ports_set_from_string(self.data.get(PORTS, '0-65535'))
        except_set = PortsRangeHelper.get_ports_set_from_string(self.data.get(EXCEPT_PORTS, ''))
        self.ports = ports_set.difference(except_set)

        nsgs = [nsg for nsg in network_security_groups if self.check_nsg(nsg)]
        return nsgs

    def check_nsg(self, nsg):
        nsg_ports = PortsRangeHelper.build_ports_array(nsg, self.direction_key, self.ip_protocol)

        allow = len([p for p in self.ports if nsg_ports[p]])
        deny = len(self.ports) - allow

        if self.ports_op == 'all':
            if self.access:
                return deny == 0
            else:
                return allow == 0
        if self.ports_op == 'any':
            if self.access:
                return allow > 0
            else:
                return deny > 0


@NetworkSecurityGroup.filter_registry.register('ingress')
class IngressFilter(SecurityRuleFilter):
    direction_key = 'Inbound'
    schema = type_schema('ingress', rinherit=SecurityRuleFilter.schema)


@NetworkSecurityGroup.filter_registry.register('egress')
class EgressFilter(SecurityRuleFilter):
    direction_key = 'Outbound'
    schema = type_schema('egress', rinherit=SecurityRuleFilter.schema)


class NetworkSecurityGroupPortsAction(BaseAction):
    """
    Action to perform on Network Security Groups
    """

    schema = {
        'type': 'object',
        'properties': {
            'type': {'enum': []},
            PORTS: {'type': 'string'},
            EXCEPT_PORTS: {'type': 'string'},
            IP_PROTOCOL: {'type': 'string', 'enum': ['TCP', 'UDP', '*']},
            DIRECTION: {'type': 'string', 'enum': ['Inbound', 'Outbound']}
        },
        'required': ['type', DIRECTION]
    }

    def validate(self):
        # Check that variable values are valid

        pattern = re.compile('^\\d+(-\\d+)?(,\\d+(-\\d+)?)*$')
        if PORTS in self.data:
            if pattern.match(self.data[PORTS]) is None:
                raise PolicyValidationError("ports string has wrong format.")

        if EXCEPT_PORTS in self.data:
            if pattern.match(self.data[EXCEPT_PORTS]) is None:
                raise PolicyValidationError("exceptPorts string has wrong format.")
        return True

    def build_ports_string(self, nsg, direction_key, ip_protocol):
        # Build list of ports for a given nsg, True if allow, False if Deny
        nsg_ports = PortsRangeHelper.build_ports_array(nsg, direction_key, ip_protocol)
        nsg_ports = [False if x is None else x for x in nsg_ports]

        access = StringUtils.equal(self.access_action, "allow")

        # Find ports with different access level from NSG and this action
        diff_ports = sorted([p for p in self.action_ports if nsg_ports[p] != access])

        # diff_ports empty means this NSG already satisfies action conditions
        if len(diff_ports) == 0:
            return ""

        # Transform diff_ports list to the ranges list
        first = 0
        result = []
        for it in range(1, len(diff_ports)):
            if diff_ports[first] == diff_ports[it] - (it - first):
                continue
            result.append((diff_ports[first], diff_ports[it - 1]))
            first = it

        # Update tuples with strings, representing ranges
        result.append((diff_ports[first], diff_ports[-1]))
        result = [str(x[0]) if x[0] == x[1] else "%i-%i" % (x[0], x[1]) for x in result]

        return result

    def process(self, network_security_groups):

        ip_protocol = self.data.get(IP_PROTOCOL, '*')
        direction = self.data[DIRECTION]
        # Build a list of ports described in the action.
        ports = PortsRangeHelper.get_ports_set_from_string(self.data.get(PORTS, '0-65535'))
        except_ports = PortsRangeHelper.get_ports_set_from_string(self.data.get(EXCEPT_PORTS, ''))
        self.action_ports = ports.difference(except_ports)

        for nsg in network_security_groups:
            nsg_name = nsg['name']
            resource_group = nsg['resourceGroup']

            # Get list of ports to Deny or Allow access to.
            ports = self.build_ports_string(nsg, direction, ip_protocol)
            if ports == '':
                # If its empty, it means NSG already blocks/allows access to all ports,
                # no need to change.
                self.manager.log.info("Network security group %s satisfies provided "
                                      "ports configuration, no actions scheduled.", nsg_name)
                continue

            rules = nsg['properties']['securityRules']
            rules = sorted(rules, key=lambda k: k['properties']['priority'])
            rules = [r for r in rules
                     if StringUtils.equal(r['properties']['direction'], direction)]
            lowest_priority = rules[0]['properties']['priority'] if len(rules) > 0 else 4096

            # Create new top-priority rule to allow/block ports from the action.
            rule_name = 'c7n-policy-' + str(uuid.uuid1())
            new_rule = {
                'name': rule_name,
                'properties': {
                    'access': self.access_action,
                    'destinationAddressPrefix': '*',
                    'destinationPortRanges': ports,
                    'direction': self.data[DIRECTION],
                    'priority': lowest_priority - 10,
                    'protocol': ip_protocol,
                    'sourceAddressPrefix': '*',
                    'sourcePortRange': '*',
                }
            }
            self.manager.log.info("NSG %s. Creating new rule to %s access for ports %s",
                                  nsg_name, self.access_action, ports)

            self.manager.get_client().security_rules.create_or_update(
                resource_group,
                nsg_name,
                rule_name,
                new_rule
            )


@NetworkSecurityGroup.action_registry.register('close')
class CloseRules(NetworkSecurityGroupPortsAction):
    """
    Deny access to Security Rule
    """
    schema = type_schema('close', rinherit=NetworkSecurityGroupPortsAction.schema)
    access_action = 'Deny'


@NetworkSecurityGroup.action_registry.register('open')
class OpenRules(NetworkSecurityGroupPortsAction):
    """
    Allow access to Security Rule
    """
    schema = type_schema('open', rinherit=NetworkSecurityGroupPortsAction.schema)
    access_action = 'Allow'
