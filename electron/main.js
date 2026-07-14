const { app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, nativeImage, Notification } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');

let mainWindow = null;
let tray = null;
let pythonProcess = null;
let isQuitting = false;

const PYTHON_PORT = 8088;
const HEALTH_URL = `http://127.0.0.1:${PYTHON_PORT}/api/developer/status`;
const DATA_DIR = app.getPath('userData');

// ============================================================
// Python backend management
// ============================================================
function startPythonBackend() {
  const phase0Dir = path.join(__dirname, '..', 'phase0');
  const pythonExe = process.env.PYTHON_PATH || 'python';
  
  console.log(`Starting Python backend from ${phase0Dir}...`);
  
  pythonProcess = spawn(pythonExe, ['server.py'], {
    cwd: phase0Dir,
    env: {
      ...process.env,
      AGENTOS_DATA_DIR: DATA_DIR,
      PORT: String(PYTHON_PORT),
      PYTHONUNBUFFERED: '1',
      ...(process.env.GEMINI_API_KEY ? { GEMINI_API_KEY: process.env.GEMINI_API_KEY } : {}),
      DEBUG: 'false',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[Python] ${data.toString().trim()}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python ERR] ${data.toString().trim()}`);
  });

  pythonProcess.on('exit', (code) => {
    console.log(`Python backend exited with code ${code}`);
    if (!isQuitting) {
      // Auto-restart after 2 seconds
      setTimeout(startPythonBackend, 2000);
    }
  });
}

function waitForBackend(callback, retries = 30) {
  http.get(HEALTH_URL, (res) => {
    if (res.statusCode === 200) {
      console.log('Python backend is ready.');
      callback(true);
    } else {
      retry();
    }
  }).on('error', () => retry());

  function retry() {
    if (retries <= 0) {
      console.error('Python backend failed to start after 30 seconds.');
      callback(false);
      return;
    }
    setTimeout(() => waitForBackend(callback, retries - 1), 1000);
  }
}

function stopPythonBackend() {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
}

// ============================================================
// Window
// ============================================================
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 900,
    height: 700,
    frame: false,
    titleBarStyle: 'hidden',
    backgroundColor: '#0a0015',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
    show: false,
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ============================================================
// Tray
// ============================================================
function createTray() {
  // Create a simple 16x16 tray icon
  const icon = nativeImage.createEmpty();
  tray = new Tray(icon);
  tray.setToolTip('AgentOS');

  const contextMenu = Menu.buildFromTemplate([
    { label: 'Show', click: () => mainWindow && mainWindow.show() },
    { label: 'Hide', click: () => mainWindow && mainWindow.hide() },
    { type: 'separator' },
    { label: 'Quit', click: () => { isQuitting = true; app.quit(); } },
  ]);

  tray.setContextMenu(contextMenu);
  tray.on('double-click', () => {
    mainWindow && mainWindow.show();
  });
}

// ============================================================
// IPC handlers (renderer → main)
// ============================================================
ipcMain.handle('get-backend-url', () => `http://127.0.0.1:${PYTHON_PORT}`);
ipcMain.handle('get-data-dir', () => DATA_DIR);

ipcMain.handle('show-notification', (event, { title, body }) => {
  if (Notification.isSupported()) {
    new Notification({ title, body }).show();
  }
});

ipcMain.handle('minimize-window', () => mainWindow && mainWindow.minimize());
ipcMain.handle('maximize-window', () => {
  if (mainWindow) {
    mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
  }
});
ipcMain.handle('close-window', () => mainWindow && mainWindow.hide());
ipcMain.handle('quit-app', () => { isQuitting = true; app.quit(); });

// ============================================================
// App lifecycle
// ============================================================
app.whenReady().then(() => {
  startPythonBackend();

  waitForBackend((ready) => {
    createWindow();
    createTray();

    // Global hotkey: Ctrl+Shift+Space to show/focus window
    globalShortcut.register('Ctrl+Shift+Space', () => {
      if (mainWindow) {
        mainWindow.show();
        mainWindow.focus();
      }
    });
  });
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  stopPythonBackend();
});

app.on('window-all-closed', () => {
  // Keep app running in tray (don't quit on all windows closed)
});
