# 🔨 Shared-Bot-Utilities

Shared utilities, packages, small API wrappers for my projects.

At some point I've realized that `utils` folders from projects [@Aluerie/AluBot](<https://github.com/Aluerie/AluBot>) and [@Aluerie/IrenesBot](<https://github.com/Aluerie/IrenesBot>) were containing "same but different" files. So in a classic DRY (don't repeat yourself) principle I've decided to make this shared github package that I use in mentioned projects as a git submodule.

> [!WARNING]
>
> * I'm not sure what would be a good solution on how to manage `pyproject.toml` dependencies, formatting and type-checking rules for this repository separately from the projects.
> * This is not a PyPI-like package, just a bunch of classes and methods.
