# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Implementation of tool support over LSP."""
from __future__ import annotations

import copy
import json
import os
import pathlib
import re
import sys
import traceback


# **********************************************************
# Update sys.path before importing any bundled libraries.
# **********************************************************
def update_sys_path(path_to_add: str, strategy: str) -> None:
    """Add given path to `sys.path`."""
    if path_to_add not in sys.path and os.path.isdir(path_to_add):
        if strategy == "useBundled":
            sys.path.insert(0, path_to_add)
        elif strategy == "fromEnvironment":
            sys.path.append(path_to_add)


# Ensure that we can import LSP libraries, and other bundled libraries.
update_sys_path(
    os.fspath(pathlib.Path(__file__).parent.parent / "libs"),
    os.getenv("LS_IMPORT_STRATEGY", "useBundled"),
)

# **********************************************************
# Imports needed for the language server goes below this.
# **********************************************************
# pylint: disable=wrong-import-position,import-error
import lsp_jsonrpc as jsonrpc
import lsp_utils as utils
import lsprotocol.types as lsp
import ast
from typing import Any, List, Optional, Sequence, Set
from pygls import server, uris, workspace
from pygls.workspace.text_document import TextDocument

WORKSPACE_SETTINGS = {}
GLOBAL_SETTINGS = {}
RUNNER = pathlib.Path(__file__).parent / "lsp_runner.py"

MAX_WORKERS = 5
LSP_SERVER = server.LanguageServer(name="DSD Language Server", version="0.0.2", max_workers=MAX_WORKERS)


# **********************************************************
# Tool specific code goes below this.
# **********************************************************

# Reference:
#  LS Protocol:
#  https://microsoft.github.io/language-server-protocol/specifications/specification-3-16/
#
#  Sample implementations:
#  Pylint: https://github.com/microsoft/vscode-pylint/blob/main/bundled/tool
#  Black: https://github.com/microsoft/vscode-black-formatter/blob/main/bundled/tool
#  isort: https://github.com/microsoft/vscode-isort/blob/main/bundled/tool

TOOL_MODULE = "dsd"

TOOL_DISPLAY = "Dynamic Stack Decider"

TOOL_ARGS = []  # default arguments always passed to your tool.


## Features
@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_COMPLETION, lsp.CompletionOptions(trigger_characters=["@", "$", "#"]))
def completions(params: Optional[lsp.CompletionParams] = None) -> lsp.CompletionList | None:
    log_to_output("Completions requested")
    items = []
    lines = get_file_contents(params.text_document.uri)
    position = params.position
    line = lines[position.line]
    _, range = find_word_from_position(lines, position)
    if range[0] < 1:
        return None
    cursor_word_prefix = line[range[0] - 1]
    if cursor_word_prefix == "@":
        items.extend(map(lambda action: lsp.CompletionItem(label=action), get_all_actions()))
    if cursor_word_prefix == "$":
        items.extend(map(lambda decision: lsp.CompletionItem(label=decision), get_all_decisions()))
    if cursor_word_prefix == "#" and not range[0] - 1 == 0:
        items.extend(map(lambda subtree: lsp.CompletionItem(label=subtree), get_all_subtrees_in(lines)))

    return lsp.CompletionList(is_incomplete=False, items=items)


def get_all_actions() -> Set[str]:
    return get_classes_in_python_files("*actions/")


def get_all_decisions() -> Set[str]:
    return get_classes_in_python_files("*decisions/")


def get_all_subtrees_in(lines: List[str]) -> Set[str]:
    subtree_names = set()
    for line in lines:
        if not line.startswith("#"):
            continue
        match = re.match(r"#(\w+)", line)
        if not match:
            continue
        subtree_name = match.group(1)
        subtree_names.add(subtree_name)
    return subtree_names


def get_classes_in_python_files(folder: str) -> Set[str]:
    python_files = get_all_python_files_in(folder)
    class_names = set()
    for document in python_files:
        tree = ast.parse(document.source)
        for element in tree.body:
            if not isinstance(element, ast.ClassDef):
                continue
            if element.name.lower().startswith("abstract"):
                continue  # Skip abstract classes
            class_names.add(element.name)
    return class_names


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_HOVER)
def hover(params: lsp.TextDocumentPositionParams) -> lsp.Hover | None:
    lines = get_file_contents(params.text_document.uri)
    position = params.position
    line = lines[position.line]
    word, range = find_word(line, position.character)
    if is_entrypoint(line, range):
        comment = get_class_comment_from_location(find_entrypoint_file_location(word))
        return lsp.Hover(contents=f"Entrypoint: {word}" + (f" \n\n_{comment}_" if len(comment) > 0 else ""))
    if is_action(line, range):
        action_class_file_location = find_action_file_location(word)
        comment = get_class_comment_from_location(action_class_file_location)
        parameters = get_class_defined_parameters(action_class_file_location)
        inherited_parameters = get_inherited_parameters(action_class_file_location, "*actions/")
        all_parameters = sorted(list(parameters.union(inherited_parameters).union(set(["r / reevaluate"]))))
        parameters_string = ", ".join(all_parameters) if len(all_parameters) > 0 else ""
        return lsp.Hover(
            contents=f"### {word}\n----------"
            + (f" \n\n{comment}" if len(comment) > 0 else "")
            + (f" \n\n**Parameters**:\n{parameters_string}" if len(parameters_string) > 0 else "")
        )
    if is_decision(line, range):
        comment = get_class_comment_from_location(find_decision_file_location(word))
        return lsp.Hover(contents=f"Decision: {word}" + (f" \n\n{comment}" if len(comment) > 0 else ""))
    if is_subtree(line, range):
        return lsp.Hover(contents=f"Subtree: {word}")
    return None


def get_class_comment_from_location(location: lsp.Location) -> str:
    if location is None:
        return ""
    class_file = LSP_SERVER.workspace.get_text_document(location.uri)
    comment_line = location.range.end.line + 1
    if len(class_file.lines) <= comment_line:
        return ""  # File ends after class definition
    return get_class_comment(class_file, comment_line)


def get_class_comment(file: TextDocument, start_line: int) -> str:
    content = "".join(file.lines[start_line:])
    match = re.search(r'\A\s*"""([\w\W]*?)"""', content)
    comment = match.group(1).strip() if match else ""
    return comment.replace("\n", " \\\n")


def get_inherited_parameters(location: lsp.Location, search_folder: str) -> set[str]:
    if location is None:
        return set()
    parent_class_location = get_parent_class(location, search_folder)
    if parent_class_location is None:
        return set()
    return get_class_defined_parameters(parent_class_location).union(
        get_inherited_parameters(parent_class_location, search_folder)
    )


def get_parent_class(location: lsp.Location, search_folder: str) -> lsp.Location | None:
    if location is None:
        return None
    class_file = LSP_SERVER.workspace.get_text_document(location.uri)
    class_definition_line = class_file.lines[location.range.start.line]
    match = re.match(r"^\s*class\s+\w+\s*\((\w+)\)", class_definition_line)
    if match is not None:
        parent_class_name = match.group(1)
        return find_class_in_python_files(parent_class_name, search_folder)
    return None


def get_class_defined_parameters(location: lsp.Location) -> set[str]:
    if location is None:
        return set()
    class_file = LSP_SERVER.workspace.get_text_document(location.uri)
    class_definition_line = location.range.start.line
    return get_parameters_in_lines(get_class_definition_lines(class_file.lines, class_definition_line))


def get_class_definition_lines(lines: list[str], start_line: int) -> list[str]:
    class_lines = [lines[start_line]]
    if len(lines) - 1 == start_line:
        return class_lines
    for line in lines[start_line + 1 :]:
        if re.match(r'^(?:\s+)|^#|^"""', line) is None:
            break
        class_lines.append(line)
    return class_lines


def get_parameters_in_lines(lines: list[str]) -> set[str]:
    parameters = set()
    matches = re.finditer(r'parameters\.get\((?:["]([A-Za-z_]+?)["]|[\']([A-Za-z_]+?)[\'])', "\n".join(lines))
    for match in matches:
        parameters.add(match.group(1) or match.group(2))
    return parameters


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DEFINITION)
def goto_definition(params: lsp.TextDocumentPositionParams) -> lsp.Location | None:
    lines = get_file_contents(params.text_document.uri)
    position = params.position
    line = lines[position.line]
    word, range = find_word(line, position.character)
    log_to_output(f"word: {word}, range: {range}")

    if len(word.strip()) < 1:
        return None

    # GOTO Entrypoint
    if is_entrypoint(line, range):
        return find_entrypoint_file_location(word)

    # GOTO Action
    if is_action(line, range):
        return find_action_file_location(word)

    # GOTO Decision
    if is_decision(line, range):
        return find_decision_file_location(word)

    # GOTO Subtrees
    if not is_subtree(line, range):
        return None
    for line_index, line in enumerate(lines):
        found_index = line.find(f"#{word}")
        if found_index < 0:
            continue
        end_index = found_index + len(word)
        if end_index < len(line):
            return make_location(params.text_document.uri, line_index, found_index, end_index)


@LSP_SERVER.feature(lsp.TEXT_DOCUMENT_REFERENCES)
def find_references(params: lsp.ReferenceParams) -> List[lsp.Location] | None:
    lines = get_file_contents(params.text_document.uri)
    position = params.position
    line = lines[position.line]
    word, range = find_word(line, position.character)
    if range[0] < 1:
        return None
    if not line[range[0] - 1] in ["#"]:  # Only find references for subtrees
        return None
    word = f"{line[range[0] - 1]}{word}"
    if len(word.strip()) < 1:
        return None
    found_locations: List[lsp.Location] = []
    for line_index, line in enumerate(lines):
        found_index = line.find(word)
        if found_index < 0:
            continue
        end_index = found_index + len(word)
        found_locations.append(make_location(params.text_document.uri, line_index, found_index, end_index))
    return found_locations


## Helper functions
def make_location(uri: str, line_index: int, start_index: int, end_index: int) -> lsp.Location:
    return lsp.Location(uri, lsp.Range(lsp.Position(line_index, start_index), lsp.Position(line_index, end_index)))


def get_file_contents(uri: str) -> List[str]:
    return list(LSP_SERVER.workspace.get_text_document(uri).lines)


def find_word(line: str, position: int) -> tuple[str, tuple[int, int]]:
    line = line.removesuffix("\n").removesuffix("\r")
    word_indices = [(ele.start(), ele.end()) for ele in re.finditer(r"[A-Za-z]\w*", line)]
    for i in word_indices:
        if i[0] <= position and i[1] >= position:
            return line[i[0] : i[1]], i
    if position == len(line):
        return "", (position, position)
    return line[position], (position, position)


def find_word_from_position(file_lines: List[str], position: lsp.Position) -> tuple[str, tuple[int, int]]:
    return find_word(file_lines[position.line], position.character)


def is_subtree(line: str, range: tuple[int, int]) -> bool:
    return range[0] > 0 and line[range[0] - 1] == "#"


def is_action(line: str, range: tuple[int, int]) -> bool:
    return range[0] > 0 and line[range[0] - 1] == "@"


def is_decision(line: str, range: tuple[int, int]) -> bool:
    return range[0] > 0 and line[range[0] - 1] == "$"


def is_entrypoint(line: str, range: tuple[int, int]) -> bool:
    return range[0] >= 3 and line[range[0] - 3] == "-" and line[range[0] - 2] == "-" and line[range[0] - 1] == ">"


def find_action_file_location(action_name: str) -> lsp.Location | None:
    return find_class_in_python_files(action_name, "*actions/")


def find_decision_file_location(decision_name: str) -> lsp.Location | None:
    return find_class_in_python_files(decision_name, "*decisions/")


def find_entrypoint_file_location(entrypoint_name: str) -> lsp.Location | None:
    return find_class_in_python_files(entrypoint_name, "")


def to_snake(pascal: str) -> str:
    """Converts a Pascal case string to snake case."""
    magic = re.findall("[A-Z]+[a-z]*", pascal)
    snake = "_".join(magic)
    snake = snake.lower()

    return snake


def find_class_in_python_files(class_name: str, folder: str) -> lsp.Location | None:
    """Finds a class in all Python files within a specific folder."""
    python_files = get_all_python_files_in(folder)
    direct_file = None
    for document in python_files:
        if document.filename.replace(".py", "") == to_snake(class_name):
            direct_file = document
        if document.lines is None:
            continue
        for line_index, line in enumerate(document.lines):
            match = re.match(r"class\s+(\w+)\s*\(", line)
            if not match:
                continue
            if class_name != match.group(1):
                continue
            start_index = match.start(1)
            end_index = match.end(1)
            return make_location(document.uri, line_index, start_index, end_index)
    if direct_file is not None:
        return make_location(direct_file.uri, 0, 0, 0)
    return None


def get_all_python_files_in(folder: str) -> List[TextDocument]:
    """Returns all Python files in the workspace."""
    python_files = []
    workspace_root = pathlib.Path(uris.to_fs_path(LSP_SERVER.workspace.root_uri))
    for py_file in workspace_root.glob(f"**/{folder}*.py"):
        try:
            document = LSP_SERVER.workspace.get_text_document(uris.from_fs_path(str(py_file)))
            python_files.append(document)
        except Exception:
            continue
    return python_files


# TODO: If your tool is a linter then update this section.
# Delete "Linting features" section if your tool is NOT a linter.
# **********************************************************
# Linting features start here
# **********************************************************

#  See `pylint` implementation for a full featured linter extension:
#  Pylint: https://github.com/microsoft/vscode-pylint/blob/main/bundled/tool


# @LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
def did_open(params: lsp.DidOpenTextDocumentParams) -> None:
    """LSP handler for textDocument/didOpen request."""
    document = LSP_SERVER.workspace.get_document(params.text_document.uri)
    diagnostics: list[lsp.Diagnostic] = _linting_helper(document)
    LSP_SERVER.publish_diagnostics(document.uri, diagnostics)


# @LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_SAVE)
def did_save(params: lsp.DidSaveTextDocumentParams) -> None:
    """LSP handler for textDocument/didSave request."""
    document = LSP_SERVER.workspace.get_document(params.text_document.uri)
    diagnostics: list[lsp.Diagnostic] = _linting_helper(document)
    LSP_SERVER.publish_diagnostics(document.uri, diagnostics)


# @LSP_SERVER.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
def did_close(params: lsp.DidCloseTextDocumentParams) -> None:
    """LSP handler for textDocument/didClose request."""
    document = LSP_SERVER.workspace.get_document(params.text_document.uri)
    # Publishing empty diagnostics to clear the entries for this file.
    LSP_SERVER.publish_diagnostics(document.uri, [])


def _linting_helper(document: workspace.Document) -> list[lsp.Diagnostic]:
    # TODO: Determine if your tool supports passing file content via stdin.
    # If you want to support linting on change then your tool will need to
    # support linting over stdin to be effective. Read, and update
    # _run_tool_on_document and _run_tool functions as needed for your project.
    result = _run_tool_on_document(document)
    return _parse_output_using_regex(result.stdout) if result.stdout else []


# TODO: If your linter outputs in a known format like JSON, then parse
# accordingly. But incase you need to parse the output using RegEx here
# is a helper you can work with.
# flake8 example:
# If you use following format argument with flake8 you can use the regex below to parse it.
# TOOL_ARGS += ["--format='%(row)d,%(col)d,%(code).1s,%(code)s:%(text)s'"]
# DIAGNOSTIC_RE =
#    r"(?P<line>\d+),(?P<column>-?\d+),(?P<type>\w+),(?P<code>\w+\d+):(?P<message>[^\r\n]*)"
DIAGNOSTIC_RE = re.compile(r"")


def _parse_output_using_regex(content: str) -> list[lsp.Diagnostic]:
    lines: list[str] = content.splitlines()
    diagnostics: list[lsp.Diagnostic] = []

    # TODO: Determine if your linter reports line numbers starting at 1 (True) or 0 (False).
    line_at_1 = True
    # TODO: Determine if your linter reports column numbers starting at 1 (True) or 0 (False).
    column_at_1 = True

    line_offset = 1 if line_at_1 else 0
    col_offset = 1 if column_at_1 else 0
    for line in lines:
        if line.startswith("'") and line.endswith("'"):
            line = line[1:-1]
        match = DIAGNOSTIC_RE.match(line)
        if match:
            data = match.groupdict()
            position = lsp.Position(
                line=max([int(data["line"]) - line_offset, 0]),
                character=int(data["column"]) - col_offset,
            )
            diagnostic = lsp.Diagnostic(
                range=lsp.Range(
                    start=position,
                    end=position,
                ),
                message=data.get("message"),
                severity=_get_severity(data["code"], data["type"]),
                code=data["code"],
                source=TOOL_MODULE,
            )
            diagnostics.append(diagnostic)

    return diagnostics


# TODO: if you want to handle setting specific severity for your linter
# in a user configurable way, then look at look at how it is implemented
# for `pylint` extension from our team.
# Pylint: https://github.com/microsoft/vscode-pylint
# Follow the flow of severity from the settings in package.json to the server.
def _get_severity(*_codes: list[str]) -> lsp.DiagnosticSeverity:
    # TODO: All reported issues from linter are treated as warning.
    # change it as appropriate for your linter.
    return lsp.DiagnosticSeverity.Warning


# **********************************************************
# Linting features end here
# **********************************************************

# TODO: If your tool is a formatter then update this section.
# Delete "Formatting features" section if your tool is NOT a
# formatter.
# **********************************************************
# Formatting features start here
# **********************************************************
#  Sample implementations:
#  Black: https://github.com/microsoft/vscode-black-formatter/blob/main/bundled/tool


# @LSP_SERVER.feature(lsp.TEXT_DOCUMENT_FORMATTING)
def formatting(params: lsp.DocumentFormattingParams) -> list[lsp.TextEdit] | None:
    """LSP handler for textDocument/formatting request."""
    # If your tool is a formatter you can use this handler to provide
    # formatting support on save. You have to return an array of lsp.TextEdit
    # objects, to provide your formatted results.

    document = LSP_SERVER.workspace.get_document(params.text_document.uri)
    edits = _formatting_helper(document)
    if edits:
        return edits

    # NOTE: If you provide [] array, VS Code will clear the file of all contents.
    # To indicate no changes to file return None.
    return None


def _formatting_helper(document: workspace.Document) -> list[lsp.TextEdit] | None:
    # TODO: For formatting on save support the formatter you use must support
    # formatting via stdin.
    # Read, and update_run_tool_on_document and _run_tool functions as needed
    # for your formatter.
    result = _run_tool_on_document(document, use_stdin=True)
    if result.stdout:
        new_source = _match_line_endings(document, result.stdout)
        return [
            lsp.TextEdit(
                range=lsp.Range(
                    start=lsp.Position(line=0, character=0),
                    end=lsp.Position(line=len(document.lines), character=0),
                ),
                new_text=new_source,
            )
        ]
    return None


def _get_line_endings(lines: list[str]) -> str:
    """Returns line endings used in the text."""
    try:
        if lines[0][-2:] == "\r\n":
            return "\r\n"
        return "\n"
    except Exception:  # pylint: disable=broad-except
        return None


def _match_line_endings(document: workspace.Document, text: str) -> str:
    """Ensures that the edited text line endings matches the document line endings."""
    expected = _get_line_endings(document.source.splitlines(keepends=True))
    actual = _get_line_endings(text.splitlines(keepends=True))
    if actual == expected or actual is None or expected is None:
        return text
    return text.replace(actual, expected)


# **********************************************************
# Formatting features ends here
# **********************************************************


# **********************************************************
# Required Language Server Initialization and Exit handlers.
# **********************************************************
@LSP_SERVER.feature(lsp.INITIALIZE)
def initialize(params: lsp.InitializeParams) -> None:
    """LSP handler for initialize request."""
    log_to_output(f"CWD Server: {os.getcwd()}")

    paths = "\r\n   ".join(sys.path)
    log_to_output(f"sys.path used to run Server:\r\n   {paths}")

    GLOBAL_SETTINGS.update(**params.initialization_options.get("globalSettings", {}))

    settings = params.initialization_options["settings"]
    _update_workspace_settings(settings)
    log_to_output(f"Settings used to run Server:\r\n{json.dumps(settings, indent=4, ensure_ascii=False)}\r\n")
    log_to_output(f"Global settings:\r\n{json.dumps(GLOBAL_SETTINGS, indent=4, ensure_ascii=False)}\r\n")


@LSP_SERVER.feature(lsp.EXIT)
def on_exit(_params: Optional[Any] = None) -> None:
    """Handle clean up on exit."""
    jsonrpc.shutdown_json_rpc()


@LSP_SERVER.feature(lsp.SHUTDOWN)
def on_shutdown(_params: Optional[Any] = None) -> None:
    """Handle clean up on shutdown."""
    jsonrpc.shutdown_json_rpc()


def _get_global_defaults():
    return {
        "path": GLOBAL_SETTINGS.get("path", []),
        "interpreter": GLOBAL_SETTINGS.get("interpreter", [sys.executable]),
        "args": GLOBAL_SETTINGS.get("args", []),
        "importStrategy": GLOBAL_SETTINGS.get("importStrategy", "useBundled"),
        "showNotifications": GLOBAL_SETTINGS.get("showNotifications", "off"),
    }


def _update_workspace_settings(settings):
    if not settings:
        key = os.getcwd()
        WORKSPACE_SETTINGS[key] = {
            "cwd": key,
            "workspaceFS": key,
            "workspace": uris.from_fs_path(key),
            **_get_global_defaults(),
        }
        return

    for setting in settings:
        key = uris.to_fs_path(setting["workspace"])
        WORKSPACE_SETTINGS[key] = {
            "cwd": key,
            **setting,
            "workspaceFS": key,
        }


def _get_settings_by_path(file_path: pathlib.Path):
    workspaces = {s["workspaceFS"] for s in WORKSPACE_SETTINGS.values()}

    while file_path != file_path.parent:
        str_file_path = str(file_path)
        if str_file_path in workspaces:
            return WORKSPACE_SETTINGS[str_file_path]
        file_path = file_path.parent

    setting_values = list(WORKSPACE_SETTINGS.values())
    return setting_values[0]


def _get_document_key(document: workspace.Document):
    if WORKSPACE_SETTINGS:
        document_workspace = pathlib.Path(document.path)
        workspaces = {s["workspaceFS"] for s in WORKSPACE_SETTINGS.values()}

        # Find workspace settings for the given file.
        while document_workspace != document_workspace.parent:
            if str(document_workspace) in workspaces:
                return str(document_workspace)
            document_workspace = document_workspace.parent

    return None


def _get_settings_by_document(document: workspace.Document | None):
    if document is None or document.path is None:
        return list(WORKSPACE_SETTINGS.values())[0]

    key = _get_document_key(document)
    if key is None:
        # This is either a non-workspace file or there is no workspace.
        key = os.fspath(pathlib.Path(document.path).parent)
        return {
            "cwd": key,
            "workspaceFS": key,
            "workspace": uris.from_fs_path(key),
            **_get_global_defaults(),
        }

    return WORKSPACE_SETTINGS[str(key)]


# *****************************************************
# Internal execution APIs.
# *****************************************************
def _run_tool_on_document(
    document: workspace.Document,
    use_stdin: bool = False,
    extra_args: Optional[Sequence[str]] = None,
) -> utils.RunResult | None:
    """Runs tool on the given document.

    if use_stdin is true then contents of the document is passed to the
    tool via stdin.
    """
    if extra_args is None:
        extra_args = []
    if str(document.uri).startswith("vscode-notebook-cell"):
        # TODO: Decide on if you want to skip notebook cells.
        # Skip notebook cells
        return None

    if utils.is_stdlib_file(document.path):
        # TODO: Decide on if you want to skip standard library files.
        # Skip standard library python files.
        return None

    # deep copy here to prevent accidentally updating global settings.
    settings = copy.deepcopy(_get_settings_by_document(document))

    code_workspace = settings["workspaceFS"]
    cwd = settings["cwd"]

    use_path = False
    use_rpc = False
    if settings["path"]:
        # 'path' setting takes priority over everything.
        use_path = True
        argv = settings["path"]
    elif settings["interpreter"] and not utils.is_current_interpreter(settings["interpreter"][0]):
        # If there is a different interpreter set use JSON-RPC to the subprocess
        # running under that interpreter.
        argv = [TOOL_MODULE]
        use_rpc = True
    else:
        # if the interpreter is same as the interpreter running this
        # process then run as module.
        argv = [TOOL_MODULE]

    argv += TOOL_ARGS + settings["args"] + extra_args

    if use_stdin:
        # TODO: update these to pass the appropriate arguments to provide document contents
        # to tool via stdin.
        # For example, for pylint args for stdin looks like this:
        #     pylint --from-stdin <path>
        # Here `--from-stdin` path is used by pylint to make decisions on the file contents
        # that are being processed. Like, applying exclusion rules.
        # It should look like this when you pass it:
        #     argv += ["--from-stdin", document.path]
        # Read up on how your tool handles contents via stdin. If stdin is not supported use
        # set use_stdin to False, or provide path, what ever is appropriate for your tool.
        argv += []
    else:
        argv += [document.path]

    if use_path:
        # This mode is used when running executables.
        log_to_output(" ".join(argv))
        log_to_output(f"CWD Server: {cwd}")
        result = utils.run_path(
            argv=argv,
            use_stdin=use_stdin,
            cwd=cwd,
            source=document.source.replace("\r\n", "\n"),
        )
        if result.stderr:
            log_to_output(result.stderr)
    elif use_rpc:
        # This mode is used if the interpreter running this server is different from
        # the interpreter used for running this server.
        log_to_output(" ".join(settings["interpreter"] + ["-m"] + argv))
        log_to_output(f"CWD Linter: {cwd}")

        result = jsonrpc.run_over_json_rpc(
            workspace=code_workspace,
            interpreter=settings["interpreter"],
            module=TOOL_MODULE,
            argv=argv,
            use_stdin=use_stdin,
            cwd=cwd,
            source=document.source,
        )
        if result.exception:
            log_error(result.exception)
            result = utils.RunResult(result.stdout, result.stderr)
        elif result.stderr:
            log_to_output(result.stderr)
    else:
        # In this mode the tool is run as a module in the same process as the language server.
        log_to_output(" ".join([sys.executable, "-m"] + argv))
        log_to_output(f"CWD Linter: {cwd}")
        # This is needed to preserve sys.path, in cases where the tool modifies
        # sys.path and that might not work for this scenario next time around.
        with utils.substitute_attr(sys, "path", sys.path[:]):
            try:
                # TODO: `utils.run_module` is equivalent to running `python -m <pytool-module>`.
                # If your tool supports a programmatic API then replace the function below
                # with code for your tool. You can also use `utils.run_api` helper, which
                # handles changing working directories, managing io streams, etc.
                # Also update `_run_tool` function and `utils.run_module` in `lsp_runner.py`.
                result = utils.run_module(
                    module=TOOL_MODULE,
                    argv=argv,
                    use_stdin=use_stdin,
                    cwd=cwd,
                    source=document.source,
                )
            except Exception:
                log_error(traceback.format_exc(chain=True))
                raise
        if result.stderr:
            log_to_output(result.stderr)

    log_to_output(f"{document.uri} :\r\n{result.stdout}")
    return result


def _run_tool(extra_args: Sequence[str]) -> utils.RunResult:
    """Runs tool."""
    # deep copy here to prevent accidentally updating global settings.
    settings = copy.deepcopy(_get_settings_by_document(None))

    code_workspace = settings["workspaceFS"]
    cwd = settings["workspaceFS"]

    use_path = False
    use_rpc = False
    if len(settings["path"]) > 0:
        # 'path' setting takes priority over everything.
        use_path = True
        argv = settings["path"]
    elif len(settings["interpreter"]) > 0 and not utils.is_current_interpreter(settings["interpreter"][0]):
        # If there is a different interpreter set use JSON-RPC to the subprocess
        # running under that interpreter.
        argv = [TOOL_MODULE]
        use_rpc = True
    else:
        # if the interpreter is same as the interpreter running this
        # process then run as module.
        argv = [TOOL_MODULE]

    argv += extra_args

    if use_path:
        # This mode is used when running executables.
        log_to_output(" ".join(argv))
        log_to_output(f"CWD Server: {cwd}")
        result = utils.run_path(argv=argv, use_stdin=True, cwd=cwd)
        if result.stderr:
            log_to_output(result.stderr)
    elif use_rpc:
        # This mode is used if the interpreter running this server is different from
        # the interpreter used for running this server.
        log_to_output(" ".join(settings["interpreter"] + ["-m"] + argv))
        log_to_output(f"CWD Linter: {cwd}")
        result = jsonrpc.run_over_json_rpc(
            workspace=code_workspace,
            interpreter=settings["interpreter"],
            module=TOOL_MODULE,
            argv=argv,
            use_stdin=True,
            cwd=cwd,
        )
        if result.exception:
            log_error(result.exception)
            result = utils.RunResult(result.stdout, result.stderr)
        elif result.stderr:
            log_to_output(result.stderr)
    else:
        # In this mode the tool is run as a module in the same process as the language server.
        log_to_output(" ".join([sys.executable, "-m"] + argv))
        log_to_output(f"CWD Linter: {cwd}")
        # This is needed to preserve sys.path, in cases where the tool modifies
        # sys.path and that might not work for this scenario next time around.
        with utils.substitute_attr(sys, "path", sys.path[:]):
            try:
                # TODO: `utils.run_module` is equivalent to running `python -m <pytool-module>`.
                # If your tool supports a programmatic API then replace the function below
                # with code for your tool. You can also use `utils.run_api` helper, which
                # handles changing working directories, managing io streams, etc.
                # Also update `_run_tool_on_document` function and `utils.run_module` in `lsp_runner.py`.
                result = utils.run_module(module=TOOL_MODULE, argv=argv, use_stdin=True, cwd=cwd)
            except Exception:
                log_error(traceback.format_exc(chain=True))
                raise
        if result.stderr:
            log_to_output(result.stderr)

    log_to_output(f"\r\n{result.stdout}\r\n")
    return result


# *****************************************************
# Logging and notification.
# *****************************************************
def log_to_output(message: str, msg_type: lsp.MessageType = lsp.MessageType.Log) -> None:
    LSP_SERVER.show_message_log(message, msg_type)


def log_error(message: str) -> None:
    LSP_SERVER.show_message_log(message, lsp.MessageType.Error)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["onError", "onWarning", "always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Error)


def log_warning(message: str) -> None:
    LSP_SERVER.show_message_log(message, lsp.MessageType.Warning)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["onWarning", "always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Warning)


def log_always(message: str) -> None:
    LSP_SERVER.show_message_log(message, lsp.MessageType.Info)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Info)


# *****************************************************
# Start the server.
# *****************************************************
if __name__ == "__main__":
    LSP_SERVER.start_io()
