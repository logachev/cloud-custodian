#!/usr/bin/env python
"""Policy Changes from Git.
---------------------------

Using custodian in accordance with infrastructure as code principles,
we store policy assets in a versioned control repository. This
provides for an audit log and facilitate change reviews. However this
capability is primarily of use to humans making semantic
interpretations of changes. This script also provides logical custodian
policy changes over a git repo and allows streaming those changes.


Two example use cases:

  - Doing dryrun only on changed policies within a pull request
  - Dashboard metrics of policy changes

Install
+++++++

Pre-requisites. pygit2, click and custodian/c7n.

Usage
+++++

Streaming use case (default stream is to stdout, also supports kinesis and sqs)::

  $ python tools/ops/policystream.py stream -r foo
  2018-08-12 12:37:00,567: c7n.policystream:INFO Cloning repository: foo
  <policy-add policy:foi provider:aws resource:ec2 date:2018-08-02T15:13:28-07:00 author:Kapil commit:09cb85>
  <policy-moved policy:foi provider:aws resource:ec2 date:2018-08-02T15:14:24-07:00 author:Kapil commit:76fce7>
  <policy-remove policy:foi provider:aws resource:ec2 date:2018-08-02T15:14:46-07:00 author:Kapil commit:570ca4>
  <policy-add policy:ec2-guard-duty provider:aws resource:ec2 date:2018-08-02T15:14:46-07:00 author:Kapil commit:570ca4>
  <policy-add policy:ec2-run provider:aws resource:ec2 date:2018-08-02T15:16:00-07:00 author:Kapil commit:d3d8d4>
  <policy-remove policy:ec2-run provider:aws resource:ec2 date:2018-08-02T15:18:31-07:00 author:Kapil commit:922c1a>
  <policy-modified policy:ec2-guard-duty provider:aws resource:ec2 date:2018-08-12T09:39:43-04:00 author:Kapil commit:189ea1>
  2018-08-12 12:37:01,275: c7n.policystream:INFO Streamed 7 policy changes


Diff use case, output policies changes in the last commit::

  $ python tools/ops/policystream.py diff -r foo -v


Pull request use, output policies changes between two branches::

  $ python tools/ops/policystream.py diff-tree -r foo
  policies:
  - filters:
    - {type: cross-account}
    name: lambda-access-check
    resource: aws.lambda

""" # NOQA
import click
import contextlib
from datetime import datetime, timedelta
from dateutil.tz import tzoffset
from functools import partial
import json
import logging
import shutil
import os
import tempfile
import pygit2
import yaml

from c7n.config import Config
from c7n.credentials import SessionFactory
from c7n.policy import PolicyCollection as BaseCollection
from c7n.policy import Policy as BasePolicy
from c7n.resources import load_resources
from c7n.utils import get_retry

import boto3


log = logging.getLogger('c7n.policystream')

EMPTY_TREE = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'


class TempDir(object):

    def __init__(self):
        self.path = None

    def open(self):
        self.path = tempfile.mkdtemp()
        return self

    def close(self):
        if not self.path:
            return
        shutil.rmtree(self.path)


class ChangeType(object):

    ADD = 1
    REMOVE = 2
    MODIFIED = 3
    MOVED = 4


CHANGE_TYPE = {
    1: 'ADD',
    2: 'REMOVE',
    3: 'MODIFIED',
    4: 'MOVED'
}

GIT_DELTA = {
    0: 'GIT_DELTA_UNMODIFIED',
    1: 'GIT_DELTA_ADDED',
    2: 'GIT_DELTA_DELETED',
    3: 'GIT_DELTA_MODIFIED',
    4: 'GIT_DELTA_RENAMED',
    5: 'GIT_DELTA_COPIED',
    6: 'GIT_DELTA_IGNORED',
    7: 'GIT_DELTA_UNTRACKED',
    8: 'GIT_DELTA_TYPECHANGE',
    9: 'GIT_DELTA_UNREADABLE'}

GIT_DELTA_INVERT = {v: k for k, v in GIT_DELTA.items()}


class PolicyChange(object):
    """References a policy change within a given commit.
    """

    def __init__(self, policy, repo_uri, commit, change, previous=None):
        self.policy = policy
        self.repo_uri = repo_uri
        self.commit = commit
        self.kind = change
        self.previous = previous

    @property
    def file_path(self):
        return self.policy.file_path

    @property
    def date(self):
        return commit_date(self.commit)

    def __repr__(self):

        return "<policy-{} policy:{} provider:{} resource:{} date:{} author:{} commit:{}>".format(
            CHANGE_TYPE[self.kind].lower(),
            self.policy.name,
            self.policy.provider_name,
            self.policy.resource_type,
            self.date.isoformat(),
            self.commit.author.name,
            str(self.commit.id)[:6])

    def data(self, indent=2):
        d = {
            'change': CHANGE_TYPE[self.kind].lower(),
            'repo_uri': self.repo_uri,
            'policy': {
                'data': dict(self.policy.data),
                'file': self.policy.file_path,
            },
            'commit': {
                'id': str(self.commit.id),
                'message': self.commit.message,
                'author': str(self.commit.author.name),
                'email': str(self.commit.author.email),
                'date': self.date.isoformat(),
            }
        }
        if self.previous:
            d['previous'] = {
                'data': dict(self.previous.data),
                'file': self.previous.file_path}
        return d


class CollectionDelta(object):
    """Iterator over changes between two policy collections.

    With a given by url associated to a give commit.
    """

    change = PolicyChange

    def __init__(self, prev, curr, commit=None, repo_uri=None):
        self.prev = prev
        self.curr = curr
        self.commit = commit
        self.repo_uri = repo_uri

    def delta(self):
        removed = set(self.prev.keys()) - set(self.curr.keys())
        added = set(self.curr.keys()) - set(self.prev.keys())

        for r in removed:
            yield PolicyChange(self.prev[r], self.repo_uri, self.commit, ChangeType.REMOVE)

        for a in added:
            yield PolicyChange(self.curr[a], self.repo_uri, self.commit, ChangeType.ADD)

        for extant in set(self.curr.keys()).intersection(set(self.prev.keys())):
            if self.curr[extant].data != self.prev[extant].data:
                yield PolicyChange(
                    self.curr[extant], self.repo_uri, self.commit,
                    ChangeType.MODIFIED, self.prev[extant])
            elif self.curr[extant].file_path != self.prev[extant].file_path:
                yield PolicyChange(
                    self.curr[extant], self.repo_uri, self.commit,
                    ChangeType.MOVED, self.prev[extant])


class Policy(BasePolicy):
    """Policy that tracks its file origin."""
    def __init__(self, data, options, file_path):
        self.file_path = file_path
        self.data = data
        self.options = options


class PolicyCollection(BaseCollection):
    """Policy collection supporting collection modifications."""

    policy_class = Policy

    def __init__(self, policies=None, options=None):
        self.policies = policies or []
        self.options = options or Config.empty()
        self.pmap = {p.name: p for p in self.policies}

    def __getitem__(self, key):
        return self.pmap[key]

    def add(self, p):
        assert p.name not in self.pmap
        self.policies.append(p)
        self.pmap[p.name] = p

    def remove(self, p):
        assert p.name in self.pmap
        self.policies = [ep for ep in self.policies if ep.name != p.name]
        del self.pmap[p.name]

    def __setitem__(self, key, p):
        assert p.name in self.pmap
        self.pmap[p.name] = p
        for idx, ep in enumerate(self.policies):
            if p.name == ep.name:
                self.policies[idx] = p

    def keys(self):
        return self.pmap.keys()

    @classmethod
    def from_data(cls, data, options, file_path):
        policies = [
            cls.policy_class(p, options, file_path)
            for p in data.get('policies', ())]
        return cls(policies, options)


def commit_date(commit):
    tzinfo = tzoffset(None, timedelta(minutes=commit.author.offset))
    return datetime.fromtimestamp(float(commit.author.time), tzinfo)


def policy_path_matcher(path):
    if (path.endswith('.yaml') or path.endswith('.yml')) and not path.startswith('.'):
        return True


class PolicyRepo(object):
    """Models a git repository containing policy files.
    """
    def __init__(self, repo_uri, repo, matcher=None):
        self.repo_uri = repo_uri
        self.repo = repo
        self.policy_files = {}
        self.matcher = matcher or policy_path_matcher

    def initialize_tree(self, tree):
        assert not self.policy_files

        for tree_ent in tree:
            fpath = tree_ent.name
            if not self.matcher(fpath):
                continue
            self.policy_files[fpath] = PolicyCollection.from_data(
                yaml.safe_load(self.repo.get(tree[fpath].id).data),
                Config.empty(), fpath)

    def delta_commits(self, baseline, target):
        """Show policies changes between arbitrary commits.

        The common use form is comparing the heads of two branches.
        """

        baseline_files = {}
        for fent in baseline.tree:
            if self.matcher(fent.name):
                baseline_files[fent.name] = fent

        target_files = {}
        for fent in target.tree:
            if self.matcher(fent.name):
                target_files[fent.name] = fent

        baseline_policies = PolicyCollection()
        target_policies = PolicyCollection()

        # Added
        for f in set(target_files) - set(baseline_files):
            target_policies += self._policy_file_rev(f, target)
        # Removed
        for f in set(baseline_files) - set(target_files):
            baseline_policies += self._policy_file_rev(f, baseline)

        # Modified
        for f in set(baseline_files).intersection(target_files):
            if baseline_files[f].hex == target_files[f].hex:
                continue
            target_policies += self._policy_file_rev(f, target)
            baseline_policies += self._policy_file_rev(f, baseline)

        return CollectionDelta(
            baseline_policies, target_policies, target, self.repo_uri).delta()

    def delta_stream(self, target='HEAD', limit=None,
                sort=pygit2.GIT_SORT_TIME | pygit2.GIT_SORT_REVERSE):
        """Return an iterator of policy changes along a commit lineage in a repo.
        """
        if target == 'HEAD':
            target = self.repo.head.target

        commits = []
        for commit in self.repo.walk(target, sort):
            log.debug(
                "processing commit id:%s date:%s parents:%d msg:%s",
                str(commit.id)[:6], commit_date(commit).isoformat(),
                len(commit.parents), commit.message)
            commits.append(commit)
            if limit and len(commits) > limit:
                break

        if limit:
            self.initialize_tree(commits[limit].tree)
            commits.pop(-1)

        for commit in commits:
            for policy_change in self._process_stream_commit(commit):
                yield policy_change

    def _policy_file_rev(self, f, commit):
        try:
            return PolicyCollection.from_data(
                yaml.safe_load(self.repo.get(commit.tree[f].id).data),
                Config.empty(), f)
        except Exception as e:
            log.warning(
                "invalid policy file %s @ %s %s %s \n error:%s",
                f, str(commit.id)[:6], commit_date(commit).isoformat(),
                commit.author.name, e)
            return PolicyCollection()

    def _process_stream_commit(self, change):
        if not change.parents:
            change_diff = self.repo.diff(self.repo.get(EMPTY_TREE, change), change)
        else:
            change_diff = self.repo.diff(change.parents[0], change)

        log.debug(
            "processing commit id:%s date:%s parents:%d add:%d del:%d files:%d change:%s",
            str(change.id)[:6], commit_date(change).isoformat(), len(change.parents),
            change_diff.stats.insertions,
            change_diff.stats.deletions,
            change_diff.stats.files_changed,
            change.message.strip())

        change_policies = PolicyCollection()
        current_policies = PolicyCollection()
        removed = set()

        for delta in change_diff.deltas:
            f = delta.new_file.path
            if not self.matcher(f):
                continue
            elif delta.status == GIT_DELTA_INVERT['GIT_DELTA_ADDED']:
                change_policies += self._policy_file_rev(f, change)
                if f in self.policy_files:
                    current_policies += self.policy_files[f]
            elif delta.status == GIT_DELTA_INVERT['GIT_DELTA_MODIFIED']:
                change_policies += self._policy_file_rev(f, change)
                if f in self.policy_files:
                    current_policies += self.policy_files[f]
            elif delta.status == GIT_DELTA_INVERT['GIT_DELTA_DELETED']:
                if f in self.policy_files:
                    current_policies += self.policy_files[f]
                    removed.add(f)
            elif delta.status == GIT_DELTA_INVERT['GIT_DELTA_RENAMED']:
                change_policies += self._policy_file_rev(f, change)
                current_policies += self.policy_files[delta.old_file.path]
                removed.add(delta.old_file.path)
            else:
                log.info(
                    "unhandled delta type:%s path:%s commit_id:%s",
                    GIT_DELTA[delta.status], delta.new_file.path, change.id)
                continue

        for change in self._process_stream_delta(CollectionDelta(
                current_policies, change_policies, change, self.repo_uri).delta()):
            yield change

        for r in removed:
            del self.policy_files[r]

    def _process_stream_delta(self, delta_stream):
        """Bookkeeping on internal data structures while iterating a stream."""
        for pchange in delta_stream:
            if pchange.kind == ChangeType.ADD:
                self.policy_files.setdefault(
                    pchange.file_path, PolicyCollection()).add(pchange.policy)
            elif pchange.kind == ChangeType.REMOVE:
                self.policy_files[pchange.file_path].remove(pchange.policy)
            elif pchange.kind in (ChangeType.MOVED, ChangeType.MODIFIED):
                if pchange.policy.file_path != pchange.previous.file_path:
                    self.policy_files[pchange.previous.file_path].remove(pchange.previous)
                    self.policy_files.setdefault(
                        pchange.file_path, PolicyCollection()).add(pchange.policy)
                else:
                    self.policy_files[pchange.file_path][pchange.policy.name] = pchange.policy
            yield pchange


def parse_arn(arn):
    # http://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html
    elements = arn.split(':', 5)
    result = {
        'arn': elements[0],
        'partition': elements[1],
        'service': elements[2],
        'region': elements[3],
        'account': elements[4],
        'resource': elements[5],
        'resource_type': None
    }
    if '/' in result['resource']:
        result['resource_type'], result['resource'] = result['resource'].split('/', 1)
    elif ':' in result['resource']:
        result['resource_type'], result['resource'] = result['resource'].split(':', 1)
    return result


class Transport(object):

    BUF_SIZE = 1

    def __init__(self, session, info):
        self.session = session
        self.info = info

    def send(self, change):
        """send the given policy change"""
        self.buf.append(change)
        if len(self.buf) % self.BUF_SIZE == 0:
            self.flush()

    def flush(self):
        """flush any buffered messages"""

    def close(self):
        self.flush()


class KinesisTransport(Transport):

    BUF_SIZE = 50

    retry = staticmethod(get_retry(('ProvisionedThroughputExceededException',)))

    def __init__(self, session, info):
        self.session = session
        self.info = info
        self.client = self.session.client('kinesis', region_name=info['region'])
        self.buf = []

    def flush(self):
        if not self.buf:
            return
        self.retry(
            self.client.put_records,
            StreamName=self.info['resource'],
            Records=[
                {'Data': json.dumps(c.data()),
                 'PartitionKey': c.repo_uri}
                for c in self.buf])
        self.buf = []


class SQSTransport(Transport):

    BUF_SIZE = 10

    def __init__(self, session, info):
        self.session = session
        self.info = info
        self.client = self.session.client('sqs', region_name=info['region'])
        self.buf = []

    def flush(self):
        if not self.buf:
            return
        self.client.send_message_batch(
            QueueUrl=self.info['resource'],
            Entries=[{
                'Id': str(change.commit.id) + change.policy.name,
                'MessageDeduplicationId': str(change.commit.id) + change.policy.name,
                'MessageGroupId': change.repo_uri,
                'MessageBody': json.dumps(change.data())}
                for change in self.buf])


class OutputTransport(Transport):

    def send(self, change):
        if self.info.get('format', '') == 'json':
            print(json.dumps(change.data(), indent=2))
        else:
            print(change)


def transport(stream_uri, assume):
    if stream_uri == 'stdout':
        return OutputTransport(None, {})
    elif stream_uri == 'json':
        return OutputTransport(None, {'format': 'json'})
    if not stream_uri.startswith('arn'):
        raise ValueError("invalid transport")
    info = parse_arn(stream_uri)
    session_factory = boto3.Session
    if assume:
        session_factory = partial(SessionFactory, assume_role=assume)
    if info['service'] == 'kinesis':
        return KinesisTransport(session_factory(), info)
    elif info['service'] == 'sqs':
        qurl = "https://sqs.{region}.amazonaws.com/{account}/{resource}".format(**info)
        info['resource'] = qurl
        return SQSTransport(session_factory(), info)

    raise ValueError("unsupported transport %s" % stream_uri)


@click.group()
def cli():
    """Policy changes from git history"""


@cli.command(name='diff')
@click.option('-r', '--repo-uri')
@click.option('--source', default='master', help="source/baseline revision spec")
@click.option('--target', default=None, help="target revisiion spec")
@click.option('-o', '--output', type=click.File('wb'), default='-')
@click.option('-v', '--verbose', default=False, help="Verbose", is_flag=True)
def diff(repo_uri, source, target, output, verbose):
    logging.basicConfig(
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s",
        level=(verbose and logging.DEBUG or logging.INFO))
    logging.getLogger('botocore').setLevel(logging.WARNING)

    if repo_uri is None:
        repo_uri = pygit2.discover_repository(os.getcwd())

    repo = pygit2.Repository(repo_uri)
    load_resources()

    if target is None:
        target = repo.head.shorthand

    policy_repo = PolicyRepo(repo_uri, repo)
    changes = list(policy_repo.delta_commits(
        repo.revparse_single(source), repo.revparse_single(target)))
    output.write(
        yaml.safe_dump({
            'policies': [c.policy.data for c in changes
                         if c.kind != ChangeType.REMOVE]}).encode('utf8'))


@cli.command()
@click.option('-r', '--repo-uri')
@click.option('-s', '--stream-uri', default="stdout")
@click.option('-v', '--verbose', default=False, help="Verbose", is_flag=True)
@click.option('--assume')
def stream(repo_uri, stream_uri, verbose, assume):
    """Stream policy changes to destination"""
    logging.basicConfig(
        format="%(asctime)s: %(name)s:%(levelname)s %(message)s",
        level=(verbose and logging.DEBUG or logging.INFO))
    logging.getLogger('botocore').setLevel(logging.WARNING)

    with contextlib.closing(TempDir().open()) as temp_dir:
        if repo_uri is None:
            repo_uri = pygit2.discover_repository(os.getcwd())
            log.debug("Using repository %s", repo_uri)
        if repo_uri.startswith('http') or repo_uri.startswith('git@'):
            log.info("Cloning repository: %s", repo_uri)
            repo = pygit2.clone_repository(repo_uri, temp_dir.path)
        else:
            repo = pygit2.Repository(repo_uri)
        load_resources()
        policy_repo = PolicyRepo(repo_uri, repo)
        change_count = 0

        with contextlib.closing(transport(stream_uri, assume)) as t:
            for change in policy_repo.delta_stream():
                change_count += 1
                t.send(change)

        log.info("Streamed %d policy changes", change_count)


if __name__ == '__main__':
    try:
        cli()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        raise
    except: # NOQA
        import traceback, pdb, sys
        traceback.print_exc()
        pdb.post_mortem(sys.exc_info()[-1])
