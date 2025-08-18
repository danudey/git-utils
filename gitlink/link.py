#!/usr/bin/env python3

"""
A simple script to get links for branches, commits, or PRs
"""

import os
import re
import sys
import pickle
import logging
import pathlib
import argparse
import datetime
import functools

from types import SimpleNamespace

# third-party libraries

import xdg
import git
import git.refs
import git.repo.base
import yaml
import pydbus
import requests

from github import Github

from rich.console import Console
from rich.logging import RichHandler

try:
    from rich_argparse import RichHelpFormatter as HelpFormatter
except ImportError:
    from argparse import HelpFormatter

PROGNAME = "net.cdslash.git-link"
CACHE_DIR = xdg.xdg_cache_home().joinpath(PROGNAME)

FORMAT = "%(message)s"
logging.basicConfig(
    level="WARNING", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)

log = logging.getLogger("rich")
console = Console(highlight=False)
args = None

def link_url(url):
    """
    Take a URL and return a rich-ified link (reduces boilerplate)
    """
    return f"[link={url}]{url}[/link]"

def get_gh_token_from_dbus():
    """
    Fetch the Github token from SecretServer via dbus
    """
    bus = pydbus.SessionBus()
    secret_service = bus.get(".secrets")
    items, _ = secret_service.SearchItems([("username",""), ("service","gh:github.com")])
    _, secret_session = secret_service.OpenSession("plain", pydbus.Variant.new_string(""))

    secrets = secret_service.GetSecrets(items, secret_session)
    _, _, secret_raw, _ = secrets[items[0]]

    secret_bytes = bytes(secret_raw)
    token = secret_bytes.decode()
    return token


# Parse out github project paths. There are two formats:
#     'ssh': ssh://git@github.com/owner/project/
#     'raw': git@github.com:owner/project.git
#
# Note we're using Python's re.VERBOSE syntax. If you haven't seen it before:
#   https://docs.python.org/3/howto/regex.html#using-re-verbose

GITHUB_PROJECT_PAT = re.compile(
    r"""
    (:?ssh://)?                     # Match URLs with ssh schemes
    git@github.com[:/]              # Match either the ssh scheme's '/' or the raw scheme's ':'
    (?P<project_name>               # Get the project name (username/repository)
        (?P<github_username>[^/]+)  # Get just the username
        /                           # separator
        (?P<repo_name>[^/.]+)       # Get just the repository name
    )                               # (<project_name> ends)
    (.git|\/|)$                     # raw ends with .git; ssh ends with nothing,
                                    # a trailing slash, or .git
    """,
    re.VERBOSE,
)

GITHUB_BASE_URL = "https://github.com"

SEM_CONFIG_FILE_PATH = "~/.sem.yaml"


class LocalCache:
    """
    A dumb easy cache to dumbly, easily cache python objects locally
    """
    def __init__(self, path):
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)

    def old(self, key):
        """
        Returns true if an object is too old to use
        """
        cache_file = self.path.joinpath(key)
        mtime = cache_file.stat().st_mtime
        mdate = datetime.datetime.fromtimestamp(mtime)
        now = datetime.datetime.now()
        delta = now - mdate
        if delta.total_seconds() > 10800:
            return True
        return False

    def get(self, key):
        """
        Gets an object from the cache (unless it's too old)
        """
        try:
            cache_file = self.path.joinpath(key)
            if self.old(key):
                return None
            data = pickle.load(cache_file.open("rb"))
            return data
        except (FileNotFoundError, pickle.UnpicklingError):
            return None

    def put(self, key, data):
        """
        Puts an object into the cache, overwriting any existing object
        """
        pickle.dump(data, self.path.joinpath(key).open("wb"))


class Semaphore:
    """
    A simple, caching Semaphore interface
    """
    def __init__(self, token, hostname):
        self.cache = LocalCache(CACHE_DIR)
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Token {token}"})
        self.hostname = hostname
        self.__projects = {}

        self.__populate_caches()

    def __populate_caches(self):
        self.__projects = self.cache.get("projects")

    def __call_api_get(self, api_name, **kwargs):
        url = f"https://{self.hostname}/api/v1alpha/{api_name}"
        response = self.session.get(url, params=kwargs)
        return response.json()

    @property
    def projects(self):
        """
        Represents the projects that exist in Semaphore; cached if possible
        """
        if not self.__projects:
            projects_data = self.__call_api_get("projects")
            projects_map = {}
            for project in projects_data:
                project_name = project["metadata"]["name"]
                projects_map[project_name] = project
            self.__projects = projects_map
            self.cache.put("projects", projects_map)
        return self.__projects

    def project_link(self, project):
        """
        Returns the link to the project on Semaphore
        """
        return f"https://{self.hostname}/projects/{project}"

    pipelines = functools.partialmethod(__call_api_get, "pipelines")


try:
    # Get from environ if possible (in case we want to override)
    GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
except KeyError:
    try:
        # Otherwise, get it from `gh` command configuration
        yaml_file = (
            pathlib.Path("~/.config/gh/hosts.yml").expanduser().open(encoding="utf8")
        )
        yaml_doc = yaml.safe_load(yaml_file)
        GITHUB_TOKEN = yaml_doc["github.com"]["oauth_token"]
    except KeyError:
        # Maybe they moved the secret to the dbus secretserver?
        GITHUB_TOKEN = get_gh_token_from_dbus()
    except FileNotFoundError:
        log.error(
            "In order to use this command, you must either "
            "specify the GITHUB_TOKEN environment variable, "
            "or install and configure the `gh` tool from "
            "GitHub (recommended):\n"
            "    https://cli.github.com/manual/ "
        )
        sys.exit(1)

repo: git.repo.base.Repo = git.repo.base.Repo(search_parent_directories=True)
gh = Github(GITHUB_TOKEN)

try:
    yaml_file = pathlib.Path(SEM_CONFIG_FILE_PATH).expanduser().open(encoding="utf8")
    yaml_doc = yaml.safe_load(yaml_file)
    semaphore_active_context = yaml_doc["active-context"]
    semaphore_data = yaml_doc["contexts"][semaphore_active_context]
    semaphore_auth = SimpleNamespace(
        token=semaphore_data["auth"]["token"], host=semaphore_data["host"]
    )
    semaphore = Semaphore(semaphore_auth.token, hostname=semaphore_auth.host)
except FileNotFoundError:
    log.warning(
        "Semaphore command-line configuration was not found at %s. "
        "Semaphore-related commands will be unavailable.", SEM_CONFIG_FILE_PATH
    )
except KeyError:
    log.warning(
        "Semaphore configuration could not be read from the semaphore CLI configuration "
        "file at %s. Semaphore-related commands will be unavailable.", SEM_CONFIG_FILE_PATH
    )


def get_commit_remote_url(commit_or_ref=None):
    """
    Get the remote URL for a given commit (or the current one)
    """
    if commit_or_ref:
        commit_obj = repo.rev_parse(commit_or_ref)
    else:
        commit_obj = repo.active_branch.commit
    commit_hex = commit_obj.hexsha

    if 'upstream' in repo.remotes:
        remote = repo.remotes["upstream"]
    else:
        remote = repo.remotes["origin"]
    remote_url = next(remote.urls)

    if github_project_match := GITHUB_PROJECT_PAT.match(remote_url):
        project_name = github_project_match.group("project_name")
        github_url = f"{GITHUB_BASE_URL}/{project_name}/commit/{commit_hex}"
        console.print(link_url(github_url))
    else:
        raise ValueError("Not found")


def get_remote_ref_name(branch_name=None):
    """
    Get the name of the remote ref for a given branch
    """
    if branch_name is None:
        local_ref = repo.active_branch
    else:
        local_ref = repo.branches[branch_name]

    remote_branch = local_ref.tracking_branch()
    if remote_branch is None:
        remote_name = None
        # TODO: Either check all remotes for a matching branch, or get the first
        # remote specified, whatever it's called (it may not be 'origin')
        console.print(
            f"Local branch {local_ref} has no tracking branch, searching remotes",
        )
        for remote in repo.remotes:
            if local_ref.name in remote.refs:
                remote_name = remote.name
                console.print(f"Using detected remote {remote}")
        if remote_name is None:
            console.print(
                "Found no remotes with matching branches, using `origin` anyway.",
            )
            remote_name = "origin"
    else:
        remote_name = remote_branch.remote_name

    remote = repo.remote(remote_name)
    remote_url = next(remote.urls)

    if github_project_match := GITHUB_PROJECT_PAT.match(remote_url):
        project_name = github_project_match.group("project_name")
        github_username = github_project_match.group("github_username")

        return SimpleNamespace(
            project_name=project_name,
            github_username=github_username,
            local_ref=local_ref,
        )

    raise RuntimeError("Couldn't get it")

def get_file_remote_url(filepath=""):
    """
    Given a file path, get the URL to that file on the web
    """
    if filepath is None:
        filepath = ""
    lineno_param = None
    if not repo.working_dir:
        raise RuntimeError("Git repo has no working dir")
    # Get the current file path for the root of the git working directory (resolving symlinks, etc)
    git_root = pathlib.Path(repo.working_dir).resolve()
    # Get the current directory we're in (absolute path, resolving symlinks, etc.)
    cwd_path = pathlib.Path().resolve()

    # Take off the leading "/" if there is one; otherwise
    # we get an absolute path from Path.joinpath()
    filepath_rel = filepath.lstrip("/")

    # Maybe we got line numbers?
    if not os.path.isfile(filepath_rel):
        # Let's make the format <filepath>:##-## (which we'll pass to Github as L##-L##)
        try:
            test_filepath, test_lineno = filepath_rel.rsplit(":", 1)
            if os.path.isfile(test_filepath):
                filepath_rel = test_filepath
                if "-" in test_lineno:
                    start_lineno, end_lineno = test_lineno.split("-")
                    lineno_param = f"#L{start_lineno}-L{end_lineno}"
                else:
                    start_lineno, end_lineno = (test_lineno, None)
                    lineno_param = f"#L{start_lineno}"
        except ValueError:
            # Give up, let the rest of the logic handle it
            pass

    # Get the target path (assuming the path is relative
    # to our current directory, which is absolute)
    target_path = cwd_path.joinpath(pathlib.Path(filepath_rel))

    if not target_path.exists():
        console.print(f"Warning: specified path {target_path} does not exist locally")

    # Convert the absolute target_path to a relative path, relative to git_root
    target_file = target_path.relative_to(git_root)

    if target_path == git_root:
        target_file_name = ""
    else:
        target_file_name = target_file.as_posix()
    # Get the remote ref info (we're assuming a link to the current branch is desired)
    remote_info = get_remote_ref_name()

    if target_path.is_file():
        sub_path = "blob"
    else:
        sub_path = "tree"

    github_url = "/".join([
        GITHUB_BASE_URL,
        remote_info.project_name,
        sub_path,
        remote_info.local_ref.name,
        target_file_name
    ])

    if lineno_param:
        github_url = f"{github_url}{lineno_param}"

    console.print(link_url(github_url))


def get_pr_remote_url(branch_name=None, include_closed=False):
    """
    Get the remote URL for PRs using the specified (or current)
    branch as a HEAD
    """

    remote_info = get_remote_ref_name(branch_name)

    if include_closed:
        state = "all"
    else:
        state = "open"
    gh_project = gh.get_repo(remote_info.project_name)
    prs = gh_project.get_pulls(
        head=f"{remote_info.github_username}:{remote_info.local_ref.name}",
        state=state,
    )

    prs = list(prs)

    if not prs:
        console.print(
            f"No PRs found for {remote_info.github_username}:{remote_info.local_ref.name}"
        )
    else:
        for pull_request in prs:
            if pull_request.merged:
                closed = " [#8250DF](merged)[/#8250DF]"
                state_icon = "[#8250DF]\uf407[/#8250DF]"
            elif pull_request.state == "closed":
                closed = "[red] (closed)[/red]"
                state_icon = "[purple]\uf407[/purple]"
            else:
                closed = ""
                state_icon = "[green]\uf407[/green]"
            console.print(
                f"{state_icon} {pull_request.title}{closed}: {link_url(pull_request.html_url)}"
            )


def get_tree_remote_url(ref_name=None):
    """
    Get the remote URL for the specified (or current) branch/tag
    """

    # Figure out our local ref
    if ref_name is None:
        local_ref = repo.active_branch
    else:
        if ref_name in repo.tags:
            local_ref = repo.tags[ref_name]
        elif ref_name in repo.branches:
            local_ref = repo.branches[ref_name]
        else:
            raise RuntimeError("Couldn't find ref")
    # If our local ref is a branch, see if we have a tracking branch

    if isinstance(local_ref, git.refs.tag.TagReference):
        remote_name = repo.remotes[0].name
        remote_head = local_ref.name
    elif isinstance(local_ref, git.refs.head.Head):
        if tracking_branch := local_ref.tracking_branch():
            remote_head = tracking_branch.remote_head
            remote_name = tracking_branch.remote_name
        else:
            remote_head = local_ref.name
            remote_name = repo.remotes[0].name
    else:
        raise RuntimeError(f"Unknown type {type(local_ref)}")

    remote = repo.remote(remote_name)
    remote_url = next(remote.urls)

    if github_project_match := GITHUB_PROJECT_PAT.match(remote_url):
        project_name = github_project_match.group("project_name")
        github_url = f"{GITHUB_BASE_URL}/{project_name}/tree/{remote_head}"
        console.print(link_url(github_url))
        return
    raise RuntimeError("Couldn't find it")

def get_repo_remote_url():
    """
    Get the remote URL for the current repository
    """
    remote = repo.remotes[0]
    remote_url = next(remote.urls)

    if github_project_match := GITHUB_PROJECT_PAT.match(remote_url):
        project_name = github_project_match.group("project_name")
        github_url = f"{GITHUB_BASE_URL}/{project_name}"
        console.print(link_url(github_url))
    raise RuntimeError("Couldn't find it")


def get_semaphore_project_url(branch_name=None):
    """
    Gets the URL to the Semaphore project for the current directory
    """
    if branch_name is None:
        local_ref = repo.active_branch
    else:
        local_ref = repo.branches[branch_name]

    if tracking_branch := local_ref.tracking_branch():
        remote_name = tracking_branch.remote_name

        remote = repo.remote(remote_name)
        remote_url = next(remote.urls)

        for project_name, project_data in semaphore.projects.items():
            if project_data["spec"]["repository"]["url"] == remote_url:
                print(link_url(semaphore.project_link(project_name)))
    else:
        raise RuntimeError("Couldn't get tracking branch")


def main():
    parser = argparse.ArgumentParser(formatter_class=HelpFormatter)

    parser.add_argument("command", help="What to run (branch, pr, commit, file, or sem)")
    parser.add_argument(
        "--closed",
        action="store_true",
        help="When looking for PRs, also look for closed PRs",
    )
    parser.add_argument(
        "parameter", nargs="*", default=[None], help="The targets to search for links to"
    )

    args = parser.parse_args()

    match args.command:
        case "branch" | "tag" | "ref":
            for param in args.parameter:
                get_tree_remote_url(param)
        case "pr":
            for param in args.parameter:
                get_pr_remote_url(param, args.closed)
        case "commit":
            for param in args.parameter:
                get_commit_remote_url(param)
        case "file":
            for param in args.parameter:
                get_file_remote_url(param)
        case "sem":
            for param in args.parameter:
                get_semaphore_project_url(param)
        case "repo":
            get_repo_remote_url()
        case _:
            console.print(f"Unrecognized command: {args.command}")

if __name__ == '__main__':
    main()