import re
from typing import List
from urllib.parse import unquote, urlparse
from pygls.server import LanguageServer
from lsprotocol import types as lsp
import logging


## Server setup
class DSDLanguageServer(LanguageServer):
    def __init__(self, *args):
        super().__init__(*args)

logging.basicConfig(filename='dsd.log', filemode='w', level=logging.DEBUG)

dsd_server = DSDLanguageServer("DSD Language Server", "v0.0.1")


def start(args) -> None:
    if args.tcp:
        print(f"Server starting on {args.host}:{args.port}")
        dsd_server.start_tcp(args.host, args.port)
    elif args.ws:
        dsd_server.start_ws(args.host, args.port)
    else:
        dsd_server.start_io()


## Features

@dsd_server.feature(lsp.TEXT_DOCUMENT_DEFINITION)
def goto_definition(params: lsp.TextDocumentPositionParams) -> lsp.Location:
    lines = get_file_contents(params.text_document.uri)
    position = params.position
    line = lines[position.line]
    word, range = find_word(line, position.character)
    logging.info(f"word: {word}, range: {range}")
    if range[0] < 1 or line[range[0] - 1] != "#": # Only find references for subtrees
        return None
    if len(word.strip()) < 1:
        return None
    for line_index, line in enumerate(lines):
        found_index = line.find(f"#{word}")
        if found_index < 0:
            continue
        end_index = found_index + len(word)
        if end_index < len(line):
            return make_location(params.text_document.uri, line_index, found_index, end_index)

@dsd_server.feature(lsp.TEXT_DOCUMENT_REFERENCES)
def find_references(params: lsp.ReferenceParams):
    lines = get_file_contents(params.text_document.uri)
    position = params.position
    line = lines[position.line]
    word, range = find_word(line, position.character)
    if range[0] < 1:
        return None
    if not line[range[0] - 1] in ["#", "@"]: # Only find references for actions and subtrees
        return None
    word = f"{line[range[0] - 1]}{word}"
    if len(word.strip()) < 1:
        return None
    found_locations = []
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

def read_file_contents(uri: str) -> List[str]:
    file_path = unquote(urlparse(uri).path)
    with open(file_path[1:]) as edited_file:
        return edited_file.read().split("\n")


def get_file_contents(uri: str) -> List[str]:
    return dsd_server.workspace.get_document(uri).lines


def find_word(line: str, position: int) -> tuple[str, int]:
    line = line.removesuffix("\n").removesuffix("\r")
    if position == len(line):
        return find_word(line, position - 1)
    if line[position] == ":":
        return find_word(line, position - 1)
    word_indices = [(ele.start(), ele.end() - 1) for ele in re.finditer(r"\w+|\d+", line)]
    for i in word_indices:
        if i[0] <= position and i[1] >= position:
            return line[i[0] : i[1] + 1], i
    return line[position], (position, position)


def find_word_from_position(file_lines: List[str], position: lsp.Position) -> tuple[str, int]:
    return find_word(file_lines[position.line], position.character)
