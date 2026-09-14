"""
Formatting utilities.

License
-------
* This Source Code Form is subject to the terms of the [Mozilla Public License v2.0](<http://mozilla.org/MPL/2.0/>).
* Copyright (C) 2020-present [@Aluerie](<https://github.com/Aluerie>).
"""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, override

from discord.utils import MISSING

if TYPE_CHECKING:
    import datetime

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
# fmt: on # cSpell:enable


def codeblock(text: str, language: str = "py") -> str:
    """Wrap text into a Python triple "`" discord codeblock.

    It's just annoying to type sometimes. Also shorter like this.
    For no code version we can just use `language=""`.

    For languages codes supported by Discord you can look the variable `fmt.CODE_LANGUAGES`.
    """
    return f"```{language}\n{text}```"


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


class plural:  # noqa: N801
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

        skip_number = format_spec.endswith('!')
        if skip_number:
            format_spec = format_spec[:-1]

        singular, _, plural = format_spec.partition("|")  # _ is `separator`
        plural = plural or f"{singular}s"

        if skip_number:
            return singular if abs(number) == 1 else plural
        return f"{number} {singular}" if abs(number) == 1 else f"{number} {plural}"


class TimeDeltaFormat(IntEnum):
    """An enum representing options for `fmt` argument in `timedelta_to_words` function."""

    Full = 1
    """1 minute 6 seconds"""
    Short = 2
    """1 min 30 sec"""
    Letter = 3
    """1m30s"""


def timedelta_to_words(
    timedelta: datetime.timedelta = MISSING,
    seconds: int = MISSING,
    *,
    accuracy: int = 2,
    fmt: TimeDeltaFormat = TimeDeltaFormat.Full,
) -> str:
    """Convert `datetime.timedelta` to a string of humanly readable words.

    Parameters
    ----------
    timedelta: datetime.timedelta = MISSING
        Time delta to convert to words (as datetime.timedelta type)
    seconds: int = MISSING
        Time delta to convert to words (as integer amount of seconds).
        Note that you should pass only one argument: either `delta` or `seconds`.
    accuracy: int = 2
        Amount of words to allow in the result. This is called accuracy because effectively,
        we are cutting down on how accurately the wording represents the time delta.
    fmt: TimeDeltaFormat = TimeDeltaFormat.Full
        A formatting choice for the output.
        The examples of each are given in `TimeDeltaFormat` class' doc-strings for each enum.

    Returns
    -------
    str
        Human-readable description for the time delta.

    Example:
    -------
    ```
    x = datetime.timedelta(seconds=66)
    timedelta_to_words(x)  # "1 minute 6 seconds"
    ```
    """
    if timedelta is not MISSING and seconds is not MISSING:
        msg = "Cannot mix `delta` and `seconds` keyword arguments."
        raise TypeError(msg)

    if timedelta:
        total_seconds = int(timedelta.total_seconds())
    elif seconds:
        total_seconds = seconds
    else:
        msg = "You need to provide at least one of the following arguments: `delta` and `seconds`."
        raise TypeError(msg)

    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    match fmt:
        case TimeDeltaFormat.Full:  # 1 minute 6 seconds
            time_units = {"day": days, "hour": hours, "minute": minutes, "second": seconds}
            output = [format(plural(number), word) for word, number in time_units.items() if number]
            return " ".join(output[:accuracy])
        case TimeDeltaFormat.Short:  # 1 min 30 sec
            time_units = {"day(-s)": days, "hr": hours, "min": minutes, "sec": seconds}
            output = [f"{number} {short}" for short, number in time_units.items() if number]
            return " ".join(output[:accuracy])
        case TimeDeltaFormat.Letter:  # 1m30s
            time_units = {"d": days, "h": hours, "m": minutes, "s": seconds}
            output = [f"{number:02d}{letter}" for letter, number in time_units.items() if number]
            return "".join(output[:accuracy]).removeprefix("0")  # remove leading zero if it managed to sneak in
