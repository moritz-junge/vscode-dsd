# DSD VSCode Extension

This extension adds language support for the Dynamic Stack Decider ([DSD](https://github.com/bit-bots/dynamic_stack_decider)) language.
As of now, it only adds syntax highlighting but full language support including auto-completion, auto-formatting and more is planned.

## Features

- Syntax highlighting for DSD files:

![Syntax Highlighting](./images/syntax_highlighting-3.png) <br>
[Code Source](https://github.com/bit-bots/bitbots_behavior/blob/master/bitbots_body_behavior/bitbots_body_behavior/minimal.dsd)

- Toggle comment (with \[Ctrl + /\] or \[Ctrl + #\] by default).
- Go to definition (\[F12\] by default)
- Find references (\[Shift + F12\] by default)

## Requirements

You need to have Python^1.11.1 as well as the [official python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python) installed.
That Python version needs to be set as your python interpreter (see [here](https://code.visualstudio.com/docs/python/environments#_select-and-activate-an-environment) for more information).
Then you need to install the language server python package in that python environment by running `pip install --index-url https://test.pypi.org/simple/ your-package` (currently on testpy until developed further) in your terminal.

## Extension Settings

As of now this extension has no settings. Mandetory settings will be added once further features are added so check back here when you update the extension.

This extension contributes the following settings:

* `dsd.client.documentSelector`: Set which files should be interpreted as DSD by the language server.
* `pygls.trace.server`: Set logging level of the server to VS Code Output.

## Known Issues

- The name of the entrypoint is currently not highlighted.

If you find any issues not listed here, please report them on the [GitHub issue tracker](https://github.com/Mastermori/vscode-dsd/issues).

## Release Notes

A comprehensive changelog can be found in this [changelog](./CHANGELOG.md).

### 0.0.1

Initial development release, providing syntax highlighting for DSD files.

<!-- ### 1.0.0

Initial release. -->
