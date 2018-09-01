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
import datetime
import logging
import six

from azure.graphrbac.models import GetObjectsParameters, AADObject
from msrestazure.azure_exceptions import CloudError
from msrestazure.tools import parse_resource_id


class ResourceIdParser(object):

    @staticmethod
    def get_namespace(resource_id):
        return parse_resource_id(resource_id).get('namespace')

    @staticmethod
    def get_resource_group(resource_id):
        result = parse_resource_id(resource_id).get("resource_group")
        # parse_resource_id fails to parse resource id for resource groups
        if result is None:
            return resource_id.split('/')[4]
        return result

    @staticmethod
    def get_resource_type(resource_id):
        parsed = parse_resource_id(resource_id)
        # parse_resource_id returns dictionary with "child_type_#" to represent
        # types sequence. "type" stores root type.
        child_type_keys = [k for k in parsed.keys() if k.find("child_type_") != -1]
        types = [parsed.get(k) for k in sorted(child_type_keys)]
        types.insert(0, parsed.get('type'))
        return '/'.join(types)

    @staticmethod
    def get_resource_name(resource_id):
        return parse_resource_id(resource_id).get('resource_name')


class StringUtils(object):

    @staticmethod
    def equal(a, b, case_insensitive=True):
        if isinstance(a, six.string_types) and isinstance(b, six.string_types):
            if case_insensitive:
                return a.strip().lower() == b.strip().lower()
            else:
                return a.strip() == b.strip()

        return False


def utcnow():
    """The datetime object for the current time in UTC
    """
    return datetime.datetime.utcnow()


def now(tz=None):
    """The datetime object for the current time in UTC
    """
    return datetime.datetime.now(tz=tz)


class Math(object):

    @staticmethod
    def mean(numbers):
        clean_numbers = [e for e in numbers if e is not None]
        return float(sum(clean_numbers)) / max(len(clean_numbers), 1)

    @staticmethod
    def sum(numbers):
        clean_numbers = [e for e in numbers if e is not None]
        return float(sum(clean_numbers))


class GraphHelper(object):
    log = logging.getLogger('custodian.azure.utils.GraphHelper')

    @staticmethod
    def get_principal_dictionary(graph_client, object_ids):
        object_params = GetObjectsParameters(
            include_directory_object_references=True,
            object_ids=object_ids)

        principal_dics = {object_id: AADObject() for object_id in object_ids}

        aad_objects = graph_client.objects.get_objects_by_object_ids(object_params)
        try:
            for aad_object in aad_objects:
                principal_dics[aad_object.object_id] = aad_object
        except CloudError:
            GraphHelper.log.warning(
                'Credentials not authorized for access to read from Microsoft Graph. \n '
                'Can not query on principalName, displayName, or aadType. \n')

        return principal_dics

    @staticmethod
    def get_principal_name(graph_object):
        if graph_object.user_principal_name:
            return graph_object.user_principal_name
        elif graph_object.service_principal_names:
            return graph_object.service_principal_names[0]
        return graph_object.display_name or ''


class PortsRangeHelper(object):

    """ Given a string with a port or port range: '80', '80-120'
        Returns tuple with range start and end ports: (80, 80), (80, 120)
    """
    @staticmethod
    def get_port_range(range_str):
        if range_str == '*':
            return (0, 65535)

        s = range_str.split('-')
        if len(s) == 2:
            return (int(s[0]), int(s[1]))

        return (int(s[0]), int(s[0]))

    """ Extracts ports ranges from the NSG rule object
        Returns an array of tuples with port ranges
    """
    @staticmethod
    def get_rule_port_ranges(rule):
        properties = rule['properties']
        if 'destinationPortRange' in properties:
            return [PortsRangeHelper.get_port_range(properties['destinationPortRange'])]
        else:
            return [PortsRangeHelper.get_port_range(r) for r in properties['destinationPortRanges']]

    """ Converts array of port ranges to the set of integers
        Example: [(10-12), (20,20)] -> {10, 11, 12, 20}
    """
    @staticmethod
    def port_ranges_to_set(ranges):
        return set([i for r in ranges for i in range(r[0], r[1] + 1)])

    """ Convert ports range string to the set of integers
        Example: "10-12, 20" -> {10, 11, 12, 20}
    """
    @staticmethod
    def get_ports_set_from_string(ports):
        ranges = [PortsRangeHelper.get_port_range(r) for r in ports.split(',') if r != '']
        return PortsRangeHelper.port_ranges_to_set(ranges)

    """ Extract port ranges from NSG rule and convert it to the set of integers
    """
    @staticmethod
    def get_ports_set_from_rule(rule):
        ranges = PortsRangeHelper.get_rule_port_ranges(rule)
        return PortsRangeHelper.port_ranges_to_set(ranges)

    """ Build entire ports array filled with True (Allow), False (Deny) and None(default - Deny)
        based on the provided Network Security Group object, direction and protocol.
    """
    @staticmethod
    def build_ports_array(nsg, direction_key, ip_protocol):
        rules = nsg['properties']['securityRules']
        rules = sorted(rules, key=lambda k: k['properties']['priority'])
        ports = [None for i in range(65536)]

        for rule in rules:
            if not StringUtils.equal(direction_key, rule['properties']['direction']):
                continue

            protocol = rule['properties']['protocol']
            if not StringUtils.equal(protocol, "*") and \
               not StringUtils.equal(ip_protocol, "*") and \
               not StringUtils.equal(protocol, ip_protocol):
                continue

            access = StringUtils.equal(rule['properties']['access'], 'allow')
            ports_set = PortsRangeHelper.get_ports_set_from_rule(rule)

            for p in ports_set:
                if ports[p] is None:
                    ports[p] = access

        return ports
