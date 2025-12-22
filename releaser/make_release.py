#!/usr/bin/python
# Release script
# Licence: GPLv3
# Requires:
# * git with a Personal Access Token to access the Github repositories
# * a local git repository with a remote called 'upstream'
# * conda-build (to build conda packages)
# * conda-verify (to check built packages)
# * anaconda-client (to upload packages)
# * twine (to upload packages to pypi)
import sys
from datetime import date
from os import makedirs
from os.path import exists, join

from releaser.utils import (call, doechocall, yes, no, rmtree, branchname, short, git_remote_last_rev,
                            git_remote_url, release_changes, echocall, chdir, underline, replace_lines)

# ----- #
# steps #
# ----- #


def _anaconda_logged_user():
    whoami = echocall(["anaconda", "org", "whoami"])
    # returns either
    # """
    # Using Anaconda API: https://api.anaconda.org
    # Anonymous User
    # """
    # or
    # """
    # Using Anaconda API: https://api.anaconda.org
    # Username: gdementen
    # <other lines>
    # """
    lines = whoami.splitlines()
    assert len(lines) >= 2
    assert lines[0].startswith('Using')
    if lines[1].startswith('Username: '):
        username = lines[1][10:]
        return username
    else:
        assert lines[1].startswith('Anonymous')
        return ''


# TODO:
#  * create a specific environment to run the make_release script (which contains all step dependencies)
#  * create a requirements.txt or environment.yml with those dependencies so that we can recreate
#    the environment easily
def check_steps_requirements(step_funcs, **extra_kwargs):
    print("Checking releaser steps requirements")
    print("====================================")
    print()
    step_functions = [func for func, comment in step_funcs]
    must_stop = False
    if build_pypi_packages in step_functions:
        try:
            import build
            _ = build.ProjectBuilder
        except (ImportError, AttributeError) as e:
            print("Releaser will not be able to 'build_pypi_packages' because "
                  f"the 'build' package is not installed ({e}). Install it"
                  "with 'pip install build'")
            must_stop = True

    if upload_pypi_packages in step_functions:
        try:
            import twine
        except ImportError as e:
            print(f"Releaser will not be able to 'upload_pypi_packages' "
                  f"because the 'twine' package is not installed ({e})")
            must_stop = True

    if build_conda_packages in step_functions:
        has_binstar = False
        try:
            import binstar_client  # for anaconda_client
            has_binstar = True
            import conda_build
            import conda_verify
        except ImportError as e:
            print(f"""\
Releaser will not be able to 'build_conda_packages' because either at least one of 
the following packages is not installed (module name in parentheses):

  * anaconda-client (binstar_client)
  * conda-build (conda_build)
  * conda-verify (conda_verify)
  
Error: {e}""")
            must_stop = True

        if has_binstar and upload_conda_packages in step_functions:
            username = _anaconda_logged_user()
            if username:
                print(f"logged in anaconda as: {username}")
            else:
                print(f"""\
No user logged to anaconda. Please use 'anaconda org login' and using your 
anaconda.org username (NOT larray-project) before running
this script, otherwise it cannot upload packages to anaconda.""")
                must_stop = True
    if must_stop:
        sys.exit(1)
    else:
        print("OK (all requirements satisfied)")
        print()


def check_local_repo(local_repository, branch, release_name, **extra_kwargs):
    # TODO: I don't think this comment still applies (but it's still interesting to check
    #       local repo to avoid uncommitted/unpushed changes)
    # releasing from the local clone has the advantage we can prepare the
    # release offline and only push and upload it when we get back online
    print("\n", underline(f"Using repository at: {local_repository} !"), "\n", sep='')

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

    # fetch upstream
    doechocall('Fetching upstream changes', ['git', 'fetch', '--tags', 'upstream'])

    branch_exists_on_upstream = len(call(['git', 'ls-remote', '--heads', 'upstream', branch])) > 0
    if branch_exists_on_upstream:
        num_behind = int(call(['git', 'rev-list', f'{branch}..upstream/{branch}', '--count']))
        num_ahead = int(call(['git', 'rev-list', f'upstream/{branch}..{branch}', '--count']))
        print(f"Branch '{branch}' is {num_behind:d} commits behind and {num_ahead:d} commits ahead of "
              f"'upstream/{branch}'", end='')
    else:
        # we are ahead an indefinite number of commits
        num_behind = 0
        num_ahead = 1
        print(f"Branch '{branch}' does not exist on upstream", end='')

    if num_ahead and num_behind:
        print(", please merge or rebase before continuing!")
        exit(1)
    elif num_behind:
        if yes(', do you want to merge (fast-forward) the new changes?'):
            doechocall('Merging (fast-forward) changes', ['git', 'merge', '--ff-only', f'upstream/{branch}'])
    elif num_ahead:
        if yes(', do you want to push the changes (if they contain any *code* '
               'changes, you should make a PR instead so that CI can run on all'
               'Python versions)?', default='n'):
            git_push_cmd = ['git', 'push', 'upstream', branch]
            doechocall('Pushing changes', git_push_cmd)
        else:
            exit(1)
    else:
        print()

    if release_name == 'dev':
        rev = call(['git', 'log', '-1', '--format=%H'])
        # take first 7 digits of commit hash
        release_name = rev[:7]
    else:
        rev = git_remote_last_rev('upstream', branch=branch)

    if no(f"Release version {release_name} ({rev})?"):
        exit(1)

    upstream_repository = git_remote_url('upstream')
    return {'upstream_repository': upstream_repository, 'release_name': release_name, 'rev': rev}


def create_tmp_directory(tmp_dir, **extra_kwargs):
    if exists(tmp_dir):
        rmtree(tmp_dir)
    makedirs(tmp_dir)


def clone_repository(tmp_dir, branch, upstream_repository, **extra_kwargs):
    chdir(tmp_dir)

    # make a temporary clone in /tmp. The goal is to make sure we do not include extra/unversioned files. For the -src
    # archive, I don't think there is a risk given that we do it via git, but the risk is there for the bundles
    # (src/build is not always clean, examples, editor, ...)

    # Since this script updates files (update_changelog), we need to get those changes propagated to GitHub. I do that
    # by updating the temporary clone then push twice: first from the temporary clone to the "working copy clone" (eg
    # ~/devel/project) then to GitHub from there. The alternative to modify the "working copy clone" directly is worse
    # because it needs more complicated path handling that the 2 push approach.
    doechocall('Cloning repository', ['git', 'clone', '-b', branch, upstream_repository, 'build'])


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


def setup_repository_remotes(build_dir, upstream_repository=None, origin_repository=None,
                             **extra_kwargs):
    chdir(build_dir)

    # set upstream remote
    if upstream_repository is not None:
        doechocall(f'setting upstream to {upstream_repository}',
                   ['git', 'remote', 'add', 'upstream', upstream_repository])

    # set origin remote
    if origin_repository is not None:
        # assumes origin remote already exist
        doechocall(f'setting origin to {origin_repository}',
                   ['git', 'remote', 'set-url', 'origin', origin_repository])


def update_version(build_dir, release_name, package_name, module_name, public_release, **extra_kwargs):
    chdir(build_dir)

    version = short(release_name)

    # __init__.py
    init_file = join(module_name, '__init__.py')
    changes = [('__version__ =', f"__version__ = '{version}'")]
    replace_lines(init_file, changes)

    # pyproject.toml
    pyproject_file = 'pyproject.toml'
    # version = "0.35-dev"
    changes = [('version =', f'version = "{version}"')]
    replace_lines(pyproject_file, changes)

    changed_files = [init_file, pyproject_file]

    # meta.yaml
    if public_release and not release_name.endswith('-dev'):
        meta_file = join('condarecipe', package_name, 'meta.yaml')
        changes = [('{% set version', '{% set version = "' + version + '" %}'), ]
        replace_lines(meta_file, changes)
        changed_files.append(meta_file)

    # check and commit changes
    print(echocall(['git', 'status', '-s']))
    print(echocall(['git', 'diff', *changed_files]))
    if no('Do the version update changes look right?'):
        exit(1)
    doechocall('Adding', ['git', 'add', *changed_files])
    doechocall('Committing', ['git', 'commit', '-m', f'bump version to {version}'])
    print(echocall(['git', 'log', '-1']))


def create_source_archive(build_dir, package_name, release_name, rev, **extra_kwargs):
    chdir(build_dir)

    archive_name = f'..\\{package_name}-{release_name}-src.zip'
    echocall(['git', 'archive', '--format', 'zip', '--output', archive_name, rev])


def update_changelog(src_documentation, build_dir, public_release, release_name, **extra_kwargs):
    """
    Update release date in changes.rst
    """
    if src_documentation is None or not public_release:
        return

    chdir(build_dir)
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

    # display result
    with open(fpath, encoding='utf-8-sig') as f:
        lines = f.readlines()
    print()
    print('\n'.join(lines[:20]))
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


def build_pypi_packages(build_dir, public_release, **extra_kwargs):
    if not public_release:
        return

    chdir(build_dir)

    # By default, a source distribution (sdist) is built from {srcdir} and a
    # binary distribution (wheel) is built from the sdist
    print(echocall(['python', '-m', 'build', '.']))
    print(echocall(['twine', 'check', 'dist/*']))


def upload_test_pypi_packages(build_dir, public_release, **extra_kwargs):
    if not public_release:
        return

    chdir(build_dir)

    print("Enter your API token (there is no echo!):")
    print(echocall(['twine', 'upload',
                    '--repository-url', 'https://test.pypi.org/legacy/',
                    'dist/*']))


def upload_pypi_packages(build_dir, public_release, **extra_kwargs):
    if not public_release:
        return

    chdir(build_dir)

    print("Enter your API token (there is no echo!):")
    cmd = ['twine', 'upload', 'dist/*']
    msg = f"""Ready to push on production pypi? If so, command line 
    {' '.join(cmd)} 
will now be executed.
"""
    if no(msg):
        exit(1)
    print(echocall(cmd))


def pull_in_local_repo(local_repository, public_release, branch, **extra_kwargs):
    if not public_release:
        return

    # pull the generated commits and the release tag (which refers to the last commit)
    chdir(local_repository)
    doechocall(f'Pulling changes in {local_repository}',
               ['git', 'pull', '--ff-only', '--tags', '.', branch])


def push(build_dir, public_release, branch, **extra_kwargs):
    if not public_release:
        return

    chdir(build_dir)
    doechocall('Pushing main repository changes upstream',
               ['git', 'push', 'upstream', branch, '--follow-tags'])


def build_conda_packages(conda_recipe_path, build_dir, conda_build_args,
                         **extra_kwargs):
    if conda_recipe_path is None:
        return

    print()
    print('Building conda packages')
    print('=======================')
    chdir(build_dir)
    cmd = ['conda', 'build', '--no-anaconda-upload']
    if conda_build_args:
        # transform dict to flat list
        for arg_name, arg_value in conda_build_args.items():
            cmd += [arg_name, arg_value]
    cmd += [conda_recipe_path]
    echocall(cmd)


# workaround for https://github.com/conda/conda-build/issues/5823
def _cleanup_conda_build_output(fpath):
    lines = fpath.splitlines()
    return lines[-1]


def upload_conda_packages(conda_recipe_path, build_dir, anaconda_upload_args,
                          **extra_kwargs):
    if conda_recipe_path is None:
        return

    print()
    print('Uploading conda packages')
    print('========================')
    chdir(build_dir)
    # TODO: this will break if there are more than one package
    built_package_path = _cleanup_conda_build_output(
        echocall(['conda', 'build', '--output', conda_recipe_path])
    )
    print()
    print(f"{built_package_path=}")
    print()
    cmd = ['anaconda', 'org', 'upload']
    if anaconda_upload_args:
        # transform dict to flat list
        for arg_name, arg_value in anaconda_upload_args.items():
            cmd += [arg_name, arg_value]
    cmd += [built_package_path]
    echocall(cmd)


def cleanup(tmp_dir, **extra_kwargs):
    chdir(tmp_dir)
    rmtree('build')


# ------------ #
# end of steps #
# ------------ #

steps_funcs = [
    (check_steps_requirements, ''),
    (check_local_repo, ''),
    (create_tmp_directory, ''),
    (clone_repository, ''),
    (check_clone, ''),
    (setup_repository_remotes, ''),
    (update_version, ''),
    (update_changelog, 'Updating changelog'),
    # (create_source_archive, 'Creating source archive'),
    (build_pypi_packages, 'Building pypi packages'),
    (final_confirmation, ''),
    (tag_release, 'Tagging release'),
    (push, ''),
    (upload_test_pypi_packages, 'Uploading packages to test pypi'),
    (upload_pypi_packages, 'Uploading packages to pypi'),
    # we cannot build conda packages before tag_release+push because we use
    # the git tag
    (build_conda_packages, ''),
    (upload_conda_packages, 'Uploading conda packages'),
    # assume the tar archive for the new release exists
    (cleanup, 'Cleaning up'),
    (pull_in_local_repo, ''),
]


def insert_step_func(func, msg='', index=None, before=None, after=None):
    # TODO: do not use a global steps_funcs variable (but instead pass them to
    #       make_release)
    if sum((index is not None, before is not None, after is not None)) != 1:
        raise ValueError("You must choose between arguments 'index', 'before' and 'after'")
    func_names = [f.__name__ for f, desc in steps_funcs]
    if before is not None:
        index = func_names.index(before)
    elif after is not None:
        index = func_names.index(after) + 1
    steps_funcs.insert(index, (func, msg))


def run_steps(config, step_funcs):
    for step_func, step_desc in step_funcs:
        if step_desc:
            print(step_desc + '...', end=' ')

        config_update = step_func(**config)
        if config_update is not None:
            assert isinstance(config_update, dict)
            config.update(config_update)

        if step_desc:
            print("done.")


def set_config(step_funcs,
               local_repository, package_name, module_name, release_name,
               branch, src_documentation,
               tmp_dir=None,
               conda_build_args=None, anaconda_upload_args=None,
               conda_recipe_path=None,
               changelog_index_template=None, create_build_dir=True):
    if conda_build_args is not None and not isinstance(conda_build_args, dict):
        raise TypeError("'conda_build_args' argument must be None or a dict")

    public_release = release_name != 'dev'
    if public_release:
        if 'pre' in release_name:
            raise ValueError("'pre' is not supported anymore, use 'alpha' or 'beta' instead")
        if '-' in release_name:
            raise ValueError("- is not supported anymore")

    if tmp_dir is None:
        # TODO: use something more standard on Windows
        tmp_dir = join(r"c:\tmp" if sys.platform == "win32" else "/tmp",
                       f"{module_name}_release")

    # TODO: make this configurable
    if conda_recipe_path is None:
        conda_recipe_path = fr'condarecipe/{package_name}'
    config = {
        'step_funcs': step_funcs,
        'branch': branch,
        'release_name': release_name,
        'package_name': package_name,
        'module_name': module_name,
        'local_repository': local_repository,
        'src_documentation': src_documentation,
        'tmp_dir': tmp_dir,
        'build_dir': join(tmp_dir, 'build') if create_build_dir else local_repository,
        'conda_build_args': conda_build_args,
        'anaconda_upload_args': anaconda_upload_args,
        'conda_recipe_path': conda_recipe_path,
        'public_release': public_release,
        'changelog_index_template': changelog_index_template,
    }
    return config


def filter_step_funcs(step_funcs, steps_filter):
    func_names = [f.__name__ for f, desc in step_funcs]
    if ':' in steps_filter:
        start, stop = steps_filter.split(':')
        start = func_names.index(start) if start else 0
        # + 1 so that stop bound is inclusive
        stop = func_names.index(stop) + 1 if stop else len(func_names)
    else:
        # assuming a single step
        start = func_names.index(steps_filter)
        stop = start + 1
    return step_funcs[start:stop]


def make_release(local_repository, package_name, module_name, release_name='dev', steps_filter=':', branch='master',
                 src_documentation=None, tmp_dir=None, conda_build_args=None, anaconda_upload_args=None):
    # TODO: do not use the global variable (but pass step_funcs as argument
    #       instead)
    filtered_step_funcs = filter_step_funcs(steps_funcs, steps_filter)
    config = set_config(filtered_step_funcs,
                        local_repository, package_name, module_name,
                        release_name, branch, src_documentation,
                        tmp_dir=tmp_dir, conda_build_args=conda_build_args,
                        anaconda_upload_args=anaconda_upload_args)
    run_steps(config, filtered_step_funcs)
