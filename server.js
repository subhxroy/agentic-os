#!/usr/bin/env node
/**
 * Agentic OS — Interactive Node.js Launcher
 * ============================================
 * Launches Agentic OS surfaces: CLI, TUI, Localhost Web Dashboard, or Electron Desktop App.
 *
 * Usage:
 *   node server.js              # Interactive selection menu
 *   node server.js --dashboard  # Localhost Web Dashboard
 *   node server.js --electron   # Native Electron Desktop App
 *   node server.js --tui        # Modern Terminal UI
 *   node server.js --voice      # Voice Mode
 *   node server.js --gateway    # Platform Gateway
 *   node server.js --status     # System & API status
 */

const { spawn, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const readline = require('readline');

const ROOT = __dirname;

function findPython() {
    const venvPaths = [
        path.join(ROOT, '.venv', 'Scripts', 'python.exe'),
        path.join(ROOT, '.venv', 'bin', 'python'),
        path.join(ROOT, 'agentic-os', '.venv', 'Scripts', 'python.exe'),
        path.join(ROOT, 'agentic-os', '.venv', 'bin', 'python'),
    ];

    for (const venvPath of venvPaths) {
        if (fs.existsSync(venvPath)) {
            return venvPath;
        }
    }

    const candidates = process.platform === 'win32' ? ['python', 'py', 'python3'] : ['python3', 'python'];
    for (const cmd of candidates) {
        try {
            execSync(`${cmd} --version`, { stdio: 'ignore' });
            return cmd;
        } catch (e) {
            // keep looking
        }
    }

    return 'python';
}

function findLaunchScript() {
    const rootLaunch = path.join(ROOT, 'launch.py');
    if (fs.existsSync(rootLaunch)) {
        return rootLaunch;
    }
    const innerLaunch = path.join(ROOT, 'agentic-os', 'launch.py');
    if (fs.existsSync(innerLaunch)) {
        return innerLaunch;
    }
    return rootLaunch;
}

function findDesktopAppDir() {
    const rootDesktop = path.join(ROOT, 'apps', 'desktop');
    if (fs.existsSync(path.join(rootDesktop, 'package.json'))) {
        return rootDesktop;
    }
    const innerDesktop = path.join(ROOT, 'agentic-os', 'apps', 'desktop');
    if (fs.existsSync(path.join(innerDesktop, 'package.json'))) {
        return innerDesktop;
    }
    return null;
}

function runProcess(cmd, args, options = {}) {
    const isShellNeeded = options.useShell !== undefined ? options.useShell : (cmd === 'npm' || cmd === 'npm.cmd' || cmd === 'npx');
    
    const child = spawn(cmd, args, {
        cwd: options.cwd || ROOT,
        stdio: 'inherit',
        env: { ...process.env, ...options.env },
        shell: isShellNeeded,
    });

    const cleanup = () => {
        if (child && !child.killed) {
            child.kill('SIGINT');
        }
    };

    process.on('SIGINT', cleanup);
    process.on('SIGTERM', cleanup);

    child.on('error', (err) => {
        console.error(`\x1b[31mError launching process: ${err.message}\x1b[0m`);
        process.exit(1);
    });

    child.on('close', (code) => {
        process.exit(code !== null ? code : 0);
    });
}

function launchElectron() {
    const desktopDir = findDesktopAppDir();
    if (!desktopDir) {
        console.error('\x1b[31mDesktop App directory not found at apps/desktop.\x1b[0m');
        process.exit(1);
    }
    console.log('\x1b[36m%s\x1b[0m', '  Launching Agentic OS Electron Desktop App...');
    console.log('\x1b[90m%s\x1b[0m', `  Directory: ${desktopDir}`);
    console.log('');
    runProcess('npm', ['run', 'dev'], { cwd: desktopDir, useShell: true });
}

function launchPythonMode(flag) {
    const pythonBin = findPython();
    const launchScript = findLaunchScript();
    const args = [launchScript];
    if (flag) {
        args.push(flag);
    }
    runProcess(pythonBin, args, { useShell: false });
}

function promptSelection() {
    console.log('\x1b[36m%s\x1b[0m', '  Agentic OS — Selection Launcher');
    console.log('\x1b[90m%s\x1b[0m', '  =================================');
    console.log('');
    console.log('  Select launch mode:');
    console.log('    \x1b[32m[1]\x1b[0m Interactive CLI       (Terminal AI Agent session)');
    console.log('    \x1b[32m[2]\x1b[0m Modern TUI           (React / Ink rich terminal)');
    console.log('    \x1b[32m[3]\x1b[0m Web Dashboard        (Localhost Browser UI + API)');
    console.log('    \x1b[32m[4]\x1b[0m Electron Desktop App (Native Desktop GUI)');
    console.log('    \x1b[32m[5]\x1b[0m Voice Mode           (Push-to-talk speech-to-text & TTS)');
    console.log('    \x1b[32m[6]\x1b[0m Multi-Platform Gateway (Telegram, Discord, Slack, etc.)');
    console.log('    \x1b[32m[7]\x1b[0m System Status Check  (API keys & Obsidian vault status)');
    console.log('');

    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
    });

    rl.question('  Enter choice [1-7] (default: 1): ', (answer) => {
        rl.close();
        const choice = (answer || '1').trim();
        console.log('');

        switch (choice) {
            case '1':
                launchPythonMode(null);
                break;
            case '2':
                launchPythonMode('--tui');
                break;
            case '3':
            case 'localhost':
            case 'web':
                launchPythonMode('--dashboard');
                break;
            case '4':
            case 'electron':
            case 'desktop':
                launchElectron();
                break;
            case '5':
                launchPythonMode('--voice');
                break;
            case '6':
                launchPythonMode('--gateway');
                break;
            case '7':
                launchPythonMode('--status');
                break;
            default:
                console.log('Invalid selection, launching default CLI mode...');
                launchPythonMode(null);
                break;
        }
    });
}

function main() {
    const rawArgs = process.argv.slice(2);
    if (rawArgs.length === 0) {
        promptSelection();
        return;
    }

    const flag = rawArgs[0].toLowerCase();
    if (flag === '--electron' || flag === '--desktop') {
        launchElectron();
    } else if (flag === '--localhost' || flag === '--web') {
        launchPythonMode('--dashboard');
    } else {
        launchPythonMode(rawArgs[0]);
    }
}

if (require.main === module) {
    main();
}
