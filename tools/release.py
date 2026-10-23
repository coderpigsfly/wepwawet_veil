#!/usr/bin/env python3
# tools/release.py - the only way anything reaches the public repo. The same file in every repo;
# each repo's own release.yaml says what's published.
#
#   python3 tools/release.py           build the public copy, show what goes out, ask, publish
#   python3 tools/release.py --check   build and show only; nothing is published
#
# What it does:
#   1. Takes what's committed here (refuses while tracked files have changes not committed).
#   2. Builds the public copy: every tracked file, minus release.yaml's never: list (unless its
#      keep: list names it, like an empty folder's .keep), minus every
#      household file that has a skeleton (its skeleton ships in the skeletons folder instead and
#      is put in place on a new install's first start). Those places, and release.yaml's
#      public_ignore:, are added to the public .gitignore.
#   3. Shows what's left out, and what's added, changed and removed since the last release.
#   4. On your "yes": one commit in the public repo, tagged v<version>, pushed; and the
#      development commit it came from tagged release-v<version>, pushed here.
# The public repo's history is releases only: nothing before the first release ever goes there.

import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tempfile

import yaml

REPO = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                      check=True).stdout.strip()


def git(*args, cwd=REPO, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout.strip()


def load():
    path = os.path.join(REPO, "release.yaml")
    if not os.path.exists(path):
        sys.exit("No release.yaml here: it says what's published (see tools/release.py).")
    with open(path) as f:
        spec = yaml.safe_load(f) or {}
    spec["version"] = version_of(REPO)
    if not spec["version"]:
        sys.exit("veil/version.py has no VERSION (like 2026.10.0).")
    if not re.fullmatch(r"20\d\d\.(?:[1-9]|1[0-2])\.\d+", spec["version"]):
        sys.exit(f"veil/version.py's VERSION {spec['version']} isn't year.month.release (like 2026.10.0, issue #26).")
    if f"## {spec['version']}" not in open(os.path.join(REPO, "CHANGELOG.md")).read():
        sys.exit(f"CHANGELOG.md has no section for {spec['version']} (## {spec['version']}): say what changed first.")
    return spec


def version_of(repo):
    """The version: veil/version.py's VERSION, the one place it's kept (read, not imported)."""
    try:
        with open(os.path.join(repo, "veil", "version.py")) as f:
            found = re.search(r"""^VERSION\s*=\s*["']([^"']+)["']""", f.read(), re.M)
    except OSError:
        return ""
    return found.group(1).strip() if found else ""


def never(path, patterns):
    for p in patterns or []:
        p = str(p)
        if p.endswith("/") and (path + "/").startswith(p):
            return True
        if fnmatch.fnmatch(path, p):
            return True
    return False


def skeleton_backed(folder):
    """The household files that have a skeleton: their place, from the skeletons folder
    (an examples/ folder inside it maps to the same places, examples only)."""
    out = set()
    base = os.path.join(REPO, folder)
    for d, _dirs, files in os.walk(base):
        for f in files:
            rel = os.path.relpath(os.path.join(d, f), base)
            parts = rel.split(os.sep)
            out.add("/".join(parts[1:] if parts[0] == "examples" else parts))
    return out


def build(spec, dest):
    folder = str(spec.get("skeletons") or "").strip("/")
    backed = skeleton_backed(folder) if folder else set()
    kept, left_out = [], []
    for path in git("ls-files").splitlines():
        if never(path, spec.get("never")) and not never(path, spec.get("keep")):
            left_out.append((path, "never"))
        elif path in backed:
            left_out.append((path, f"its skeleton ships in {folder}/"))
        elif not os.path.exists(os.path.join(REPO, path)):
            continue
        else:
            kept.append(path)
            os.makedirs(os.path.dirname(os.path.join(dest, path)) or dest, exist_ok=True)
            shutil.copy2(os.path.join(REPO, path), os.path.join(dest, path))
    ignore_household(spec, dest, sorted(backed))
    return kept, left_out


def ignore_household(spec, dest, backed):
    """A new install makes its household files (from the skeletons) beside the code: the public
    .gitignore gets them, and release.yaml's public_ignore:, so git status doesn't offer them for
    a commit. Only when release.yaml has public_ignore: (a repo without it is left as it was)."""
    extra = spec.get("public_ignore")
    if extra is None:
        return
    # each from the top (/settings.yaml), so defaults/settings.yaml and the like stay in git
    lines = ["/" + str(p).lstrip("/") for p in extra] + ["/" + p for p in backed if not never(p, extra)]
    path = os.path.join(dest, ".gitignore")
    old = open(path).read() if os.path.exists(path) else ""
    with open(path, "w") as f:
        f.write(old.rstrip("\n") + "\n\n# Your household's own files, made on the first start (never committed)\n"
                + "\n".join(lines) + "\n")


def files_in(folder):
    out = {}
    for d, dirs, files in os.walk(folder):
        dirs[:] = [x for x in dirs if x != ".git"]
        for f in files:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, folder).replace(os.sep, "/")] = fh.read()
    return out


def show(title, items, limit=None):
    print(f"\n{title} ({len(items)})")
    for x in items[:limit] if limit else items:
        print("   ", x)
    if limit and len(items) > limit:
        print(f"    ... and {len(items) - limit} more")


def main():
    check_only = "--check" in sys.argv[1:]
    spec = load()
    version = str(spec["version"]).strip()
    tag = f"v{version}"
    if git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("Tracked files have changes not committed. Commit (or put them aside) first: a release is made "
                 "from what's committed.")
    here = git("rev-parse", "--short", "HEAD")
    work = tempfile.mkdtemp(prefix="release-")
    out = os.path.join(work, "build")
    os.makedirs(out)
    kept, left_out = build(spec, out)
    print(f"Release {tag} from development commit {here}: {len(kept)} files go public.")
    show("Left out", [f"{p}  ({why})" for p, why in left_out])

    public = str(spec.get("public") or "").strip()
    branch = str(spec.get("branch") or "main")
    if not public:
        print(f"\nNo public repo yet (release.yaml public: is empty): the public copy is built in {out}; nothing published.")
        return
    pub = os.path.join(work, "public")
    if git("ls-remote", "--heads", public, branch, cwd=work):
        git("clone", "-q", "-b", branch, public, pub, cwd=work)     # the public branch itself
    else:
        git("clone", "-q", public, pub, cwd=work)                   # the first release: nothing there yet
    if tag in git("tag", "-l", cwd=pub).splitlines():
        sys.exit(f"The public repo already has {tag}: change version: in release.yaml.")
    old, new = files_in(pub), files_in(out)
    show("Added", sorted(set(new) - set(old)), 60)
    show("Changed", sorted(p for p in set(new) & set(old) if new[p] != old[p]), 60)
    show("Removed", sorted(set(old) - set(new)), 60)
    if check_only:
        print(f"\n--check: nothing published (the public copy is in {out}).")
        return
    if input(f"\nPublish {tag} to {public}? Type yes to go on: ").strip().lower() != "yes":
        print("Nothing published.")
        return
    for name in os.listdir(pub):
        if name != ".git":
            p = os.path.join(pub, name)
            shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
    shutil.copytree(out, pub, dirs_exist_ok=True)
    git("checkout", "-q", "-B", branch, cwd=pub)
    git("add", "-A", cwd=pub)
    for key in ("user.name", "user.email"):      # the public commit is made as you, like every commit here
        val = git("config", key, check=False)
        if val:
            git("config", key, val, cwd=pub)
    if str(spec.get("email") or "").strip():     # the address the public sees (like GitHub's noreply), else yours here
        git("config", "user.email", str(spec["email"]).strip(), cwd=pub)
    git("commit", "-q", "-m", f"Release {tag}", cwd=pub)
    git("tag", "-a", tag, "-m", f"Release {tag}", cwd=pub)
    git("push", "-q", "origin", branch, cwd=pub)                 # the release first; its tag only once it's in
    git("push", "-q", "origin", tag, cwd=pub)
    git("tag", "-a", f"release-{tag}", "-m", f"Released as {tag} ({public})")
    git("push", "-q", "origin", f"release-{tag}")
    print(f"\nPublished {tag}. This development commit ({here}) is tagged release-{tag}.")
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
