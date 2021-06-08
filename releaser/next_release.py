#!/usr/bin/python
# script to start a new release cycle
# Licence: GPLv3
from os.path import join
from shutil import copy

from releaser.utils import relname2fname, no, short, echocall, chdir
from releaser.make_release import update_version, set_config


DEFAULT_CHANGELOG_INDEX_TEMPLATE = """{title}
{underline}

In development.

.. include:: ./changes/{fname}


"""


def update_changelog(src_documentation, build_dir, release_name, changelog_index_template, **extra_kwargs):
    chdir(build_dir)

    fname = relname2fname(release_name)

    # create "empty" changelog for that release
    changes_dir = join(src_documentation, 'changes')
    changelog_file = join(changes_dir, fname)
    copy(join(changes_dir, 'template.rst.inc'), changelog_file)

    # include release changelog in changes.rst
    fpath = join(src_documentation, 'changes.rst')
    with open(fpath) as f:
        lines = f.readlines()
        title = f"Version {short(release_name)}"
        if lines[3] == title + '\n':
            print(f"changes.rst not modified (it already contains {title})")
            return
        this_version = changelog_index_template.format(title=title,
                                                       underline="=" * len(title),
                                                       fname= fname)
        lines[3:3] = this_version.splitlines(True)
    with open(fpath, 'w') as f:
        f.writelines(lines)
    with open(fpath, encoding='utf-8-sig') as f:
        print('\n'.join(f.read().splitlines()[:20]))
    if no('Does the full changelog look right?'):
        exit(1)
    echocall(['git', 'add', fpath, changelog_file])


def add_release(local_repository, package_name, module_name, release_name, branch='master', src_documentation=None,
                changelog_index_template=None):
    if changelog_index_template is None:
        changelog_index_template = DEFAULT_CHANGELOG_INDEX_TEMPLATE

    config = set_config(local_repository, package_name, module_name, release_name, branch, src_documentation,
                        changelog_index_template=changelog_index_template, create_build_dir=False)

    if src_documentation is not None:
        update_changelog(**config)

    config['release_name'] = release_name + '-dev'
    update_version(**config)
    # we should NOT push by default as next_release can be called when the working copy is on a branch (when we want to
    # add release notes for features which are not targeted for the current release)
