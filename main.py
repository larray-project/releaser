#!/usr/bin/python
# coding=utf-8
from __future__ import print_function, unicode_literals
import sys
from releaser.next_release import add_release
from releaser.make_release import make_release, steps_funcs

if __name__ == '__main__':
    argv = sys.argv
    if len(argv) < 3:
        print("Usage: {} package_name release_name|dev [next|step|startstep:stopstep] [branch]".format(argv[0]))
        print("steps:", ', '.join(f.__name__ for f, _ in steps_funcs))
        sys.exit()

    if argv[3] == 'next':
        del argv[3]
        add_release(*argv[1:])
    else:
        make_release(*argv[1:])
