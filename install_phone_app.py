"""Install the USB-only companion and pair through authorized ADB run-as.
Does not enable Accessibility or change Android security settings.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import shlex
import sys
import phone_mcp as bridge

ROOT=Path(__file__).resolve().parent
PACKAGE='hk.jimmy.galaxybridge'

def main(pair_only=False):
    if bridge.settings().get('adb_read_only', True):
        raise RuntimeError('Read-only mode: installation/pairing is disabled. Ask your administrator for authorization; use screenshots + ESP32 instead.')
    target=bridge.device_id()
    if pair_only:
        print('Pairing the already installed App on:',target)
        print('No install/update command will be sent. Open Galaxy Phone Bridge on the phone first.')
    else:
        apk=ROOT/'GalaxyPhoneBridge.apk'
        expected=(ROOT/'APK_SHA256.txt').read_text(encoding='ascii').split()[0]
        if hashlib.sha256(apk.read_bytes()).hexdigest()!=expected:
            raise RuntimeError('APK hash mismatch. Extract the complete ZIP again.')
        print('Installing Galaxy Phone Bridge v3 on the selected phone:',target)
        reply=bridge.adb_run(['install','-r',str(apk)],target=target,timeout=90).decode(errors='replace')
        print(reply.strip())
        if 'Success' not in reply:raise RuntimeError('Android did not report installation success.')
        # Launch for app-private data directory and show the disclosure/control screen.
        bridge.adb_run(['shell','am','start','-n',PACKAGE+'/.MainActivity'],target=target)
    path=ROOT/'bridge.json'
    cfg=json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    existing=cfg.get('companion_token','')
    token=existing if len(existing)==64 and all(c in '0123456789abcdef' for c in existing) else secrets.token_hex(32)
    # Token is private to the app. The debug build permits provisioning by the authorized ADB shell.
    # All shell data here is fixed or validated hex; no UI text or arbitrary user paths are interpolated.
    script='mkdir -p files && umask 077 && printf %s '+token+' > files/bridge_token'
    bridge.adb_run(['shell','run-as '+PACKAGE+' sh -c '+shlex.quote(script)],target=target)
    cfg['device_serial']=target;cfg['companion_token']=token;cfg['ui_backend']='auto'
    path.write_text(json.dumps(cfg,indent=2,ensure_ascii=False),encoding='utf-8')
    print('\nPAIRED. Token is stored privately; do not share bridge.json.')
    print('On phone: Accessibility settings > Installed apps > Galaxy Phone Bridge > Enable.')
    print('Then return to Galaxy Phone Bridge and tap Allow computer.')
    print('Return to your target app. Restart OpenCode MCP and call phone_app_status, then phone_ui.')
    print('No Accessibility or security settings were changed automatically.')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--pair-only',action='store_true',help='Pair a manually installed App without install/update or launching it')
    args=parser.parse_args()
    try:main(pair_only=args.pair_only)
    except Exception as exc:
        print('\nPAIRING FAILED:' if args.pair_only else '\nINSTALL FAILED:',exc)
        print('If Android reports a security block, read README_TC.md. No security bypass was attempted.')
        sys.exit(1)
