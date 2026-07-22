#!/usr/bin/env node
/**
 * Agentic OS Node.js Server Launcher
 * =====================================
 * Runs Agentic OS system via Node.js by spawning `launch.py` with standard I/O.
 *
 * Usage:
 *   node server.js              # Interactive CLI mode
 *   node server.js --tui        # Terminal UI mode
 *   node server.js --voice      # Voice mode (STT / TTS)
 *   node server.js --gateway    # Platform gateway
 *   node server.js --dashboard  # Web dashboard
 *   node server.js --status     # System status
 */

const { spawn, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const ROOT = __dirname;

function findPython() {
    // Check virtualenv candidates
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

    // Check system binaries
    const candidates = process.platform === 'win32' ? ['python', 'py', 'python3'] : ['python3', 'python'];
    for (const cmd of candidates) {
        try {
            execSync(`${cmd} --version`, { stdio: 'ignore' });
            return cmd;
        } catch (e) {
            // continue checking
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

function main() {
    const pythonBin = findPython();
    const launchScript = findLaunchScript();
    const args = [launchScript, ...process.argv.slice(2)];

    console.log('\x1b[36m%s\x1b[0m', '  Agentic OS — Node.js Launcher');
    console.log('\x1b[90m%s\x1b[0m', `  Python: ${pythonBin}`);
    console.log('\x1b[90m%s\x1b[0m', `  Script: ${launchScript}`);
    console.log('');

    const child = spawn(pythonBin, args, {
        cwd: ROOT,
        stdio: 'inherit',
        env: process.env,
    });

    const cleanup = () => {
        if (child && !child.killed) {
            child.kill('SIGINT');
        }
    };

    process.on('SIGINT', cleanup);
    process.on('SIGTERM', cleanup);

    child.on('error', (err) => {
        console.error('\x1b[31m%s\x1b[0m', `Failed to start Python process: ${err.message}`);
        console.error('Make sure Python 3.11+ is installed and on your PATH.');
        process.exit(1);
    });

    child.on('close', (code) => {
        process.exit(code !== null ? code : 0);
    });
}

if (require.main === module) {
    main();
}
