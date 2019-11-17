import sys
import errno
import fnmatch
import os
import re
import stat
import zipfile
from os.path import join
from shutil import rmtree as _rmtree
from subprocess import check_output, STDOUT, CalledProcessError


# ------------- #
# generic tools #
# ------------- #

def size2str(value):
    unit = "bytes"
    if value > 1024.0:
        value /= 1024.0
        unit = "Kb"
        if value > 1024.0:
            value /= 1024.0
            unit = "Mb"
        return f"{value:.2f} {unit}"
    else:
        return f"{value:d} {unit}"


def generate(fname, **kwargs):
    with open(f'{fname}.tmpl') as in_f, open(fname, 'w') as out_f:
        out_f.write(in_f.read().format(**kwargs))


def _remove_readonly(function, path, excinfo):
    if function in {os.rmdir, os.remove, os.unlink} and excinfo[1].errno == errno.EACCES:
        # add write permission to owner
        os.chmod(path, stat.S_IWUSR)
        # retry removing
        function(path)
    else:
        raise Exception(f"Cannot remove {path}")


def rmtree(path):
    _rmtree(path, onerror=_remove_readonly)


def chdir(path):
    print("cd", path)
    os.chdir(path)


def force_decode(s):
    if isinstance(s, str):
        return s
    assert isinstance(s, bytes)
    encodings = ['utf8', 'cp1252']
    for encoding in encodings:
        try:
            return s.decode(encoding)
        except UnicodeDecodeError:
            pass
    return s.decode('ascii', 'replace')


def call(*args, **kwargs):
    assert len(args) == 1 and isinstance(args[0], list)
    try:
        res = check_output(*args, stderr=STDOUT, **kwargs)
        if 'universal_newlines' not in kwargs:
            return force_decode(res)
        else:
            return res
    except CalledProcessError as e:
        print(f"""

call failed
===========
{' '.join(args[0])}

output
======
{force_decode(e.output)}""")
        raise e
    except FileNotFoundError as e:
        print(f"""

call failed
===========
{' '.join(args[0])}""")
        raise e


def echocall(*args, **kwargs):
    assert len(args) == 1 and isinstance(args[0], list)
    end = kwargs.pop('end', '\n')
    print(' '.join(args[0]), end=end)
    sys.stdout.flush()
    return call(*args, **kwargs)


def branchname(statusline):
    """
    computes the branch name from a "git status -b -s" line
    ## master...origin/master
    """
    statusline = statusline.replace('#', '').strip()
    pos = statusline.find('...')
    return statusline[:pos] if pos != -1 else statusline


def yes(msg, default='y'):
    y = "Y" if default == "y" else "y"
    n = "N" if default == "n" else "n"
    choices = f' ({y}/{n}) '
    answer = None
    while answer not in ('', 'y', 'n'):
        if answer is not None:
            print("answer should be 'y', 'n', or <return>")
        answer = input(msg + choices).lower()
    return (default if answer == '' else answer) == 'y'


def no(msg, default='n'):
    return not yes(msg, default)


def doechocall(description, *args, **kwargs):
    print(description + '... "', end='')
    kwargs['end'] = '" '
    echocall(*args, **kwargs)
    print('done.')


def do(description, func, *args, **kwargs):
    print(description + '...', end=' ')
    func(*args, **kwargs)
    print("done.")


def allfiles(pattern, path='.'):
    """
    like glob.glob(pattern) but also include files in subdirectories
    """
    return (os.path.join(dirpath, f)
            for dirpath, dirnames, files in os.walk(path)
            for f in fnmatch.filter(files, pattern))


def zip_pack(archivefname, filepattern):
    with zipfile.ZipFile(archivefname, 'w', zipfile.ZIP_DEFLATED) as f:
        for fname in allfiles(filepattern):
            f.write(fname)


def zip_unpack(archivefname, dest=None):
    with zipfile.ZipFile(archivefname) as f:
        f.extractall(dest)


def short(rel_name):
    return rel_name[:-2] if rel_name.endswith('.0') else rel_name


def long_release_name(release_name):
    """
    transforms a short release name such as 0.8 to a long one such as 0.8.0
    >>> long_release_name('0.8')
    '0.8.0'
    >>> long_release_name('0.8.0')
    '0.8.0'
    >>> long_release_name('0.8rc1')
    '0.8.0rc1'
    >>> long_release_name('0.8.0rc1')
    '0.8.0rc1'
    """
    dotcount = release_name.count('.')
    if dotcount >= 2:
        return release_name
    assert dotcount == 1, f"{release_name} contains {dotcount} dots"
    pos = pretag_pos(release_name)
    if pos is not None:
        return release_name[:pos] + '.0' + release_name[pos:]
    return release_name + '.0'


def pretag_pos(release_name):
    """
    gives the position of any pre-release tag
    >>> pretag_pos('0.8')
    >>> pretag_pos('0.8alpha25')
    3
    >>> pretag_pos('0.8.1rc1')
    5
    """
    # 'a' needs to be searched for after 'beta'
    for tag in ('rc', 'c', 'beta', 'b', 'alpha', 'a'):
        match = re.search(tag + r'\d+', release_name)
        if match is not None:
            return match.start()
    return None


def strip_pretags(release_name):
    """
    removes pre-release tags from a version string
    >>> strip_pretags('0.8')
    '0.8'
    >>> strip_pretags('0.8alpha25')
    '0.8'
    >>> strip_pretags('0.8.1rc1')
    '0.8.1'
    """
    pos = pretag_pos(release_name)
    return release_name[:pos] if pos is not None else release_name


def isprerelease(release_name):
    """
    tests whether the release name contains any pre-release tag
    >>> isprerelease('0.8')
    False
    >>> isprerelease('0.8alpha25')
    True
    >>> isprerelease('0.8.1rc1')
    True
    """
    return pretag_pos(release_name) is not None


# -------------------- #
# end of generic tools #
# -------------------- #

# ---------------- #
# helper functions #
# ---------------- #


def relname2fname(release_name):
    short_version = short(strip_pretags(release_name))
    return fr"version_{short_version.replace('.', '_')}.rst.inc"


def release_changes(config):
    if config['src_documentation'] is not None:
        directory = join(config['src_documentation'], "changes")
        fname = relname2fname(config['release_name'])
        with open(os.path.join(config['build_dir'], directory, fname), encoding='utf-8-sig') as f:
            return f.read()


def replace_lines(fpath, changes, end="\n"):
    """
    Parameters
    ----------
    changes : list of pairs
        List of pairs (substring_to_find, new_line).
    """
    with open(fpath) as f:
        lines = f.readlines()
        for i, line in enumerate(lines[:]):
            for substring_to_find, new_line in changes:
                if substring_to_find in line and not line.strip().startswith('#'):
                    lines[i] = new_line + end
    with open(fpath, 'w') as f:
        f.writelines(lines)


def git_remote_last_rev(url, branch=None):
    """
    :param url: url of the remote repository
    :param branch: an optional branch (defaults to 'refs/heads/master')
    :return: name/hash of the last revision
    """
    if branch is None:
        branch = 'refs/heads/master'
    output = call(['git', 'ls-remote', url, branch])
    for line in output.splitlines():
        if line.endswith(branch):
            return line.split()[0]
    raise Exception("Could not determine revision number")


# ----------------------- #
# end of helper functions #
# ----------------------- #
