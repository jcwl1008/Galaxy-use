"""Authenticated newline JSON over a USB ADB-forwarded Android abstract socket.
No phone TCP listener or network permission. Never retry an input operation.
"""
from __future__ import annotations
import json
import socket
import threading
import time

class CompanionError(RuntimeError):
    pass

class Companion:
    def __init__(self, adb_run, settings):
        self.adb_run=adb_run
        self.settings=settings
        self.target=''
        self.port=None
        self.lock=threading.RLock()

    def close(self):
        with self.lock:
            if self.port is not None:
                try:self.adb_run(['forward','--remove',f'tcp:{self.port}'],target=self.target,timeout=3)
                except Exception:pass
            self.port=None;self.target=''

    def configured(self):
        token=self.settings().get('companion_token','')
        return len(token)==64 and all(c in '0123456789abcdef' for c in token)

    def call(self, operation, target, **arguments):
        if not self.configured():
            raise CompanionError('Phone App is not paired. Run INSTALL_PHONE_APP.cmd, enable Accessibility, then tap Allow computer.')
        with self.lock:
            try:
                if self.target!=target:self.close()
                if self.port is None:
                    value=self.adb_run(['forward','tcp:0','localabstract:galaxy_phone_access_v3'],target=target).decode().strip()
                    port=int(value)
                    if not 1<=port<=65535:raise ValueError('Invalid ADB forwarding port')
                    self.port=port;self.target=target
                request={'op':operation,**arguments,'token':self.settings()['companion_token']}
                raw=json.dumps(request,ensure_ascii=False,separators=(',',':')).encode('utf-8')+b'\n'
                if len(raw)>16384:raise ValueError('Request too large')
                started=time.monotonic()
                with socket.create_connection(('127.0.0.1',self.port),timeout=5) as sock:
                    sock.settimeout(6)
                    sock.sendall(raw)
                    with sock.makefile('rb') as stream:payload=stream.readline(4_000_001)
                if len(payload)>4_000_000 or not payload.endswith(b'\n'):
                    raise CompanionError('Incomplete/oversized reply; input outcome may be unknown. Do not retry automatically.')
                data=json.loads(payload)
                if not isinstance(data,dict) or not isinstance(data.get('ok'),bool):raise CompanionError('Invalid phone App reply')
                if not data['ok']:raise CompanionError(str(data.get('error','Phone App request failed')))
                data['transport_ms']=round((time.monotonic()-started)*1000)
                return data
            except CompanionError:raise
            except (OSError,ValueError) as exc:
                # Rebuild forwarding on the NEXT explicit call; no request is replayed here.
                self.close()
                raise CompanionError('Phone App connection failed; no automatic retry. '
                    'If an input was requested its outcome is unknown: observe before another action. '
                    'Check USB, Accessibility and Allow computer. '+str(exc)) from exc
