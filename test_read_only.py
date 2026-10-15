import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import phone_mcp as app
import install_phone_app as installer

class ReadOnlyTests(unittest.TestCase):
 def test_defaults_are_read_only(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(app,'ROOT',Path(directory)):
   self.assertTrue(app.settings()['adb_read_only']);self.assertFalse(app.settings()['adb_actions'])
 def test_exact_read_commands_permitted(self):
  for args in [['devices'],['exec-out','screencap','-p'],['shell','wm','size'],['shell','dumpsys','input']]:
   app.validate_adb_read_only(args,{'adb_read_only':True})
 def test_write_and_shell_variants_rejected_before_process(self):
  cases=[['install','-r','app.apk'],['forward','tcp:0','localabstract:test'],['shell','input','tap','10','20'],['shell','uiautomator','dump','/tmp/a.xml'],['shell','run-as x sh -c echo'],['shell','wm','size','1080x1920'],['shell','wm size; input tap 1 1'],['exec-out','screencap','-p',';','rm','file']]
  for args in cases:
   with self.subTest(args=args),patch.object(app,'settings',return_value={'adb_read_only':True}),patch.object(app.subprocess,'run') as process:
    with self.assertRaisesRegex(RuntimeError,'read-only'):app.adb_run(args)
    process.assert_not_called()
 def test_read_only_overrides_adb_actions_true(self):
  with patch.object(app,'settings',return_value={'adb_read_only':True,'adb_actions':True}),patch.object(app,'adb_run') as adb:
   with self.assertRaises(RuntimeError):app.adb_key('HOME')
   adb.assert_not_called()
 def test_ui_dump_fails_without_writing_temp_xml(self):
  with patch.object(app,'settings',return_value={'adb_read_only':True}),patch.object(app,'get_legacy_ui_snapshot') as legacy:
   with self.assertRaisesRegex(RuntimeError,'read-only'):app.phone_ui(backend='legacy')
   legacy.assert_not_called()
 def test_app_status_does_not_forward(self):
  with patch.object(app,'settings',return_value={'adb_read_only':True}),patch.object(app.companion,'call') as remote:
   self.assertFalse(app.phone_app_status()['available']);remote.assert_not_called()
 def test_install_and_pair_fail_before_device_side_effects(self):
  with patch.object(installer.bridge,'settings',return_value={'adb_read_only':True}),patch.object(installer.bridge,'device_id') as device:
   for pair_only in [False,True]:
    with self.assertRaisesRegex(RuntimeError,'Read-only'):installer.main(pair_only=pair_only)
   device.assert_not_called()

if __name__=='__main__':unittest.main()
