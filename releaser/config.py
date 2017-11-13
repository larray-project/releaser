#!/usr/bin/python
# coding=utf-8
from __future__ import print_function, unicode_literals

import sys
from os.path import join
from releaser.utils import git_remote_last_rev

TMP_DIR = r"c:\tmp" if sys.platform == "win32" else "/tmp"

LARRAY_CONFIG = {'github_user': 'liam2',
                 'module_name': 'larray',
                 'src_documentation': join('doc', 'source'),
                 'announce_group': 'larray-announce@googlegroups.com',
                 'users_group': 'larray-users@googlegroups.com',
                 'online_doc': 'http://larray.readthedocs.io/en/stable/',
                 }

EDITOR_CONFIG = {'github_user': 'larray-project',
                 'module_name': 'larray_editor',
                 }

EUROSTAT_CONFIG = {'github_user': 'larray-project',
                   'module_name': 'larray_eurostat',
                   }

LIAM2_CONFIG = {'github_user': 'liam2',
                'module_name': 'liam2',
                'src_documentation': join('doc', 'usersguide', 'source'),
                'online_doc': 'http://liam2.plan.be',
                'announce_group': 'liam2-announce@googlegroups.com',
                'users_group': 'liam2-users@googlegroups.com',
                }

CONFIG = {'larray': LARRAY_CONFIG, 'larray-editor': EDITOR_CONFIG, 'larray-eurostat': EUROSTAT_CONFIG,
          'liam2': LIAM2_CONFIG}


def get_config(package_name, release_name, branch):
    config = CONFIG[package_name].copy()

    repository = "https://github.com/{}/{}".format(config['github_user'], package_name)
    rev = git_remote_last_rev(repository, 'refs/heads/{}'.format(branch))
    public_release = release_name != 'dev'
    if not public_release:
        # take first 7 digits of commit hash
        config['release_name'] = rev[:7]

    config.update({'rev': rev,
                   'repository': repository,
                   'tmp_dir': join(TMP_DIR, "{}_new_release".format(package_name)),
                   'build_dir': join(TMP_DIR, "{}_new_release".format(package_name), 'build'),
                   'public_release': public_release
                   })
    return config


def update_config_for_conda(config):
    package_name = config['package_name']
    github_user = config['github_user']
    config['tmp_dir'] = join(TMP_DIR, "conda_{}_new_release".format(package_name))
    config['build_dir'] = join(config['tmp_dir'], 'build')
    config['repository'] = "https://github.com/{}/{}-feedstock.git".format(github_user, package_name)
    return config
