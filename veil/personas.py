# veil/personas.py - the assistants: one file each in personality/ (wren.yaml, juniper.yaml). Core:
# who she is and the names she's heard by. What she adds to her answers (flair, people's names) is
# an add-on's (issue #25), read from the same file by that add-on.

import os

import yaml

from veil import util

# files in personality/ that aren't an assistant: where her lines come from, how the books are combed
NOT_PERSONALITIES = ("sources", "combing")


def files(folder):
    """{assistant: its personality file (a dict)}, for every personality/<name>.yaml that is one."""
    out = {}
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if name.endswith((".yaml", ".yml")) and not name.startswith(NOT_PERSONALITIES):
                with open(os.path.join(folder, name)) as fh:
                    doc = yaml.safe_load(fh)
                out[name.rsplit(".", 1)[0].lower()] = doc if isinstance(doc, dict) else {}
    return out


def names(folder):
    """The assistants, by their files' names."""
    return sorted(files(folder))


def words(folder):
    """Each assistant's name (its file's name) and how speech-to-text hears it (heard_as:), lowercase.
    Said alone they're filler, like "um" (vocab/path0.yaml filler_words), never a request."""
    out = set()
    for who, doc in files(folder).items():
        out.add(who)
        heard = doc.get("heard_as")
        if isinstance(heard, str):       # one name written without the list's brackets
            heard = [heard]
        # each as the router compares words (util.words: "Esmé." is "esm"), a word at a time
        out |= {w for h in heard or [] if isinstance(h, str) for w in util.words(h).split()}
    return out
