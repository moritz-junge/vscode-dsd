# Change Log

All notable changes to this extension will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2025-08-15

### Added
- Hover documentation for actions, decisions, and entry points

### Changed
- Parsing python files should work more reliably now.
  - Now parses all actions in any folder ending with actions
  - Now parses all decisions in any folder ending with decisions
  - Now parses all entry points in any folder if the name is the snake_case version of the PascalCase Entrypoint in DSD
  - Allow multiple Actions/Decisions in one file by searching for classes in found python files instead of only checking filename

## [0.1.0] - 2025-08-15

This Release exists as a substitute for 0.0.2 and 0.0.3 to correct version naming.
Those versions should have been 0.1.0 and 0.1.1, this release aims to fix this for the future.

## [0.0.3] - 2025-08-15

### Added
- Go to definition for entry points

### Changed
- Updated README with more detailed information about the extension's features

### Removed
- Wrong Requirements from README
- Find References for actions

## [0.0.2] - 2025-08-15

### Added
- Information about VS Code standard language features for DSD files to README
- Basic language server written in [pygls](https://github.com/openlawlibrary/pygls) currently implements:
    - Go to definition (only for subtrees, actions and decisions)
    - Find references (only for subtrees and actions)
- Language server client script for VS Code written in Typescript
- Configuration for which file extensions to associate with DSD language (language server only, syntax highlighting is configured in VS Code directly)
- Language server restart command to VS Code command palette
- New information about language server to README
- Github issue link to package.json
- Requirements description in README

### Changed
- Updated extension from entirely new template to simplify usage


## [0.0.1] - 2023-10-21

### Added
- VS Code extension files every extension needs (most notably package.json)
- Language type contribution in extension to make VS Code recognize DSD as a language
- Syntax highlighting for DSD files through a grammar contribution
- README file with basic information about the extension
- This changelog file to keep track of changes to the extension