#!/usr/bin/env python3

import re
import sys
import pathlib
import subprocess

from enum import IntEnum, auto

import git

from rich.console import Console

class ExitCodes(IntEnum):
    OK = 0
    NOTGITREPO = auto()
    DIRECTORYNAMEINVALID = auto()
    NOBRANCHESFOUND = auto()
    SWITCHBRANCHESFAILED = auto()

def main():

    console = Console(highlight=False, file=sys.stderr, style="dim")

    pat =  re.compile(r"^(?P<project>.*)-(?P<version>v\d\.\d\d(-[0-9.]+)?)$")

    # Get our git repo loaded
    repo = git.Repo(search_parent_directories=True)
    working_dir = pathlib.Path(repo.working_dir).name

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

    # Check if we're already on that branch
    if repo.active_branch == branch:
        console.print(f"We already seem to be on branch [cyan not dim]{branch.name}[/cyan not dim], exiting")
        sys.exit(ExitCodes.OK)

    branch_name = branches[0].name

    console.print(f"Switching to branch [cyan not dim]{branch_name}[/cyan not dim]")

    try:
        subprocess.check_output(["git","switch","--quiet", branch_name], stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:
        console.print("[not dim]Error while switching branch:")
        for line in exc.stderr.decode().splitlines():
            console.print(f"  [bright_red not dim]{line}[/bright_red not dim]")
        sys.exit(ExitCodes.SWITCHBRANCHESFAILED)

if __name__ == '__main__':
    main()