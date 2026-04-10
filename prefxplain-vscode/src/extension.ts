import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";

let currentPanel: vscode.WebviewPanel | undefined;
let currentWatcher: vscode.FileSystemWatcher | undefined;
let currentHtmlPath: string | undefined;

function disposeWatcher(): void {
  if (currentWatcher) {
    currentWatcher.dispose();
    currentWatcher = undefined;
  }
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => {
    switch (char) {
      case "&":
        return "&amp;";
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case '"':
        return "&quot;";
      case "'":
        return "&#39;";
      default:
        return char;
    }
  });
}

function renderStatusHtml(title: string, message: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>${escapeHtml(title)}</title>
  <style>
    body {
      margin: 0;
      padding: 24px;
      font-family: var(--vscode-font-family);
      color: var(--vscode-foreground);
      background: var(--vscode-editor-background);
    }
    h1 { margin: 0 0 12px; font-size: 1.1rem; font-weight: 600; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word;
          font-family: var(--vscode-editor-font-family, var(--vscode-font-family)); }
  </style>
</head>
<body>
  <h1>${escapeHtml(title)}</h1>
  <pre>${escapeHtml(message)}</pre>
</body>
</html>`;
}

function injectBaseTag(rawHtml: string, baseHref: string): string {
  const baseTag = `<base href="${baseHref}">`;

  if (/<base\b[^>]*>/i.test(rawHtml)) {
    return rawHtml.replace(/<base\b[^>]*>/i, baseTag);
  }
  if (/<head\b[^>]*>/i.test(rawHtml)) {
    return rawHtml.replace(/<head\b[^>]*>/i, (match) => `${match}${baseTag}`);
  }
  if (/<html\b[^>]*>/i.test(rawHtml)) {
    return rawHtml.replace(
      /<html\b[^>]*>/i,
      (match) => `${match}<head>${baseTag}</head>`
    );
  }
  return `<head>${baseTag}</head>${rawHtml}`;
}

function createPanel(htmlPath: string): vscode.WebviewPanel {
  const panel = vscode.window.createWebviewPanel(
    "prefxplain.preview",
    "PrefXplain",
    vscode.ViewColumn.Active,
    {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.file(path.dirname(htmlPath))],
    }
  );

  panel.onDidDispose(() => {
    currentPanel = undefined;
    currentHtmlPath = undefined;
    disposeWatcher();
  });

  return panel;
}

function loadHtml(panel: vscode.WebviewPanel, htmlPath: string): void {
  try {
    const raw = fs.readFileSync(htmlPath, "utf-8");
    const baseHref = `${panel.webview
      .asWebviewUri(vscode.Uri.file(path.dirname(htmlPath)))
      .toString()}/`;

    panel.webview.html = injectBaseTag(raw, baseHref);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    panel.webview.html = renderStatusHtml(
      "PrefXplain",
      `Unable to load preview from:\n${htmlPath}\n\n${message}`
    );
  }
}

function showDeletedState(panel: vscode.WebviewPanel, htmlPath: string): void {
  panel.webview.html = renderStatusHtml(
    "PrefXplain",
    `File deleted:\n${htmlPath}\n\nWaiting for it to be recreated...`
  );
}

function setupWatcher(htmlPath: string): void {
  disposeWatcher();

  const pattern = new vscode.RelativePattern(
    path.dirname(htmlPath),
    path.basename(htmlPath)
  );

  currentWatcher = vscode.workspace.createFileSystemWatcher(pattern);

  const reload = (): void => {
    if (!currentPanel) return;
    if (!fs.existsSync(htmlPath)) {
      showDeletedState(currentPanel, htmlPath);
      return;
    }
    loadHtml(currentPanel, htmlPath);
  };

  currentWatcher.onDidChange(reload);
  currentWatcher.onDidCreate(reload);
  currentWatcher.onDidDelete(() => {
    if (currentPanel) showDeletedState(currentPanel, htmlPath);
  });
}

function openPreview(htmlPath: string): void {
  const normalizedPath = path.resolve(htmlPath);

  if (!fs.existsSync(normalizedPath)) {
    vscode.window.showErrorMessage(
      `PrefXplain: file not found: ${normalizedPath}`
    );
    return;
  }

  const nextDir = path.dirname(normalizedPath);
  const currentDir = currentHtmlPath
    ? path.dirname(currentHtmlPath)
    : undefined;

  // If directory changed, recreate panel (localResourceRoots needs updating)
  if (!currentPanel || currentDir !== nextDir) {
    if (currentPanel) currentPanel.dispose();
    currentPanel = createPanel(normalizedPath);
  } else {
    currentPanel.reveal(vscode.ViewColumn.Active);
  }

  currentHtmlPath = normalizedPath;
  loadHtml(currentPanel, normalizedPath);
  setupWatcher(normalizedPath);
}

function toHtmlPath(input?: string | vscode.Uri): string | undefined {
  if (!input) return undefined;
  return typeof input === "string" ? input : input.fsPath;
}

export function activate(context: vscode.ExtensionContext): void {
  // Cleanup on deactivation
  context.subscriptions.push({
    dispose: () => {
      disposeWatcher();
      if (currentPanel) currentPanel.dispose();
    },
  });

  // Command: prefxplain.preview
  context.subscriptions.push(
    vscode.commands.registerCommand(
      "prefxplain.preview",
      (input?: string | vscode.Uri) => {
        let htmlPath = toHtmlPath(input);

        if (!htmlPath) {
          const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
          if (workspaceFolder) {
            htmlPath = path.join(workspaceFolder.uri.fsPath, "prefxplain.html");
          }
        }

        if (!htmlPath) {
          vscode.window.showErrorMessage(
            "PrefXplain: no path provided and no workspace folder open."
          );
          return;
        }

        openPreview(htmlPath);
      }
    )
  );

  // URI handler: vscode://prefxplain.prefxplain-vscode/preview?path=...
  context.subscriptions.push(
    vscode.window.registerUriHandler({
      async handleUri(uri: vscode.Uri): Promise<void> {
        const params = new URLSearchParams(uri.query);
        const htmlPath = params.get("path");

        if (!htmlPath) {
          vscode.window.showErrorMessage(
            'PrefXplain: missing "path" query parameter in URI.'
          );
          return;
        }

        openPreview(htmlPath);
      },
    })
  );
}
