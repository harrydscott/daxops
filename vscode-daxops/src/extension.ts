import * as vscode from "vscode";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

let outputChannel: vscode.OutputChannel;

export function activate(context: vscode.ExtensionContext) {
  outputChannel = vscode.window.createOutputChannel("DaxOps");

  const commands: [string, string[]][] = [
    ["daxops.score", ["score", "--format", "json"]],
    ["daxops.check", ["check", "--format", "json"]],
    ["daxops.fix", ["fix"]],
    ["daxops.fixDryRun", ["fix", "--dry-run"]],
    ["daxops.report", ["report"]],
    ["daxops.watch", ["watch"]],
    ["daxops.badge", ["badge"]],
    ["daxops.baseline", ["baseline"]],
  ];

  for (const [commandId, args] of commands) {
    const disposable = vscode.commands.registerCommand(commandId, () =>
      runDaxOps(args)
    );
    context.subscriptions.push(disposable);
  }

  // Run on save if configured
  const onSave = vscode.workspace.onDidSaveTextDocument((doc) => {
    const config = vscode.workspace.getConfiguration("daxops");
    if (config.get<boolean>("runOnSave") && doc.fileName.endsWith(".tmdl")) {
      runDaxOps(["check", "--format", "json"]);
    }
  });
  context.subscriptions.push(onSave);

  outputChannel.appendLine("DaxOps extension activated");
}

export function deactivate() {
  outputChannel?.dispose();
}

async function runDaxOps(args: string[]): Promise<void> {
  const config = vscode.workspace.getConfiguration("daxops");
  const pythonPath = config.get<string>("pythonPath") || "python";
  const modelPath = config.get<string>("modelPath") || detectModelPath();

  if (!modelPath) {
    vscode.window.showErrorMessage(
      "DaxOps: No TMDL model found. Set daxops.modelPath in settings."
    );
    return;
  }

  const cmd = `${pythonPath} -m daxops ${args.join(" ")} "${modelPath}"`;
  outputChannel.appendLine(`> ${cmd}`);
  outputChannel.show(true);

  try {
    const { stdout, stderr } = await execAsync(cmd, {
      cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
    });

    if (stdout) {
      outputChannel.appendLine(stdout);
      // Try to parse JSON output and show as notification
      try {
        const data = JSON.parse(stdout);
        if (data.tier) {
          vscode.window.showInformationMessage(
            `DaxOps: Model tier is ${data.tier}`
          );
        } else if (data.summary) {
          const s = data.summary;
          vscode.window.showInformationMessage(
            `DaxOps: ${s.errors ?? 0} errors, ${s.warnings ?? 0} warnings, ${s.info ?? 0} info`
          );
        }
      } catch {
        // Not JSON, just show raw output
      }
    }
    if (stderr) {
      outputChannel.appendLine(stderr);
    }
  } catch (err: unknown) {
    const error = err as { stdout?: string; stderr?: string; message: string };
    // daxops exits 1 for findings — still show output
    if (error.stdout) {
      outputChannel.appendLine(error.stdout);
    }
    if (error.stderr) {
      outputChannel.appendLine(error.stderr);
    }
    if (!error.stdout && !error.stderr) {
      outputChannel.appendLine(`Error: ${error.message}`);
      vscode.window.showErrorMessage(`DaxOps error: ${error.message}`);
    }
  }
}

function detectModelPath(): string | undefined {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders) return undefined;
  // Return workspace root — daxops CLI auto-detects from there
  return folders[0].uri.fsPath;
}
