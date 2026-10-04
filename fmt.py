"""Formatting utilities.

Notices
-------
* MPL-2.0 License, see LICENSE file for more details.
* Copyright (C) 2020-present @Aluerie.
"""

from __future__ import annotations

import pprint
from typing import TYPE_CHECKING, Any, override

if TYPE_CHECKING:
    from collections.abc import Sequence


__all__ = (
    "codeblock",
    "ordinal",
    "plural",
)

# fmt: off
# cSpell:disable
CODE_LANGUAGES = [
    # list of code languages that can be used in discord's triple backtick ` codeblocks
    # https://www.reddit.com/r/discordapp/comments/8krzjp/list_of_languages_you_can_use_in_codeblocks/
    # https://highlightjs.org/demo
    "1c", "abnf", "accesslog", "actionscript", "ada", "angelscript", "apache", "applescript", "arcade", "arduino",
    "armasm", "xml", "asciidoc", "aspectj", "autohotkey", "autoit", "avrasm", "awk", "axapta", "bash", "basic", "bnf",
    "brainfuck", "c", "cal", "capnproto", "ceylon", "clean", "clojure", "clojure-repl", "cmake", "coffeescript", "coq",
    "cos", "cpp", "crmsh", "crystal", "csharp", "csp", "css", "d", "markdown", "dart", "delphi", "diff", "django",
    "dns", "dockerfile", "dos", "dsconfig", "dts", "dust", "ebnf", "elixir", "elm", "ruby", "erb", "erlang-repl",
    "erlang", "excel", "fix", "flix", "fortran", "fsharp", "gams", "gauss", "gcode", "gherkin", "glsl", "gml", "go",
    "golo", "gradle", "graphql", "groovy", "haml", "handlebars", "haskell", "haxe", "hsp", "http", "hy", "inform7",
    "ini", "irpf90", "isbl", "java", "javascript", "jboss-cli", "json", "julia", "julia-repl", "kotlin", "lasso",
    "latex", "ldif", "leaf", "less", "lisp", "livecodeserver", "livescript", "llvm", "lsl", "lua", "makefile",
    "mathematica", "matlab", "maxima", "mel", "mercury", "mipsasm", "mizar", "perl", "mojolicious", "monkey",
    "moonscript", "n1ql", "nestedtext", "nginx", "nim", "nix", "node-repl", "nsis", "objectivec", "ocaml", "openscad",
    "oxygene", "parser3", "pf", "pgsql", "php", "php-template", "plaintext", "pony", "powershell", "processing",
    "profile", "prolog", "properties", "protobuf", "puppet", "purebasic", "python", "python-repl", "q", "qml", "r",
    "reasonml", "rib", "roboconf", "routeros", "rsl", "ruleslanguage", "rust", "sas", "scala", "scheme", "scilab",
    "scss", "shell", "smali", "smalltalk", "sml", "sqf", "sql", "stan", "stata", "step21", "stylus", "subunit", "swift",
    "taggerscript", "yaml", "tap", "tcl", "thrift", "tp", "twig", "typescript", "vala", "vbnet", "vbscript",
    "vbscript-html", "verilog", "vhdl", "vim", "wasm", "wren", "x86asm", "xl", "xquery", "zephir",
]
# fmt: on
# # cSpell:enable


def codeblock(text: str, language: str = "py") -> str:
    """Wrap text into a triple "`" discord codeblock.

    For no code version we can just use `language=""`.

    You can check which languages are supported in Discord by looking at the `fmt.CODE_LANGUAGES` constant.
    """
    return f"```{language}\n{text}```"


def pformat_dict(data: dict[str, Any]) -> str:
    """Pformat Kwarg or dictionaries (mainly for the discord messages)."""
    return codeblock(
        text=(
            "\n".join(f"{name}={pprint.pformat(repr(value), indent=4)}" for name, value in data.items())
            if data
            else "No arguments"
        ),
        language="toml",
    )


def ordinal(n: int | str) -> str:
    """Convert an integer into its ordinal representation, i.e. 0->'0th', '3'->'3rd'.

    Dev Note
    --------
    Remember that there is always a funny lambda possibility
    `ordinal = lambda n: "%d%s" % (n, "tsnrhtdd"[(n // 10 % 10 != 1) * (n % 10 < 4) * n % 10::4])`
    """
    n = int(n)
    suffix = "th" if 11 <= n % 100 <= 13 else ["th", "st", "nd", "rd", "th"][min(n % 10, 4)]
    return str(n) + suffix


class plural:  # ruff: ignore[invalid-class-name]
    """Helper class to format tricky number + singular/plural noun situations.

    Returns a human-readable string combining number and a proper noun.

    Some usage rules:
    * if it's a special word (plural form doesn't follow simple "-s" ending rule) then separate them with "|".
    * if you want to skip the number from the output - add "!" to the end of formatting spec.

    Examples
    --------
    >>> format(plural(1), 'child|children')  # '1 child'
    >>> format(plural(8), 'week|weeks')  # '8 weeks'
    >>> f'{plural(3):reminder}' # '3 reminders'
    >>> f'{plural(3):reminder!}' # 'reminders'

    Sources
    -------
    * Rapptz/RoboDanny (licensed MPL v2), `plural` class:
        https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/utils/formats.py
    """

    def __init__(self, number: int) -> None:
        self.number: int = number

    @override
    def __format__(self, format_spec: str) -> str:
        number = self.number

        skip_number = format_spec.endswith("!")
        if skip_number:
            format_spec = format_spec[:-1]

        singular, _, plural = format_spec.partition("|")  # _ is `separator`
        plural = plural or f"{singular}s"

        if skip_number:
            return singular if abs(number) == 1 else plural
        return f"{number} {singular}" if abs(number) == 1 else f"{number} {plural}"


def human_join(seq: Sequence[str], delim: str = ", ", final: str = "or") -> str:
    """Join sequence of string in human-readable format.

    Examples
    --------
    >>> human_join(['Conan Doyle', 'Nabokov', 'Fitzgerald'], final='and')
    'Conan Doyle, Nabokov and Fitzgerald'

    Sources
    -------
    * Rapptz/RoboDanny (license MPL v2)
        https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/utils/formats.py
    """
    size = len(seq)
    if size == 0:
        return ""

    if size == 1:
        return seq[0]

    if size == 2:
        return f"{seq[0]} {final} {seq[1]}"

    return delim.join(seq[:-1]) + f" {final} {seq[-1]}"
