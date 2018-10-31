import json
import logging
import os
import sys
import subprocess
import hashlib
import re
from builtins import bytes

logger = logging.getLogger('c7n_azure.dependency_manager')


class DependencyManager(object):

    @staticmethod
    def _run(cmd, verbose=False, **kwargs):
        if verbose:
            stdout = stderr = None
        else:
            stdout = stderr = subprocess.PIPE

        logger.debug(' '.join(cmd))
        return subprocess.run(cmd, stdout=stdout, stderr=stderr, **kwargs)

    @staticmethod
    def get_dependency_packages_list(packages, excluded_packages):
        try:
            from pip._internal.utils.misc import get_installed_distributions
        except ImportError:
            from pip import get_installed_distributions

        dists = get_installed_distributions()
        res = []
        for p in packages:
            res.extend([str(r) for r in next(d.requires() for d in dists if (p + ' ') in str(d))])

        res = [t for t in res if not any((e in t) for e in excluded_packages)]
        return res

    @staticmethod
    def prepare_non_binary_wheels(packages, folder):
        cmd = ['pip', 'wheel', '-w', folder, '--no-binary=:all:']
        cmd.extend(packages)
        pip = DependencyManager._run(cmd)

        if pip.returncode != 0:
            logger.error('Failed to download wheels!')
            sys.exit(1)

        package_names = [re.findall('[^<>=~]+', p)[0] for p in packages]
        for p in package_names:
            filename = next(f for f in os.listdir(folder) if p.lower() in f.lower())
            newname = '-'.join(filename.split('-')[:2] + ['cp36-cp36m-manylinux1_x86_64.whl'])
            os.rename(os.path.join(folder, filename),
                      os.path.join(folder, newname))

    @staticmethod
    def download_wheels(packages, folder):

        if not os.path.exists(folder):
            os.makedirs(folder)

        cmd = ['pip', 'download', '--dest', folder, '--find-links', folder]
        cmd.extend(packages)
        cmd.extend(['--platform=manylinux1_x86_64',
                    '--python-version=36',
                    '--implementation=cp',
                    '--abi=cp36m',
                    '--only-binary=:all:'])
        pip = DependencyManager._run(cmd)

        if pip.returncode != 0:
            logger.error('Failed to download wheels!')
            sys.exit(1)

    @staticmethod
    def install_wheels(wheels_folder, install_folder):
        logging.getLogger('distlib').setLevel(logging.ERROR)
        if not os.path.exists(install_folder):
            os.makedirs(install_folder)

        from distlib.wheel import Wheel
        from distlib.scripts import ScriptMaker

        paths = {
            'prefix': '',
            'purelib': install_folder,
            'platlib': install_folder,
            'scripts': '',
            'headers': '',
            'data': ''}
        files = os.listdir(wheels_folder)
        for f in [os.path.join(wheels_folder, f) for f in files]:
            wheel = Wheel(f)
            wheel.install(paths, ScriptMaker(None, None), lib_only=True)

    @staticmethod
    def _get_dir_hash(directory):
        hash = hashlib.md5()

        for root, _, files in os.walk(directory):
            for names in files:
                filepath = os.path.join(root, names)
                with open(filepath, 'rb') as f:
                    buf = f.read(65536)
                    if not buf:
                        break
                    hash.update(buf)
        return hash.hexdigest()

    @staticmethod
    def _get_string_hash(string):
        return hashlib.md5(bytes(string, 'utf-8')).hexdigest()

    @staticmethod
    def check_cache(cache_folder, install_folder, packages):
        metadata_file = os.path.join(cache_folder, 'metadata.json')

        if not os.path.exists(metadata_file):
            return False

        if not os.path.exists(install_folder):
            return False

        with open(metadata_file, 'rt') as f:
            try:
                data = json.load(f)
            except Exception:
                return False

        if DependencyManager._get_string_hash(' '.join(packages)) != data.get('packages_hash'):
            return False

        if DependencyManager._get_dir_hash(install_folder) != data.get('install_hash'):
            return False
        return True

    @staticmethod
    def create_cache_metadata(cache_folder, install_folder, packages):
        metadata_file = os.path.join(cache_folder, 'metadata.json')
        with open(metadata_file, 'wt+') as f:
            json.dump({'packages_hash': DependencyManager._get_string_hash(' '.join(packages)),
                       'install_hash': DependencyManager._get_dir_hash(install_folder)}, f)
