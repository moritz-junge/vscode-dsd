from argparse import ArgumentParser

from dsd_language_server import server

default_host = "127.0.0.1"
default_port = 8085


def add_arguments(parser: ArgumentParser):
    parser.description = "simple json server example"

    parser.add_argument("--tcp", action="store_true", help="Use TCP server")
    parser.add_argument("--ws", action="store_true", help="Use WebSocket server")
    parser.add_argument("--host", default=default_host, help="Bind to this address")
    parser.add_argument("--port", type=int, default=default_port, help="Bind to this port")


def main():
    parser = ArgumentParser()
    add_arguments(parser)
    args = parser.parse_args()
    server.start(args)


if __name__ == "__main__":
    main()
