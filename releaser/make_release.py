#!/usr/bin/python
# Release script
# Licence: GPLv3
# Requires:
# * git
import sys
from datetime import date
from os import makedirs
from os.path import exists, join
from subprocess import check_call

from releaser.utils import (call, doechocall, yes, no, rmtree, branchname, short,
                            git_remote_last_rev, replace_lines, release_changes, echocall, chdir)

# ----- #
# steps #
# ----- #


def check_local_repo(repository, branch, release_name, rev, **extra_kwargs):
    # releasing from the local clone has the advantage we can prepare the
    # release offline and only push and upload it when we get back online
    s = f"Using local repository at: {repository} !"
    print("\n", s, "\n", "=" * len(s), "\n", sep='')

    status = call(['git', 'status', '-s', '-b'])
    lines = status.splitlines()
    statusline, lines = lines[0], lines[1:]
    curbranch = branchname(statusline)
    if curbranch != branch:
        print(f"{branch} is not the current branch ({curbranch}). "
              f"Please use 'git checkout {branch}'.")
        exit(1)

    if lines:
        uncommited = sum(1 for line in lines if line[1] in 'MDAU')
        untracked = sum(1 for line in lines if line.startswith('??'))
        print(f'Warning: there are {uncommited:d} files with uncommitted changes and {untracked:d} untracked files:')
        print('\n'.join(lines))
        if no('Do you want to continue?'):
            exit(1)

    ahead = call(['git', 'log', '--format=format:%H', f'origin/{branch}..{branch}'])
    num_ahead = len(ahead.splitlines())
    print(f"Branch '{branch}' is {num_ahead:d} commits ahead of 'origin/{branch}'", end='')
    if num_ahead:
        if yes(', do you want to push?'):
            doechocall('Pushing changes', ['git', 'push'])
    else:
        print()

    if no(f"Release version {release_name} ({rev})?"):
        exit(1)


def create_tmp_directory(tmp_dir, **extra_kwargs):
    if exists(tmp_dir):
        rmtree(tmp_dir)
    makedirs(tmp_dir)


def clone_repository(tmp_dir, branch, repository, **extra_kwargs):
    chdir(tmp_dir)

    # make a temporary clone in /tmp. The goal is to make sure we do not include extra/unversioned files. For the -src
    # archive, I don't think there is a risk given that we do it via git, but the risk is there for the bundles
    # (src/build is not always clean, examples, editor, ...)

    # Since this script updates files (update_changelog), we need to get those changes propagated to GitHub. I do that
    # by updating the temporary clone then push twice: first from the temporary clone to the "working copy clone" (eg
    # ~/devel/project) then to GitHub from there. The alternative to modify the "working copy clone" directly is worse
    # because it needs more complicated path handling that the 2 push approach.
    doechocall('Cloning repository', ['git', 'clone', '-b', branch, repository, 'build'])


def check_clone(build_dir, public_release, src_documentation, release_name, **extra_kwargs):
    chdir(build_dir)

    # check last commit
    print()
    print(echocall(['git', 'log', '-1'], end='\n'))
    print()

    if no('Does that last commit look right?'):
        exit(1)

    if public_release:
        # check release changes
        print(release_changes(src_documentation, release_name, build_dir))
        if no('Does the release changelog look right?'):
            exit(1)


def create_source_archive(build_dir, package_name, release_name, rev, **extra_kwargs):
    chdir(build_dir)

    archive_name = f'..\\{package_name}-{release_name}-src.zip'
    echocall(['git', 'archive', '--format', 'zip', '--output', archive_name, rev])


def update_version(build_dir, release_name, package_name, module_name, **extra_kwargs):
    chdir(build_dir)

    version = short(release_name)
    # meta.yaml
    meta_file = join('condarecipe', package_name, 'meta.yaml')
    changes = [('version: ', f"  version: {version}"),
               ('git_tag: ', f"  git_tag: {version}")]
    replace_lines(meta_file, changes)

    # __init__.py
    init_file = join(module_name, '__init__.py')
    changes = [('__version__ =', f"__version__ = '{version}'")]
    replace_lines(init_file, changes)

    # setup.py
    setup_file = 'setup.py'
    changes = [('VERSION =', f"VERSION = '{version}'")]
    replace_lines(setup_file, changes)

    # check, commit and push
    print(echocall(['git', 'status', '-s']))
    print(echocall(['git', 'diff', meta_file, init_file, setup_file]))
    if no('Do the version update changes look right?'):
        exit(1)
    doechocall('Adding', ['git', 'add', meta_file, init_file, setup_file])
    doechocall('Committing', ['git', 'commit', '-m', f'bump version to {version}'])
    print(echocall(['git', 'log', '-1']))


def update_changelog(src_documentation, build_dir, public_release, release_name, **extra_kwargs):
    """
    Update release date in changes.rst
    """
    if src_documentation is not None:
        chdir(build_dir)

        if not public_release:
            return

        fpath = join(src_documentation, 'changes.rst')
        with open(fpath) as f:
            lines = f.readlines()
            expected_title = f"Version {short(release_name)}"
            title = lines[3]
            if title != expected_title + '\n':
                print(f'changes.rst not modified (the version title is "{title}" and instead of "{expected_title}")')
                return
            release_date = lines[6]
            if release_date != "In development.\n":
                print(f'changes.rst not modified (the version release date is "{release_date}" '
                      'instead of "In development.", was it already released?)')
                return
            lines[6] = f"Released on {date.today().isoformat()}.\n"
        with open(fpath, 'w') as f:
            f.writelines(lines)
        with open(fpath, encoding='utf-8-sig') as f:
            print()
            print('\n'.join(f.read().splitlines()[:20]))
        if no('Does the changelog look right?'):
            exit(1)
        echocall(['git', 'commit', '-m', f'update release date for {short(release_name)}', fpath])


def build_doc(build_dir, **extra_kwargs):
    chdir(build_dir)
    chdir('doc')
    if sys.platform == "win32":
        echocall('buildall.bat')
    else:
        echocall('buildall.sh')


def final_confirmation(public_release, **extra_kwargs):
    if not public_release:
        return

    msg = """Is the release looking good? If so, the tag will be created and pushed, everything will be uploaded to 
the production server. Stuff to watch out for:
* version numbers (executable & changelog)
* changelog
* doc on readthedocs
"""
    if no(msg):
        exit(1)


def tag_release(build_dir, public_release, release_name, **extra_kwargs):
    if not public_release:
        return

    chdir(build_dir)

    echocall(['git', 'tag', '-a', release_name, '-m', f'tag release {release_name}'])


def push_on_pypi(build_dir, public_release, **extra_kwargs):
    if not public_release:
        return

    chdir(build_dir)

    cmd = ['python', 'setup.py', 'clean', 'register', 'sdist', 'bdist_wheel', '--universal', 'upload', '-r', 'pypi']
    msg = f"""Ready to push on pypi? If so, command line 
    {' '.join(cmd)} 
will now be executed.
"""
    if no(msg):
        exit(1)
    echocall(cmd)


def pull(repository, public_release, build_dir, branch, **extra_kwargs):
    if not public_release:
        return

    # pull the changelog commits to the branch (usually master)
    # and the release tag (which refers to the last commit)
    chdir(repository)
    doechocall(f'Pulling changes in {repository}',
               ['git', 'pull', '--ff-only', '--tags', build_dir, branch])


def push(repository, public_release, branch, **extra_kwargs):
    if not public_release:
        return

    chdir(repository)
    doechocall('Pushing main repository changes to GitHub',
               ['git', 'push', 'upstream', branch, '--follow-tags'])


def build_conda_packages(conda_recipe_path, build_dir, conda_build_args, **extra_kwargs):
    if conda_recipe_path is None:
        return
    chdir(build_dir)
    print()
    print('Building conda packages')
    print('=======================')
    # XXX: split build & upload? (--no-anaconda-upload)
    cmd = ['conda', 'build']
    if conda_build_args:
        for arg_name, arg_value in conda_build_args.items():
            cmd += [arg_name, arg_value]
    cmd += [conda_recipe_path]
    print(' '.join(cmd))
    print(flush=True)
    check_call(cmd)


def cleanup(tmp_dir, **extra_kwargs):
    chdir(tmp_dir)
    rmtree('build')


# ------------ #
# end of steps #
# ------------ #

steps_funcs = [
    (check_local_repo, ''),
    (create_tmp_directory, ''),
    (clone_repository, ''),
    (check_clone, ''),
    (update_version, ''),
    (update_changelog, 'Updating changelog'),
    # (create_source_archive, 'Creating source archive'),
    (final_confirmation, ''),
    (tag_release, 'Tagging release'),
    # We used to push from /tmp to the local repository but you cannot push
    # to the currently checked out branch of a repository, so we need to
    # pull changes instead. However pull (or merge) add changes to the
    # current branch, hence we make sure at the beginning of the script
    # that the current git branch is the branch to release. It would be
    # possible to do so without a checkout by using:
    # git fetch {tmp_path} {branch}:{branch}
    # instead but then it only works for fast-forward and non-conflicting
    # changes. So if the working copy is dirty, you are out of luck.
    (pull, ''),
    # >>> need internet from here
    (push, ''),
    (push_on_pypi, 'Pushing on Pypi'),
    (build_conda_packages, ''),
    # assume the tar archive for the new release exists
    (cleanup, 'Cleaning up'),
]


def insert_step_func(func, msg='', index=None, before=None, after=None):
    if sum([index is not None, before is not None, after is not None]) != 1:
        raise ValueError("You must choose between arguments 'index', 'before' and 'after'")
    func_names = [f.__name__ for f, desc in steps_funcs]
    if before is not None:
        index = func_names.index(before)
    elif after is not None:
        index = func_names.index(after) + 1
    steps_funcs.insert(index, (func, msg))


def set_config(local_repository, package_name, module_name, release_name, branch, src_documentation, tmp_dir,
               conda_build_args):
    if conda_build_args is not None and not isinstance(conda_build_args, dict):
        raise TypeError("'conda_build_args' argument must be None or a dict")

    if release_name != 'dev':
        if 'pre' in release_name:
            raise ValueError("'pre' is not supported anymore, use 'alpha' or 'beta' instead")
        if '-' in release_name:
            raise ValueError("- is not supported anymore")

        # release_name = long_release_name(release_name)

    rev = git_remote_last_rev(local_repository, f'refs/heads/{branch}')
    public_release = release_name != 'dev'
    if not public_release:
        # take first 7 digits of commit hash
        release_name = rev[:7]

    if tmp_dir is None:
        tmp_dir = join(r"c:\tmp" if sys.platform == "win32" else "/tmp",
                       f"{module_name}_release")

    # TODO: make this configurable
    conda_recipe_path = fr'condarecipe/{package_name}'
    config = {
        'rev': rev,
        'branch': branch,
        'release_name': release_name,
        'package_name': package_name,
        'module_name': module_name,
        'repository': local_repository,
        'src_documentation': src_documentation,
        'tmp_dir': tmp_dir,
        'build_dir': join(tmp_dir, 'build'),
        'conda_build_args': conda_build_args,
        'conda_recipe_path': conda_recipe_path,
        'public_release': public_release,
    }
    return config


def run_steps(config, steps, steps_funcs):
    func_names = [f.__name__ for f, desc in steps_funcs]
    if ':' in steps:
        start, stop = steps.split(':')
        start = func_names.index(start) if start else 0
        # + 1 so that stop bound is inclusive
        stop = func_names.index(stop) + 1 if stop else len(func_names)
    else:
        # assuming a single step
        start = func_names.index(steps)
        stop = start + 1

    for step_func, step_desc in steps_funcs[start:stop]:
        if step_desc:
            print(step_desc + '...', end=' ')

        config_update = step_func(**config)
        if config_update is not None:
            assert isinstance(config_update, dict)
            config.update(config_update)

        if step_desc:
            print("done.")


def make_release(local_repository, package_name, module_name, release_name='dev', steps=':', branch='master',
                 src_documentation=None, tmp_dir=None, conda_build_args=None):
    config = set_config(local_repository, package_name, module_name, release_name, branch, src_documentation,
                        tmp_dir, conda_build_args)
    run_steps(config, steps, steps_funcs)
