/* -------------------------------------------------------------------------
 * Original work Copyright (c) Microsoft Corporation. All rights reserved.
 * Original work licensed under the MIT License.
 * See ThirdPartyNotices.txt in the project root for license information.
 * All modifications Copyright (c) Open Law Library. All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License")
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http: // www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * ----------------------------------------------------------------------- */
"use strict";

import * as net from "net";
import * as path from "path";
import * as vscode from "vscode";
import * as semver from "semver";

import { PythonExtension } from "@vscode/python-extension";
import { LanguageClient, LanguageClientOptions, ServerOptions, State } from "vscode-languageclient/node";

const MIN_PYTHON = semver.parse("3.11.1")!

let client: LanguageClient | undefined;
let clientStarting = false
let python: PythonExtension;
let logger: vscode.LogOutputChannel

/**
 * This is the main entry point.
 * Called when vscode first activates the extension
 */
export async function activate(context: vscode.ExtensionContext) {
    logger = vscode.window.createOutputChannel('DSD', { log: true })
    logger.info("Extension activated.")

    await getPythonExtension();
    if (!python) {
        return
    }

    // Restart language server command
    context.subscriptions.push(
        vscode.commands.registerCommand("dsd.server.restart", async () => {
            logger.info('restarting server...')
            await startLangServer()
        })
    )

    // Execute command... command
    context.subscriptions.push(
        vscode.commands.registerCommand("dsd.server.executeCommand", async () => {
            await executeServerCommand()
        })
    )

    // Restart the language server if the user switches Python envs...
    context.subscriptions.push(
        python.environments.onDidChangeActiveEnvironmentPath(async () => {
            logger.info('python env modified, restarting server...')
            await startLangServer()
        })
    )

    // ... or if they change a relevant config option
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration(async (event) => {
            if (event.affectsConfiguration("dsd.server") || event.affectsConfiguration("dsd.client")) {
                logger.info('config modified, restarting server...')
                await startLangServer()
            }
        })
    )

    // Start the language server once the user opens the first text document...
    context.subscriptions.push(
        vscode.workspace.onDidOpenTextDocument(
            async () => {
                if (!client) {
                    await startLangServer()
                }
            }
        )
    )

    // ...or notebook.
    context.subscriptions.push(
        vscode.workspace.onDidOpenNotebookDocument(
            async () => {
                if (!client) {
                    await startLangServer()
                }
            }
        )
    )

    // Restart the server if the user modifies it.
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument(async (document: vscode.TextDocument) => {
            const expectedUri = vscode.Uri.file(path.join(getCwd(), getServerPath()))

            if (expectedUri.toString() === document.uri.toString()) {
                logger.info('server modified, restarting...')
                await startLangServer()
            }
        })
    )
}

export function deactivate(): Thenable<void> {
    return stopLangServer()
}

async function startLangServer() {
    await startLangServerIO()
}

/**
 * Start (or restart) the language server.
 *
 * @param command The executable to run
 * @param args Arguments to pass to the executable
 * @param cwd The working directory in which to run the executable
 * @returns
 */
async function startLangServerIO(usePackage: boolean = true) {

    // Don't interfere if we are already in the process of launching the server.
    if (clientStarting) {
        return
    }

    clientStarting = true
    if (client) {
        await stopLangServer()
    }

    const pythonPath = await getPythonPath()
    if (!pythonPath) {
        clientStarting = false
        return
    }
    
    const serverOptions = getIOServerOptions(pythonPath, usePackage)

    client = new LanguageClient('dsd', serverOptions, getClientOptions());
    try {
        await client.start()
        clientStarting = false
    } catch (err) {
        clientStarting = false
        logger.error(`Unable to start server: ${err}`)
    }
}

function getIOServerOptions(pythonPath, usePackage: boolean): ServerOptions {
    if (usePackage) {
        const serverOptions: ServerOptions = {
            command: "dsd-ls",
        };
        return serverOptions
    } else {
        const cwd = getCwd()
        const serverPath = getServerPath()

        logger.info(`cwd: '${cwd}'`)
        logger.info(`server: '${serverPath}'`)

        const serverOptions: ServerOptions = {
            command: pythonPath,
            args: [serverPath],
            options: { cwd },
        };
        return serverOptions
    }
}

async function stopLangServer(): Promise<void> {
    if (!client) {
        return
    }

    if (client.state === State.Running) {
        await client.stop()
    }

    client.dispose()
    client = undefined
}

function getClientOptions(): LanguageClientOptions {
    const config = vscode.workspace.getConfiguration('dsd.client')
    const options = {
        documentSelector: config.get<any>('documentSelector'),
        outputChannel: logger,
        connectionOptions: {
            maxRestartCount: 0 // don't restart on server failure.
        },
    };
    logger.info(`client options: ${JSON.stringify(options, undefined, 2)}`)
    return options
}

function startLangServerTCP(addr: number = 8085): LanguageClient {
    const serverOptions: ServerOptions = () => {
        return new Promise((resolve /*, reject */) => {
            const clientSocket = new net.Socket();
            clientSocket.connect(addr, "127.0.0.1", () => {
                resolve({
                    reader: clientSocket,
                    writer: clientSocket,
                });
            });
        });
    };

    logger.info(`Starting server on port ${addr}`)

    return new LanguageClient(
        `tcp lang server (port ${addr})`,
        serverOptions,
        getClientOptions()
    );
}

/**
 * Execute a command provided by the language server.
 */
async function executeServerCommand() {
    if (!client || client.state !== State.Running) {
        await vscode.window.showErrorMessage("There is no language server running.")
        return
    }

    const knownCommands = client.initializeResult?.capabilities.executeCommandProvider?.commands
    if (!knownCommands || knownCommands.length === 0) {
        const info = client.initializeResult?.serverInfo
        const name = info?.name || "Server"
        const version = info?.version || ""

        await vscode.window.showInformationMessage(`${name} ${version} does not implement any commands.`)
        return
    }

    const commandName = await vscode.window.showQuickPick(knownCommands, { canPickMany: false })
    if (!commandName) {
        return
    }
    logger.info(`executing command: '${commandName}'`)

    const result = await vscode.commands.executeCommand(commandName /* if your command accepts arguments you can pass them here */)
    logger.info(`${commandName} result: ${JSON.stringify(result, undefined, 2)}`)
}

/**
 * If the user has explicitly provided a src directory use that.
 * Otherwise, fallback to the examples/servers directory.
 *
 * @returns The working directory from which to launch the server
 */
function getCwd(): string {
    const serverDir = path.resolve(
        path.join(__dirname, "..", "language_server", "dsd_language_server")
    )
    return serverDir
}

/**
 *
 * @returns The python script to launch the server with
 */
function getServerPath(): string {
    // const config = vscode.workspace.getConfiguration("dsd.server")
    const server = "__main__.py"
    return server
}

/**
 * This uses the official python extension to grab the user's currently
 * configured environment.
 *
 * @returns The python interpreter to use to launch the server
 */
async function getPythonPath(): Promise<string | undefined> {
    if (!python) {
        return
    }

    // Use whichever python interpreter the user has configured.
    const activeEnvPath = python.environments.getActiveEnvironmentPath()
    logger.info(`Using environment: ${activeEnvPath.id}: ${activeEnvPath.path}`)

    const activeEnv = await python.environments.resolveEnvironment(activeEnvPath)
    if (!activeEnv) {
        logger.error(`Unable to resolve envrionment: ${activeEnvPath}`)
        return
    }

    const v = activeEnv.version
    if (!v) {
        logger.error(`Unable to get environment version from: ${activeEnvPath}`)
        return
    }
    const pythonVersion = semver.parse(`${v.major}.${v.minor}.${v.micro}`)
    if (pythonVersion == null) {
        logger.error(`Unable to parse Python version: ${v.major}.${v.minor}.${v.micro}`)
        return
    }

    // Check to see if the environment satisfies the min Python version.
    if (semver.lt(pythonVersion, MIN_PYTHON)) {
        const message = [
            `Your currently configured environment provides Python v${pythonVersion} `,
            `but dsd requires v${MIN_PYTHON}.\n\nPlease choose another environment.`
        ].join('')

        const response = await vscode.window.showErrorMessage(message, "Change Environment")
        if (!response) {
            return
        } else {
            await vscode.commands.executeCommand('python.setInterpreter')
            return
        }
    }

    const pythonUri = activeEnv.executable.uri
    if (!pythonUri) {
        logger.error(`URI of Python executable is undefined!`)
        return
    }

    return pythonUri.fsPath
}

async function getPythonExtension() {
    try {
        python = await PythonExtension.api();
    } catch (err) {
        logger.error(`Unable to load python extension: ${err}`)
    }
}