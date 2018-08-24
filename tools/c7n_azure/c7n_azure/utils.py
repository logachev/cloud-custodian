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
from azure.mgmt.resource.resources.models import GenericResource, ResourceGroupPatchable
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


class TagHelper:

    log = logging.getLogger('custodian.azure.utils.TagHelper')

    @staticmethod
    def update_resource_tags(tag_action, resource, tags):
        client = tag_action.session.client('azure.mgmt.resource.ResourceManagementClient')

        # resource group type
        if tag_action.manager.type == 'resourcegroup':
            params_patch = ResourceGroupPatchable(
                tags=tags
            )
            client.resource_groups.update(
                resource['name'],
                params_patch,
            )
        # other Azure resources
        else:
            # generic armresource tagging isn't supported yet Github issue #2637
            if tag_action.manager.type == 'armresource':
                raise NotImplementedError('Cannot tag generic ARM resources.')

            api_version = tag_action.session.resource_api_version(resource['id'])

            # deserialize the original object
            az_resource = GenericResource.deserialize(resource)

            # create a GenericResource object with the required parameters
            generic_resource = GenericResource(location=az_resource.location,
                                               tags=tags,
                                               properties=az_resource.properties,
                                               kind=az_resource.kind,
                                               managed_by=az_resource.managed_by,
                                               identity=az_resource.identity)

            try:
                client.resources.update_by_id(resource['id'], api_version, generic_resource)
            except Exception as e:
                TagHelper.log.error("Failed to update tags for the resource.\n"
                                    "Type: {0}.\n"
                                    "Name: {1}.\n"
                                    "Error: {2}".format(resource['type'], resource['name'], e))

    @staticmethod
    def remove_tags(tag_action, resource, tags_to_delete):
        # get existing tags
        tags = resource.get('tags', {})

        # only determine if any tags_to_delete exist on the resource
        tags_exist = False
        for tag in tags_to_delete:
            if tag in tags:
                tags_exist = True
                break

        # only call the resource update if there are tags to delete tags
        if tags_exist:
            resource_tags = {key: tags[key] for key in tags if key not in tags_to_delete}
            TagHelper.update_resource_tags(tag_action, resource, resource_tags)

    @staticmethod
    def add_tags(tag_action, resource, tags_to_add):
        new_or_updated_tags = False

        # get existing tags
        tags = resource.get('tags', {})

        # add or update tags
        for key in tags_to_add:

            # nothing to do if the tag and value already exists on the resource
            if key in tags:
                if tags[key] != tags_to_add[key]:
                    new_or_updated_tags = True
            else:
                # the tag doesn't exist or the value was updated
                new_or_updated_tags = True

            tags[key] = tags_to_add[key]

        # call the arm resource update method if there are new or updated tags
        if new_or_updated_tags:
            TagHelper.update_resource_tags(tag_action, resource, tags)

    @staticmethod
    def get_tag_value(resource, tag, enforce_utf_8=False, to_lower=False, strip_chars=[]):
        """Get the resource's tag value."""

        found = False
        tags = resource.get('tags', {})

        for key in tags.keys():
            if key.lower() == tag.lower():
                found = tags[key]
                break

        if found is not False:
            if enforce_utf_8:
                found = found.encode('utf8').decode('utf8')
            if to_lower:
                found = found.lower()
            for c in strip_chars:
                found = found.strip(c)
        return found
