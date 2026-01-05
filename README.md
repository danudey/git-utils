# Random git utils

Some commands I wrote.

## Installation

You should install using a tool that handles Python venv installations for you so as not to overwrite existing packages.

### `uv` (recommended)

If you have `uv` [installed](https://docs.astral.sh/uv/#installation):

```
uv tool install git+https://github.com/danudey/git-utils.git
```

### `pipx`

If you don't have `uv`, there's a decent chance that `pipx` is installed, or can be installed, via your system's package manager; otherwise, you could [install it yourself](https://github.com/pypa/pipx#install-pipx). If so:

```
pipx install git+https://github.com/danudey/git-utils.git
```

### `pip`

Probably not a good idea. Almost definitely not a good idea.

```
pip install git+https://github.com/danudey/git-utils.git
```

## The commands

### `git link`

Just prints out a link to whatever you tell it to on Github. Links are cllickable/Ctrl-clickable in your terminal if it supports clickable links (most do). Examples:

* `git link repo` - prints a link to the remote repository
* `git link sem` - links to the repository in semaphore (assuming your current semaphore context is set correctly)
* `git link pr` - prints a link to the PR for the current branch (assuming you're on a PR's branch)
* `git link commit` - prints a link to the commit for current `HEAD`, or, if you specify a ref, the commit for that ref (not the ref itself, but the commit it points to)
* `git link branch` - prints a link to the current branch, or any branch or tag you specify
* `git link file` - prints a link to the file specified; if you don't specify one it links you to the file list for the directory you're in.

Two variations to file links: it can link to a specific line in a file, e.g. Makefile:12, or a range of lines in a file, e.g. Makefile:12-24.

### `git release-branch`

Changes you to the release branch for the current directory, assuming that you're in a directory named `<anything>-vX.YY` and that the associated release branch is named `release.*-vX.YY` (i.e. starts with release and ends with the version from the directory name)

## The caveats

Both of these tools do their best to do the right thing, which is not always easy, obvious, or possible. Lots of 'detection' (guesswork) happens, so there's a chance things will break if your setup isn't very similar to mine (Ubuntu Linux, using Semaphore and Github).

One example is that, if necessary, `git link     tries to look for a saved Github token in your system's secret store (e.g. your 'system keychain') via dbus, but this only works on Linux (or other systems using dbus? FreeBSD?) and may not work on anyone else's Linux system. At some point, fetching from the MacOS keychain would be a good thing to add.