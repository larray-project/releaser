#!/usr/bin/python
# encoding: utf-8
# script to start a new release cycle
# Licence: GPLv3
from os.path import join
from os import chdir
from shutil import copy

from releaser.utils import relname2fname, no, short, call
from releaser.make_release import create_tmp_directory, clone_repository, update_version, push


def update_changelog(config):
    if 'src_documentation' in config:
        chdir(config['build_dir'])
        release_name = config['release_name']
        src_documentation = config['src_documentation']

        fname = relname2fname(release_name)

        # create "empty" changelog for that release
        changes_dir = join(src_documentation, 'changes')
        copy(join(changes_dir, 'template.rst.inc'),
             join(changes_dir, fname))

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
        call(['git', 'add', fpath])


def add_release(package_name, release_name, branch='master'):
    assert '-dev' not in release_name
    config = get_config(package_name=package_name, release_name=release_name, branch=branch)
    create_tmp_directory(config)
    clone_repository(config)
    update_changelog(config)
    config['release_name'] = release_name+'-dev'
    update_version(config)
    push(config)


if __name__ == '__main__':
    from sys import argv

    add_release(*argv[1:])