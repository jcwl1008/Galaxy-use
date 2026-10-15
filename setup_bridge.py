"""Create an isolated environment and a project-local OpenCode configuration."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import venv

ROOT = Path(__file__).resolve().parent

def detect_adb():
    home = Path.home()
    choices = [home/'Documents/platform-tools/adb.exe',
               home/'Downloads/platform-tools/adb.exe',
               Path(os.environ.get('LOCALAPPDATA', str(home)))/'Android/Sdk/platform-tools/adb.exe']
    found = shutil.which('adb')
    if found: choices.insert(0, Path(found))
    return next((str(p.resolve()) for p in choices if p.is_file()), '')

def main():
    if sys.version_info < (3, 10):
        raise RuntimeError('Python 3.10 or newer is required.')
    print('Galaxy Phone MCP v3.1 setup - keep the extracted folder in its final location.')
    environment = ROOT/'.venv'
    python = environment/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists(): venv.EnvBuilder(with_pip=True).create(environment)
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT/'requirements.txt')], check=True)
    path = ROOT/'bridge.json'
    cfg = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    cfg.setdefault('port', 'COM4'); cfg.setdefault('device_serial', '')
    cfg.setdefault('adb_actions', False)
    cfg.setdefault('adb_read_only', True)
    if not Path(cfg.get('adb', '')).is_file():
        cfg['adb'] = detect_adb()
    if not cfg.get('adb'):
        value = input('Paste the full path to adb.exe (no quotes needed): ').strip().strip('"')
        if not Path(value).is_file(): raise RuntimeError('adb.exe not found at that path.')
        cfg['adb'] = value
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
    opencode = ROOT/'opencode.json'
    config = json.loads(opencode.read_text(encoding='utf-8-sig')) if opencode.exists() else {'$schema':'https://opencode.ai/config.json'}
    if opencode.exists():
        shutil.copy2(opencode, ROOT/f'opencode.backup-{time.time_ns()}.json')
    config.setdefault('mcp', {})['galaxy_phone'] = {
        'type':'local', 'command':[str(python.resolve()), str((ROOT/'phone_mcp.py').resolve())],
        'enabled': True, 'timeout': 15000}
    opencode.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding='utf-8')
    print('\nSETUP COMPLETE. Close Arduino Serial Monitor, then open THIS folder in OpenCode.')
    print('Keep ESP32 UART connected on COM4, and the phone directly connected to PC with USB debugging authorized.')
    subprocess.run([str(python), str(ROOT/'phone_mcp.py'), '--doctor'], check=True)
    print('\nDefault: read-only ADB observations; ESP32 BLE mouse input. Optional App requires authorization.')
    print('\nUse an OpenRouter model supporting images AND tool calls. No API key is stored by this bridge.')

if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print('\nSETUP FAILED:', exc); sys.exit(1)
