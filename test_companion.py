import copy
import json
import socket
import threading
import time
import unittest
from unittest.mock import patch
import phone_mcp as app
from companion import Companion, CompanionError

TOKEN='a'*64
NODE={'node_id':'0','text':'設定','description':'','resource_id':'android:id/title',
      'class':'TextView','package':'com.android.settings','enabled':True,'password':False,
      'clickable':True,'scrollable':False,'bounds':[10,20,210,100]}
PAYLOAD={'ok':True,'snapshot_id':'remote-123','revision':12,'nodes':[NODE],'rotation':0,'width':1440,'height':3120,'elapsed_ms':7}

class CompanionTests(unittest.TestCase):
 def setUp(self):
  app.invalidate_observations()
  self.cfg_patch=patch.object(app,'settings',return_value={'adb_actions':True,'adb_read_only':False,'ui_backend':'auto'})
  self.cfg_patch.start();self.addCleanup(self.cfg_patch.stop)
 def snapshot(self):
  with patch.object(app,'settings',return_value={'ui_backend':'auto','adb_read_only':False}),patch.object(app.companion,'configured',return_value=True),patch.object(app,'device_id',return_value='phone'),patch.object(app.companion,'call',return_value=copy.deepcopy(PAYLOAD)):
   return app.get_ui_snapshot()
 def test_auto_prefers_companion_and_no_legacy_dump(self):
  with patch.object(app,'settings',return_value={'ui_backend':'auto','adb_read_only':False}),patch.object(app.companion,'configured',return_value=True),patch.object(app,'device_id',return_value='phone'),patch.object(app.companion,'call',return_value=copy.deepcopy(PAYLOAD)),patch.object(app,'get_legacy_ui_snapshot') as legacy:
   out=app.phone_ui();self.assertEqual(out['route'],'USB Accessibility App');self.assertEqual(out['nodes'][0]['text'],'設定');legacy.assert_not_called()
 def test_unpaired_uses_legacy(self):
  with patch.object(app,'settings',return_value={'ui_backend':'auto','adb_read_only':False}),patch.object(app.companion,'configured',return_value=False),patch.object(app,'get_legacy_ui_snapshot',return_value={'legacy':True}) as legacy:
   self.assertEqual(app.get_ui_snapshot(),{'legacy':True});legacy.assert_called_once()
 def test_paired_failure_has_no_hidden_slow_fallback(self):
  with patch.object(app,'settings',return_value={'ui_backend':'auto','adb_read_only':False}),patch.object(app.companion,'configured',return_value=True),patch.object(app,'device_id',return_value='phone'),patch.object(app.companion,'call',side_effect=CompanionError('paused')),patch.object(app,'get_legacy_ui_snapshot') as legacy:
   with self.assertRaisesRegex(RuntimeError,'paused'):app.phone_ui()
   legacy.assert_not_called()
 def test_semantic_click_no_adb_coordinate_fallback(self):
  snap=self.snapshot()
  with patch.object(app,'device_id',return_value='phone'),patch.object(app.companion,'call',return_value={'ok':True,'clicked':True,'route':'Accessibility ACTION_CLICK'}) as remote,patch.object(app,'adb_run') as adb:
   self.assertTrue(app.phone_click_node(snap['snapshot_id'],'0')['clicked'])
   remote.assert_called_once_with('click','phone',snapshot_id='remote-123',node_id='0');adb.assert_not_called()
  self.assertFalse(app.ui_cache)
 def test_remote_stale_failure_never_replayed_and_invalidates(self):
  snap=self.snapshot()
  with patch.object(app,'device_id',return_value='phone'),patch.object(app.companion,'call',side_effect=CompanionError('UI changed')) as remote,patch.object(app,'adb_run') as adb:
   with self.assertRaisesRegex(CompanionError,'UI changed'):app.phone_click_node(snap['snapshot_id'],'0')
   self.assertEqual(remote.call_count,1);adb.assert_not_called()
  self.assertFalse(app.ui_cache)
 def test_ambiguous_app_text_does_not_call_click(self):
  snap=self.snapshot();n=copy.deepcopy(snap['nodes'][0]);n['node_id']='1';app.ui_cache['nodes'].append(n)
  with patch.object(app,'device_id',return_value='phone'),patch.object(app.companion,'call') as remote:
   self.assertEqual(app.phone_click_text('設定',snapshot_id=snap['snapshot_id'])['reason'],'ambiguous');remote.assert_not_called()
 def test_input_gate_applies_to_companion(self):
  snap=self.snapshot()
  with patch.object(app,'settings',return_value={'adb_actions':False}),patch.object(app.companion,'call') as remote:
   with self.assertRaisesRegex(RuntimeError,'disabled'):app.phone_click_node(snap['snapshot_id'],'0')
   remote.assert_not_called()
 def test_password_defense_on_pc(self):
  raw=copy.deepcopy(PAYLOAD);raw['nodes'][0].update(password=True,text='secret',description='secret')
  with patch.object(app,'settings',return_value={'ui_backend':'accessibility','adb_read_only':False}),patch.object(app,'device_id',return_value='phone'),patch.object(app.companion,'call',return_value=raw):
   snap=app.get_ui_snapshot();self.assertNotIn('secret',json.dumps(snap))
   with self.assertRaisesRegex(ValueError,'password'):app.tap_ui_node(snap['nodes'][0],snap)
 def test_invalid_remote_bounds_rejected(self):
  raw=copy.deepcopy(PAYLOAD);raw['nodes'][0]['bounds']=[0,0,0,0]
  with patch.object(app,'settings',return_value={'ui_backend':'accessibility','adb_read_only':False}),patch.object(app,'device_id',return_value='phone'),patch.object(app.companion,'call',return_value=raw):
   with self.assertRaisesRegex(RuntimeError,'bounds'):app.get_ui_snapshot()
 def test_real_socket_roundtrip_authenticated_and_forward_reused(self):
  server=socket.socket();server.bind(('127.0.0.1',0));server.listen(2);port=server.getsockname()[1];received=[]
  def worker():
   try:
    for _ in range(2):
     with server.accept()[0] as conn:
      with conn.makefile('rb') as f:request=json.loads(f.readline())
      received.append(request);conn.sendall(b'{"ok":true,"version":"3.0"}\n')
   finally:server.close()
  thread=threading.Thread(target=worker,daemon=True);thread.start()
  calls=[]
  def adb(args,**kwargs):calls.append(args);return str(port).encode()
  c=Companion(adb,lambda:{'companion_token':TOKEN})
  try:
   self.assertEqual(c.call('status','phone')['version'],'3.0');c.call('ui','phone')
   thread.join(2);self.assertFalse(thread.is_alive());self.assertEqual(len(calls),1)
   self.assertEqual(received[0]['token'],TOKEN);self.assertEqual(received[1]['op'],'ui')
  finally:c.close()
 def test_uncertain_input_not_retried(self):
  c=Companion(lambda *a,**k:b'12345',lambda:{'companion_token':TOKEN})
  with patch('companion.socket.create_connection',side_effect=ConnectionRefusedError('disconnected')) as connect:
   with self.assertRaisesRegex(CompanionError,'no automatic retry'):c.call('click','phone',snapshot_id='x',node_id='0')
   self.assertEqual(connect.call_count,1)
 def test_unpaired_status_is_actionable(self):
  with patch.object(app.companion,'configured',return_value=False):self.assertFalse(app.phone_app_status()['paired'])

if __name__=='__main__':unittest.main(verbosity=2)
