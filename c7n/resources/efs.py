# Copyright 2015-2017 Capital One Services, LLC
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

from c7n.actions import Action
from c7n.filters.kms import KmsRelatedFilter
from c7n.manager import resources
from c7n.filters.vpc import SecurityGroupFilter, SubnetFilter
from c7n.query import QueryResourceManager, ChildResourceManager, TypeInfo
from c7n.tags import universal_augment, register_universal_tags
from c7n.utils import local_session, type_schema, get_retry


@resources.register('efs')
class ElasticFileSystem(QueryResourceManager):

    class resource_type(TypeInfo):
        service = 'efs'
        enum_spec = ('describe_file_systems', 'FileSystems', None)
        id = 'FileSystemId'
        name = 'Name'
        date = 'CreationTime'
        dimension = 'FileSystemId'
        arn_type = 'file-system'
        arn_service = 'elasticfilesystem'
        filter_name = 'FileSystemId'
        filter_type = 'scalar'

    def augment(self, resources):
        return universal_augment(
            self, super(ElasticFileSystem, self).augment(resources))


register_universal_tags(
    ElasticFileSystem.filter_registry,
    ElasticFileSystem.action_registry)


@resources.register('efs-mount-target')
class ElasticFileSystemMountTarget(ChildResourceManager):

    class resource_type(TypeInfo):
        service = 'efs'
        parent_spec = ('efs', 'FileSystemId', None)
        enum_spec = ('describe_mount_targets', 'MountTargets', None)
        name = id = 'MountTargetId'
        filter_name = 'MountTargetId'
        filter_type = 'scalar'
        arn = False


@ElasticFileSystemMountTarget.filter_registry.register('subnet')
class Subnet(SubnetFilter):

    RelatedIdsExpression = "SubnetId"


@ElasticFileSystemMountTarget.filter_registry.register('security-group')
class SecurityGroup(SecurityGroupFilter):

    efs_group_cache = None

    RelatedIdsExpression = ""

    def get_related_ids(self, resources):

        if self.efs_group_cache:
            group_ids = set()
            for r in resources:
                group_ids.update(
                    self.efs_group_cache.get(r['MountTargetId'], ()))
            return list(group_ids)

        client = local_session(self.manager.session_factory).client('efs')
        groups = {}
        group_ids = set()
        retry = get_retry(('Throttled',), 12)

        for r in resources:
            groups[r['MountTargetId']] = retry(
                client.describe_mount_target_security_groups,
                MountTargetId=r['MountTargetId'])['SecurityGroups']
            group_ids.update(groups[r['MountTargetId']])

        self.efs_group_cache = groups
        return list(group_ids)


@ElasticFileSystem.filter_registry.register('kms-key')
class KmsFilter(KmsRelatedFilter):
    """
    Filter a resource by its associcated kms key and optionally the aliasname
    of the kms key by using 'c7n:AliasName'

    :example:

        .. code-block:: yaml

            policies:
                - name: efs-kms-key-filters
                  resource: efs
                  filters:
                    - type: kms-key
                      key: c7n:AliasName
                      value: "^(alias/aws/)"
                      op: regex
    """
    RelatedIdsExpression = 'KmsKeyId'


@ElasticFileSystem.action_registry.register('delete')
class Delete(Action):

    schema = type_schema('delete')
    permissions = ('efs:DescribeMountTargets',
                   'efs:DeleteMountTargets',
                   'efs:DeleteFileSystem')

    def process(self, resources):
        client = local_session(self.manager.session_factory).client('efs')
        self.unmount_filesystems(resources)
        retry = get_retry(('FileSystemInUse',), 12)
        for r in resources:
            retry(client.delete_file_system, FileSystemId=r['FileSystemId'])

    def unmount_filesystems(self, resources):
        client = local_session(self.manager.session_factory).client('efs')
        for r in resources:
            if not r['NumberOfMountTargets']:
                continue
            for t in client.describe_mount_targets(
                    FileSystemId=r['FileSystemId'])['MountTargets']:
                client.delete_mount_target(MountTargetId=t['MountTargetId'])
