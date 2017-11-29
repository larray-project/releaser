#!/usr/bin/python
# coding=utf-8
# Release script
# Licence: GPLv3
# Requires:
# * git
from __future__ import print_function, unicode_literals

import sys
import hashlib
import urllib.request as request
from os.path import join

from releaser.utils import call, echocall, doechocall, no, replace_lines, chdir
from releaser.make_release import create_tmp_directory, clone_repository, cleanup, run_steps


# ----- #
# steps #
# ----- #

def update_version_conda_forge_package(config):
    chdir(config['build_dir'])

    # compute sha256 of archive of current release
    version = config['version']
    url = config['main_repository'] + '/archive/{version}.tar.gz'.format(version=version)
    print('Computing SHA256 from archive {url}'.format(url=url), end=' ')
    with request.urlopen(url) as response:
        sha256 = hashlib.sha256(response.read()).hexdigest()
        print('done.')
        print('SHA256: ', sha256)

    # set version and sha256 in meta.yml file
    meta_file = r'recipe\meta.yaml'
    changes = [('set version', '{{% set version = "{version}" %}}'.format(version=version)),
               ('set sha256', '{{% set sha256 = "{sha256}" %}}'.format(sha256=sha256))]
    replace_lines(meta_file, changes)

    # add, commit and push
    print(echocall(['git', 'status', '-s']))
    print(echocall(['git', 'diff', meta_file]))
    if no('Does that last changes look right?'):
        exit(1)
    doechocall('Adding', ['git', 'add', meta_file])
    doechocall('Commiting', ['git', 'commit', '-m', 'bump to version {version}'.format(version=version)])


def push_conda_forge(config):
    chdir(config['build_dir'])
    doechocall('Pushing changes to GitHub', ['git', 'push', 'origin', config['branch']])


# ------------ #
# end of steps #
# ------------ #

steps_funcs = [
    ########################################
    # UPDATE LARRAY PACKAGE ON CONDA-FORGE #
    ########################################
    (create_tmp_directory, ''),
    (clone_repository, ''),
    (update_version_conda_forge_package, ''),
    (push_conda_forge, ''),
    (cleanup, 'Cleaning up'),
]


def set_config_conda(main_repository, feedstock_repository, module_name, version, branch, tmp_dir):
    if tmp_dir is None:
        tmp_dir = join(r"c:\tmp" if sys.platform == "win32" else "/tmp", "{}_feedstock".format(module_name))

    config = {
        'module_name': module_name,
        'branch': branch,
        'version': version,
        'main_repository': main_repository,
        'repository': feedstock_repository,
        'tmp_dir': tmp_dir,
        'build_dir': join(tmp_dir, 'build'),
    }
    return config


def update_feedstock(main_repository, feedstock_repository, module_name, release_name, steps=':', branch='master',
                     tmp_dir=None):
    config = set_config_conda(main_repository, feedstock_repository, module_name, release_name, branch, tmp_dir)
    run_steps(config, steps, steps_funcs)
