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

from releaser.utils import (call, do, doechocall, yes, no, zip_unpack, rmtree, branchname, short, long_release_name,
                            git_remote_last_rev, replace_lines, release_changes, echocall, chdir)


# ------------------------- #
# specific helper functions #
# ------------------------- #

def create_source_archive(package_name, release_name, rev):
    archive_name = rf'..\{package_name}-{release_name}-src.zip'
    echocall(['git', 'archive', '--format', 'zip', '--output', archive_name, rev])


def copy_release(release_name):
    pass


def create_bundle_archives(release_name):
    pass


def check_bundle_archives(package_name, release_name):
    """
    checks the bundles unpack correctly
    """
    makedirs('test')
    zip_unpack(f'{package_name}-{release_name}-src.zip', r'test\src')
    rmtree('test')

# -------------------------------- #
# end of specific helper functions #
# -------------------------------- #


# ----- #
# steps #
# ----- #

def check_local_repo(config):
    # releasing from the local clone has the advantage we can prepare the
    # release offline and only push and upload it when we get back online
    repository = config['repository']
    branch = config['branch']
    s = f"Using local repository at: {repository} !"
    print("\n", s, "\n", "=" * len(s), "\n", sep='')

    status = call(['git', 'status', '-s', '-b'])
    lines = status.splitlines()
    statusline, lines = lines[0], lines[1:]
    curbranch = branchname(statusline)
    if curbranch != config['branch']:
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

    if no(f"Release version {config['release_name']} ({config['rev']})?"):
        exit(1)


def create_tmp_directory(config):
    tmp_dir = config['tmp_dir']
    if exists(tmp_dir):
        rmtree(tmp_dir)
    makedirs(tmp_dir)


def clone_repository(config):
    chdir(config['tmp_dir'])

    # make a temporary clone in /tmp. The goal is to make sure we do not include extra/unversioned files. For the -src
    # archive, I don't think there is a risk given that we do it via git, but the risk is there for the bundles
    # (src/build is not always clean, examples, editor, ...)

    # Since this script updates files (update_changelog), we need to get those changes propagated to GitHub. I do that
    # by updating the temporary clone then push twice: first from the temporary clone to the "working copy clone" (eg
    # ~/devel/project) then to GitHub from there. The alternative to modify the "working copy clone" directly is worse
    # because it needs more complicated path handling that the 2 push approach.
    doechocall('Cloning repository', ['git', 'clone', '-b', config['branch'], config['repository'], 'build'])


def check_clone(config):
    chdir(config['build_dir'])

    # check last commit
    print()
    print(echocall(['git', 'log', '-1'], end='\n'))
    print()

    if no('Does that last commit look right?'):
        exit(1)

    if config['public_release']:
        # check release changes
        print(release_changes(config))
        if no('Does the release changelog look right?'):
            exit(1)


def build_exe(config):
    pass


def test_executables(config):
    pass


def create_archives(config):
    chdir(config['build_dir'])

    release_name = config['release_name']
    create_source_archive(config['package_name'], release_name, config['rev'])

    chdir(config['tmp_dir'])

    # copy_release(release_name)
    # create_bundle_archives(release_name)
    # check_bundle_archives(release_name)


def run_tests():
    """
    assumes to be in build
    """
    echocall('pytest')


def update_version(config):
    chdir(config['build_dir'])

    version = short(config['release_name'])
    package_name = config['package_name']
    src_code = config['module_name']

    # meta.yaml
    meta_file = join('condarecipe', package_name, 'meta.yaml')
    changes = [('version: ', f"  version: {version}"),
               ('git_tag: ', f"  git_tag: {version}")]
    replace_lines(meta_file, changes)

    # __init__.py
    init_file = join(src_code, '__init__.py')
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


def update_changelog(config):
    """
    Update release date in changes.rst
    """
    if config['src_documentation'] is not None:
        chdir(config['build_dir'])

        if not config['public_release']:
            return

        release_name = config['release_name']
        fpath = join(config['src_documentation'], 'changes.rst')
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


def build_doc(config):
    chdir(config['build_dir'])
    chdir('doc')
    if sys.platform == "win32":
        echocall('buildall.bat')
    else:
        echocall('buildall.sh')


def final_confirmation(config):
    if not config['public_release']:
        return

    msg = """Is the release looking good? If so, the tag will be created and pushed, everything will be uploaded to 
the production server. Stuff to watch out for:
* version numbers (executable & changelog)
* changelog
* doc on readthedocs
"""
    if no(msg):
        exit(1)


def tag_release(config):
    chdir(config['build_dir'])

    if not config['public_release']:
        return

    release_name = config['release_name']
    echocall(['git', 'tag', '-a', release_name, '-m', f'tag release {release_name}'])


def push_on_pypi(config):
    chdir(config['build_dir'])

    if not config['public_release']:
        return

    cmd = ['python', 'setup.py', 'clean', 'register', 'sdist', 'bdist_wheel', '--universal', 'upload', '-r', 'pypi']
    msg = f"""Ready to push on pypi? If so, command line 
    {' '.join(cmd)} 
will now be executed.
"""
    if no(msg):
        exit(1)
    echocall(cmd)


def pull(config):
    if not config['public_release']:
        return

    # pull the changelog commits to the branch (usually master)
    # and the release tag (which refers to the last commit)
    repository = config['repository']
    chdir(repository)
    doechocall(f'Pulling changes in {repository}',
               ['git', 'pull', '--ff-only', '--tags', config['build_dir'], config['branch']])


def push(config):
    if not config['public_release']:
        return

    chdir(config['repository'])
    doechocall('Pushing main repository changes to GitHub',
               ['git', 'push', 'upstream', config['branch'], '--follow-tags'])


def build_conda_packages(config):
    if config['conda_recipe_path'] is None:
        return
    chdir(config['build_dir'])
    print()
    print('Building conda packages')
    print('=======================')
    # XXX: split build & upload? (--no-anaconda-upload)
    cmd = ['conda', 'build']
    if config['conda_build_args']:
        for arg_name, arg_value in config['conda_build_args'].items():
            cmd += [arg_name, arg_value]
    cmd += [config['conda_recipe_path']]
    print(' '.join(cmd))
    print()
    sys.stdout.flush()
    check_call(cmd)


def cleanup(config):
    chdir(config['tmp_dir'])
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
    (build_exe, 'Building executables'),
    (test_executables, 'Testing executables'),
    (update_changelog, 'Updating changelog'),
    (create_archives, 'Creating archives'),
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
            do(step_desc, step_func, config)
        else:
            step_func(config)


def make_release(local_repository, package_name, module_name, release_name='dev', steps=':', branch='master',
                 src_documentation=None, tmp_dir=None, conda_build_args=None):
    config = set_config(local_repository, package_name, module_name, release_name, branch, src_documentation,
                        tmp_dir, conda_build_args)
    run_steps(config, steps, steps_funcs)
