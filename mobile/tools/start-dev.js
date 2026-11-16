const { spawn } = require('node:child_process');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');

const mobileRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(mobileRoot, '..');

function loadRepoEnv() {
  const envFile = path.join(repoRoot, '.env');
  if (!require('node:fs').existsSync(envFile)) return;
  for (const raw of require('node:fs').readFileSync(envFile, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!match || process.env[match[1]] !== undefined) continue;
    const value = match[2].trim().replace(/^(['"])(.*)\1$/, '$2');
    process.env[match[1]] = value;
  }
}

loadRepoEnv();
const expoPackage = require.resolve('expo/package.json', { paths: [mobileRoot] });
const expoCli = path.join(path.dirname(expoPackage), 'bin', 'cli');
const expoArgs = ['start', '--port', '8082', ...process.argv.slice(2)];
const ports = [8765, 8766, 8767, 8000, 8001, 8002, 8003, 8088, 9000];
let modelServer = null;
let expoProcess = null;
let shuttingDown = false;

async function isVisionServer(baseUrl) {
  try {
    const health = await fetch(`${baseUrl}/api/health`, { signal: AbortSignal.timeout(900) });
    if (!health.ok) return false;
    const result = await health.json();
    return result.ok === true && result.service === 'o2-vision';
  } catch {
    return false;
  }
}

function canBindPort(port) {
  return new Promise(resolve => {
    const probe = net.createServer();
    probe.once('error', () => resolve(false));
    probe.listen(port, '0.0.0.0', () => probe.close(() => resolve(true)));
  });
}

function findEphemeralPort() {
  return new Promise(resolve => {
    const probe = net.createServer();
    probe.once('error', () => resolve(null));
    probe.listen(0, '0.0.0.0', () => {
      const address = probe.address();
      const port = address && typeof address === 'object' ? address.port : null;
      probe.close(() => resolve(port));
    });
  });
}

function localIpv4Addresses() {
  const addresses = [];
  for (const entries of Object.values(os.networkInterfaces())) {
    for (const entry of entries ?? []) {
      if (entry.family === 'IPv4' && !entry.internal && !entry.address.startsWith('169.254.')) {
        addresses.push(entry.address);
      }
    }
  }
  return addresses;
}

async function chooseServerPort() {
  const addresses = localIpv4Addresses();
  for (const port of ports) {
    const localUrl = `http://127.0.0.1:${port}`;
    if (await isVisionServer(localUrl)) {
      const lanReachable = await Promise.all(addresses.map(ip => isVisionServer(`http://${ip}:${port}`)));
      if (lanReachable.some(Boolean)) {
        console.log(`Vision server is already reachable on port ${port}; reusing it.`);
        return { port, start: false };
      }
      console.warn(`O2 server on ${port} is not reachable through a LAN address; checking another port.`);
    }
    if (await canBindPort(port)) {
      return { port, start: true };
    }
    console.warn(`Port ${port} is already in use by another service; checking another port.`);
  }
  const port = await findEphemeralPort();
  return port == null ? null : { port, start: true };
}

function startModelServer(port) {
  console.log(`Starting the vision server on 0.0.0.0:${port}…`);
  modelServer = spawn(process.env.PYTHON || 'python', [
    'vision/tools/tester_app.py', '--host', '0.0.0.0', '--port', String(port),
  ], { cwd: repoRoot, stdio: 'inherit', windowsHide: true });
  modelServer.on('error', error => {
    console.error(`Could not start Python (${error.message}). Activate the project's vision environment and retry.`);
  });
  modelServer.on('exit', code => {
    if (!shuttingDown && code !== 0) console.warn(`Vision server exited (${code ?? 'unknown status'}).`);
  });
}

async function waitForModelServer(port, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  const url = `http://127.0.0.1:${port}`;
  while (Date.now() < deadline && modelServer?.exitCode == null) {
    if (await isVisionServer(url)) {
      console.log(`O2 model server is ready at ${url}. Starting Expo.`);
      return true;
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  console.error(`The O2 model server did not become ready on port ${port}. Check the Python error above; Expo will start so you can still use the demo.`);
  return false;
}

function stopChildren() {
  if (shuttingDown) return;
  shuttingDown = true;
  if (modelServer && modelServer.exitCode == null) modelServer.kill();
  if (expoProcess && expoProcess.exitCode == null) expoProcess.kill();
}

async function main() {
  const server = await chooseServerPort();
  if (!server) {
    console.error('Could not select a model-server port. Expo will start, but model readings will stay unavailable.');
  } else {
    process.env.O2_VISION_PORT = String(server.port);
    if (server.start) {
      startModelServer(server.port);
      await waitForModelServer(server.port);
    }
  }

  expoProcess = spawn(process.execPath, [expoCli, ...expoArgs], {
    cwd: mobileRoot, stdio: 'inherit', windowsHide: true,
  });
  expoProcess.on('error', error => {
    console.error(`Could not start Expo: ${error.message}`);
    stopChildren();
    process.exitCode = 1;
  });
  expoProcess.on('exit', code => {
    stopChildren();
    process.exitCode = code ?? 0;
  });
}

process.once('SIGINT', () => { stopChildren(); process.exit(0); });
process.once('SIGTERM', () => { stopChildren(); process.exit(0); });
main().catch(error => {
  console.error(error);
  stopChildren();
  process.exitCode = 1;
});
