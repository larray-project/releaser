#!/usr/bin/python
# encoding: utf-8
# script to start a new release cycle
# Licence: GPLv3
from os.path import join
from shutil import copy

from releaser.utils import relname2fname, no, short, echocall, chdir
from releaser.make_release import update_version, push


def update_changelog(config):
    if config['src_documentation'] is not None:
        chdir(config['build_dir'])
        release_name = config['release_name']
        src_documentation = config['src_documentation']

        fname = relname2fname(release_name)

        # create "empty" changelog for that release
        changes_dir = join(src_documentation, 'changes')
        changelog_file = join(changes_dir, fname)
        copy(join(changes_dir, 'template.rst.inc'), changelog_file)

        # include release changelog in changes.rst
        fpath = join(src_documentation, 'changes.rst')
        changelog_index_template = """{title}
{underline}

In development.

.. include:: {fpath}


"""

        with open(fpath) as f:
            lines = f.readlines()
            title = "Version {}".format(short(release_name))
            if lines[3] == title + '\n':
                print("changes.rst not modified (it already contains {})".format(title))
                return
            this_version = changelog_index_template.format(title=title,
                                                           underline="=" * len(title),
                                                           fpath='./changes/' + fname)
            lines[3:3] = this_version.splitlines(True)
        with open(fpath, 'w') as f:
            f.writelines(lines)
        with open(fpath, encoding='utf-8-sig') as f:
            print('\n'.join(f.read().splitlines()[:20]))
        if no('Does the full changelog look right?'):
            exit(1)
        echocall(['git', 'add', fpath, changelog_file])


def add_release(local_repository, package_name, module_name, release_name, branch='master', src_documentation=None):
    config = {
        'branch': branch,
        'release_name': release_name,
        'package_name': package_name,
        'module_name': module_name,
        'repository': local_repository,
        'build_dir': local_repository,
        'src_documentation': src_documentation,
        'public_release': True
    }
    update_changelog(config)
    config['release_name'] += '-dev'
    update_version(config)
    push(config)
