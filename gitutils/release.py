#!/usr/bin/env python3

import re
import sys
from enum import IntEnum, auto
import subprocess

import git
import term

from rich import print
from rich.console import Console
from rich.style import Style

class ExitCodes(IntEnum):
    OK = 0
    NOTGITREPO = auto()
    DIRECTORYNAMEINVALID = auto()
    NOBRANCHESFOUND = auto()

def get_lowkey_text_color_style() -> str:
    colors: tuple[int, int, int] = term.getfgcolor()
    if term.islightmode():
        # lighten text colour
        newcolors = [int(c / 256 + 51) for c in colors]
    else:
        # darken text colour
        newcolors = [int(c / 256 - 51) for c in colors]
    
    newcolorsstr = ','.join([str(c) for c in newcolors])
    return f"rgb({newcolorsstr})"

def main():

    console = Console(highlight=False, file=sys.stderr)

    pat =  re.compile(r"^(?P<project>.*)-(?P<version>v\d\.\d\d(-[0-9.]+)?)$")

    # Get our git repo loaded
    repo = git.Repo(search_parent_directories=True)
    working_dir = str(repo.working_dir)

    # Check the name of the working directory against our regex
    if match := pat.match(working_dir):
        version = match.groupdict()['version']
    else:
        console.print(f"Working directory name '{working_dir}' does not appear to end in a valid version string")
        sys.exit(ExitCodes.DIRECTORYNAMEINVALID)

    # Get the list of branches that start with "release" and end with our version
    branches = [branch for branch in repo.branches if branch.name.startswith("release") and branch.name.endswith(version)]

    # Make sure we only got one
    if len(branches) == 0:
        console.print(f"No branches found matching `release.*{version}`")
        sys.exit(ExitCodes.NOBRANCHESFOUND)
    if len(branches) > 1:
        console.print(f"Too many branches found matching `release.*{version}`:")
        for branch in branches:
            console.print(f" * {branch.name}")
        sys.exit(ExitCodes.NOBRANCHESFOUND)

    branch = branches[0]

    lowkey = get_lowkey_text_color_style()

    # Check if we're already on that branch
    if repo.active_branch == branch:
        console.print(f"[{lowkey}]We already seem to be on branch [cyan]{branch.name}[/cyan], exiting")
        sys.exit(ExitCodes.OK)

    branch_name = branches[0].name

    console.print(f"[{lowkey}]Switching to branch {branch_name}")
    out = subprocess.check_call(["git","switch","--quiet", branch_name])

    if out != 0:
        console.print(f"Running `git switch` failed!")

if __name__ == '__main__':
    main()