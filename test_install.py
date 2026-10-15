import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import install_phone_app as install

class InstallerTests(unittest.TestCase):
 def setUp(self):
  self.cfg_patch=patch.object(install.bridge,'settings',return_value={'adb_read_only':False})
  self.cfg_patch.start();self.addCleanup(self.cfg_patch.stop)
 def test_pairs_through_run_as_and_preserves_existing_settings(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);apk=root/'GalaxyPhoneBridge.apk';apk.write_bytes(b'test apk')
   (root/'APK_SHA256.txt').write_text(hashlib.sha256(apk.read_bytes()).hexdigest()+'  GalaxyPhoneBridge.apk')
   cfg={'adb':'C:/platform-tools/adb.exe','port':'COM4','adb_actions':False,'custom':'preserve'}
   (root/'bridge.json').write_text(json.dumps(cfg))
   def reply(args,**kwargs):return b'Success' if args[0]=='install' else b''
   stdout=io.StringIO()
   with patch.object(install,'ROOT',root),patch.object(install.bridge,'device_id',return_value='phone'),patch.object(install.bridge,'adb_run',side_effect=reply) as adb,contextlib.redirect_stdout(stdout):install.main()
   result=json.loads((root/'bridge.json').read_text())
   self.assertEqual(result['custom'],'preserve');self.assertFalse(result['adb_actions']);self.assertEqual(len(result['companion_token']),64)
   self.assertNotIn(result['companion_token'],stdout.getvalue())
   commands=[call.args[0] for call in adb.call_args_list]
   self.assertEqual(len(commands),3);self.assertIn('run-as hk.jimmy.galaxybridge',commands[2][1])
   self.assertFalse(any('settings put' in str(command) for command in commands))
 def test_pair_only_never_installs_or_launches(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'bridge.json').write_text(json.dumps({'port':'COM4','custom':'preserve'}))
   with patch.object(install,'ROOT',root),patch.object(install.bridge,'device_id',return_value='phone'),patch.object(install.bridge,'adb_run',return_value=b'') as adb,contextlib.redirect_stdout(io.StringIO()):install.main(pair_only=True)
   self.assertEqual(adb.call_count,1);self.assertIn('run-as hk.jimmy.galaxybridge',adb.call_args.args[0][1])
   cfg=json.loads((root/'bridge.json').read_text());self.assertEqual(len(cfg['companion_token']),64);self.assertEqual(cfg['custom'],'preserve')
 def test_denied_pair_only_does_not_claim_or_save_pairing(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);path=root/'bridge.json';original=json.dumps({'port':'COM4'});path.write_text(original)
   with patch.object(install,'ROOT',root),patch.object(install.bridge,'device_id',return_value='phone'),patch.object(install.bridge,'adb_run',side_effect=RuntimeError('blocked by policy')),contextlib.redirect_stdout(io.StringIO()):
    with self.assertRaisesRegex(RuntimeError,'blocked by policy'):install.main(pair_only=True)
   self.assertEqual(path.read_text(),original)
 def test_apk_tamper_prevents_install(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);(root/'GalaxyPhoneBridge.apk').write_bytes(b'tampered');(root/'APK_SHA256.txt').write_text('a'*64)
   with patch.object(install,'ROOT',root),patch.object(install.bridge,'device_id',return_value='phone'),patch.object(install.bridge,'adb_run') as adb:
    with self.assertRaisesRegex(RuntimeError,'hash mismatch'):install.main()
    adb.assert_not_called()

if __name__=='__main__':unittest.main()
