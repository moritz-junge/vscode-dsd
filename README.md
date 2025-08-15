# DSD VSCode Extension

This extension adds language support for the Dynamic Stack Decider ([DSD](https://github.com/bit-bots/dynamic_stack_decider)) language.

This Extension is still under active development and will include more features in the future.

## Features

- Syntax highlighting for DSD files:

![Syntax Highlighting](./images/syntax_highlighting-3.png) <br>
[Code Source](https://github.com/bit-bots/bitbots_behavior/blob/master/bitbots_body_behavior/bitbots_body_behavior/minimal.dsd)

- Toggle comment (with \[Ctrl + /\] or \[Ctrl + #\] by default).
- Go to definition (\[F12\] by default) for some symbols:
  - Subtrees in the DSD file
  - Actions (jumps to their python class) - this only works for actions in [vscode-workspace-root]/actions folder.
  - Decisions (jumps to their python class) - this only works for decisions in [vscode-workspace-root]/decisions folder.
  - Entry points (jumps to their python class) - this only works for entry points in [vscode-workspace-root] folder.
- Find references (\[Shift + F12\] by default)
  - Subtrees in the DSD file
- Hover documentation
  - Shows documentation for Actions,  Decisions and Entrypoints
    - Displays the docstring of the corresponding Python class or file in case of Entrypoints

## Requirements

For advanced language features to work you need to fulfill the following requirements:
- have the [official python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python) installed in VS Code.
- have python 3.9 or a newer version installed on your system.

## Extension Settings

This extension contributes the following settings:

* `dsd.interpreter`: Use this to override which python interpreter is used for the Language Server (needs to be version 3.9 or higher).
* `dsd.showNotifications`: Controls when notifications are shown by this extension.

## Known Issues

- The name of the entrypoint is currently not properly highlighted.

If you find any issues not listed here, please report them on the [GitHub issue tracker](https://github.com/Mastermori/vscode-dsd/issues).

## Release Notes

A comprehensive changelog can be found in this [changelog](./CHANGELOG.md). \
Here are some highlights:

### 0.1.1

- Added Hover documentation for Actions and Decisions.
- Improved searching for actions and decisions in Python files.

### 0.1.0

- Added new language features (see [CHANGELOG.md](./CHANGELOG.md)):
  - Go to definition (\[F12\] by default)
  - Find references (\[Shift + F12\] by default)

These features use a language server that now exists.

### 0.0.1

- Initial development release, providing syntax highlighting for DSD files.
