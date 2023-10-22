# Change Log

All notable changes to this extension will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.2] - Unreleased

### Added
- Information about VS Code standard language features for DSD files to README
- Basic language server written in [pygls](https://github.com/openlawlibrary/pygls) currently implements:
    - Go to definition (only for subtrees)
    - Find references (only for subtrees and actions)
- Language server client script for VS Code written in Typescript
- Pygls server logging configuration to package.json
- Configuration for which file extensions to associate with DSD language (language server only, syntax highlighting is configured in VS Code directly)
- Language server restart command to VS Code command palette
- Language server execute command to VS Code command palette (experimental, may be removed in future versions)
- New information about language server to README
- Github issue link to package.json
- Requirement for Language server python package
- Requirements description in README

### Changed
- Updated package.json with new dependencies and devDependencies
- Moved language_server into correct package folder structure to make publishing possible


## [0.0.1] - 2023-10-21

### Added
- VS Code extension files every extension needs (most notably package.json)
- Language type contribution in extension to make VS Code recognize DSD as a language
- Syntax highlighting for DSD files through a grammar contribution
- README file with basic information about the extension
- This changelog file to keep track of changes to the extension