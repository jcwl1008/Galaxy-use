import asyncio
import io
import time
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import phone_mcp as app

GOOD = '[STATE] linked=1 encrypted=1 bonded=1 reportSub=1 bootSub=0 protocol=report ready=1'
BAD = '[STATE] linked=0 encrypted=0 bonded=0 reportSub=0 bootSub=0 protocol=report ready=0'

class FakeSerial:
    def __init__(self, ready=True, fail_tx=False):
        self.is_open=True; self.commands=[]; self.lines=[]
        self.ready=ready; self.fail_tx=fail_tx
    def reset_input_buffer(self): self.lines=[]
    def write(self, data):
        command=data.decode().strip(); self.commands.append(command)
        self.lines=[((GOOD if self.ready else BAD) if command=='status' else
                     ('[ERROR] HID not ready.' if self.fail_tx else '[TX] '+command)).encode()+b'\n']
    def flush(self): pass
    def readline(self): return self.lines.pop(0) if self.lines else b''
    def close(self): self.is_open=False

class BridgeTests(unittest.TestCase):
    def setUp(self):
        app.invalidate_observations()
        self.cfg_patch=patch.object(app,'settings',return_value={'port':'COM4','baud':115200,'adb':'adb','device_serial':'','adb_actions':True,'adb_read_only':False,'ui_backend':'auto','companion_token':''})
        self.cfg_patch.start();self.addCleanup(self.cfg_patch.stop)
    def test_state_requires_all_flags(self):
        self.assertTrue(app.parse_state(GOOD)['ready'])
        with self.assertRaises(ValueError): app.parse_state('[STATE] linked=1 ready=1')
    def test_no_mouse_action_before_ready(self):
        board=app.Board(); fake=FakeSerial(ready=False); board.connection=fake
        with self.assertRaises(RuntimeError): board.action('click')
        self.assertEqual(fake.commands,['status'])
    def test_one_click_no_automatic_retry(self):
        board=app.Board(); fake=FakeSerial(); board.connection=fake
        with patch.object(app.time,'sleep'):
            self.assertTrue(board.action('click')['acknowledged'])
        self.assertEqual(fake.commands,['status','click'])
    def test_firmware_error_is_not_success(self):
        board=app.Board(); fake=FakeSerial(fail_tx=True); board.connection=fake
        with self.assertRaises(RuntimeError):board.action('click')
        self.assertEqual(fake.commands,['status','click'])
    def test_multi_click_rejected(self):
        with self.assertRaises(ValueError):app.Board().action('click',2)
    def test_coordinate_bounds_prevent_command(self):
        with patch.object(app,'screen_bounds',return_value=(100,200)), patch.object(app,'device_id',return_value='phone'), patch.object(app,'adb_run') as adb:
            with self.assertRaises(ValueError):app.adb_tap(100,50)
            adb.assert_not_called()
    def test_action_route_is_explicit(self):
        with patch.object(app,'screen_bounds',return_value=(100,200)), patch.object(app,'device_id',return_value='phone'), patch.object(app,'adb_run',return_value=b'') as adb:
            self.assertEqual(app.adb_tap(99,199)['route'],'ADB')
            adb.assert_called_once_with(['shell','input','tap','99','199'],target='phone')
    def test_ascii_shell_argument_quoted(self):
        import shlex
        text="hello; $(touch nope) 'x'"
        with patch.object(app,'adb_run',return_value=b'') as adb:
            result=app.adb_type_ascii(text)
            command=adb.call_args.args[0][1]
            self.assertEqual(shlex.split(command),['input','text',text.replace(' ','%s')])
            self.assertFalse(result['submitted'])
    def test_unicode_not_silently_corrupted(self):
        with patch.object(app,'adb_run') as adb:
            with self.assertRaises(ValueError):app.adb_type_ascii('你好')
            adb.assert_not_called()
    def test_multiple_devices_need_selection(self):
        with patch.object(app,'adb_run',return_value=b'List of devices attached\na\tdevice\nb\tdevice\n'):
            with self.assertRaises(RuntimeError):app.device_id()
    def test_unauthorized_phone_rejected(self):
        with patch.object(app,'adb_run',return_value=b'List of devices attached\na\tunauthorized\n'):
            with self.assertRaises(RuntimeError):app.device_id()
    def test_invalid_screen_rejected(self):
        with patch.object(app,'adb_run',return_value=b'error: device offline'):
            with self.assertRaises(RuntimeError):app.capture_screen()
    def test_dimensions_from_png_header(self):
        header=b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',1440,3120)+b'\x08\x02\x00\x00\x00'+b'\x00'*4
        with patch.object(app,'adb_run',return_value=header):
            self.assertEqual(app.capture_screen()[1:],(1440,3120))

UI_XML = b'''<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">
<node text="Settings" resource-id="app:id/settings" class="android.widget.TextView" enabled="true" clickable="true" bounds="[10,20][210,100]"/>
<node text="Send" enabled="true" clickable="true" bounds="[0,110][100,180]"/>
<node text="Send" enabled="true" clickable="true" bounds="[110,110][210,180]"/>
<node text="secret" content-desc="secret" password="true" enabled="true" bounds="[0,200][100,260]"/>
<node text="hidden" visible-to-user="false" bounds="[0,0][20,20]"/>
<node text="offscreen" bounds="[0,0][0,0]"/>
</hierarchy>'''

class FastUITests(unittest.TestCase):
    def setUp(self):
        app.invalidate_observations()
        self.cfg_patch=patch.object(app,'settings',return_value={'port':'COM4','baud':115200,'adb':'adb','device_serial':'','adb_actions':True,'adb_read_only':False,'ui_backend':'auto','companion_token':''})
        self.cfg_patch.start();self.addCleanup(self.cfg_patch.stop)
    def snapshot(self):
        nodes,rot=app.parse_ui_xml(UI_XML)
        return {'snapshot_id':'snap','nodes':nodes,'rotation':rot,'device':'phone','at':time.monotonic()}
    def test_password_redaction_and_visibility(self):
        nodes,_=app.parse_ui_xml(UI_XML)
        self.assertEqual(len(nodes),4)
        self.assertNotIn('secret',json.dumps(nodes))
    def test_xml_entity_rejected(self):
        with self.assertRaises(ValueError):app.parse_ui_xml(b'<!DOCTYPE hierarchy><hierarchy></hierarchy>')
    def test_node_click_without_screenshot_or_new_dump(self):
        app.ui_cache.update(self.snapshot())
        with patch.object(app,'device_id',return_value='phone'), patch.object(app,'adb_run',return_value=b'') as adb, patch.object(app,'capture_screen') as screen, patch.object(app,'get_ui_snapshot') as dump:
            self.assertTrue(app.phone_click_node('snap','0')['clicked'])
            adb.assert_called_once_with(['shell','input','tap','110','60'],target='phone')
            screen.assert_not_called();dump.assert_not_called()
        self.assertFalse(app.ui_cache)
    def test_ambiguous_text_never_clicks(self):
        app.ui_cache.update(self.snapshot())
        with patch.object(app,'device_id',return_value='phone'), patch.object(app,'adb_run') as adb:
            result=app.phone_click_text(text='Send',snapshot_id='snap')
            self.assertFalse(result['clicked']);self.assertEqual(result['reason'],'ambiguous')
            adb.assert_not_called()
    def test_unique_text_reuses_snapshot(self):
        app.ui_cache.update(self.snapshot())
        with patch.object(app,'device_id',return_value='phone'), patch.object(app,'adb_run',return_value=b''), patch.object(app,'get_ui_snapshot') as dump:
            self.assertTrue(app.phone_click_text(text='Settings',snapshot_id='snap')['clicked'])
            dump.assert_not_called()
    def test_expired_snapshot_rejected(self):
        snap=self.snapshot();snap['at']-=31;app.ui_cache.update(snap)
        with self.assertRaises(ValueError):app.phone_click_node('snap','0')
    def test_switched_device_rejected(self):
        app.ui_cache.update(self.snapshot())
        with patch.object(app,'device_id',return_value='another-phone'),patch.object(app,'adb_run') as adb:
            with self.assertRaises(RuntimeError):app.phone_click_node('snap','0')
            adb.assert_not_called()
    def test_image_coordinate_mapping_and_invalidation(self):
        app.image_cache.update(id='image',at=time.monotonic(),device='phone',width=1440,height=3120,image_width=720,image_height=1560)
        with patch.object(app,'device_id',return_value='phone'),patch.object(app,'adb_run',return_value=b'') as adb,patch.object(app,'capture_screen') as screen:
            result=app.adb_tap(360,780,coordinate_space='image',screenshot_id='image')
            self.assertEqual(result['tap_device_pixels'],[720,1560])
            adb.assert_called_once_with(['shell','input','tap','720','1560'],target='phone')
            screen.assert_not_called()
        self.assertFalse(app.image_cache)
    def test_unknown_image_id_rejected(self):
        with self.assertRaises(ValueError):app.adb_tap(10,10,coordinate_space='image',screenshot_id='wrong')
    def test_rotation_fallback_uses_no_image(self):
        with patch.object(app,'device_id',return_value='phone'),patch.object(app,'adb_run',side_effect=[b'Physical size: 1440x3120',b'SurfaceOrientation: 1']),patch.object(app,'capture_screen') as screen:
            self.assertEqual(app.screen_bounds(),(3120,1440));screen.assert_not_called()
    def test_ui_dump_tempfile_cleanup_and_parsing(self):
        with patch.object(app,'device_id',return_value='phone'),patch.object(app,'adb_run',side_effect=[b'UI hierarchy dumped',UI_XML]) as adb:
            snap=app.get_ui_snapshot()
            self.assertEqual(len(snap['nodes']),4)
            self.assertIn('rm -f',adb.call_args_list[1].args[0][1])

class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_screenshot_is_compressed_mcp_image(self):
        from PIL import Image
        out=io.BytesIO();Image.new('RGB',(1440,3120),'white').save(out,format='PNG')
        with patch.object(app,'capture_screen',return_value=(out.getvalue(),1440,3120)), patch.object(app,'device_id',return_value='phone'):
            result=await app.mcp.call_tool('phone_screenshot',{})
            contents=result[0] if isinstance(result,tuple) else result
            self.assertEqual([c.type for c in contents],['text','image'])
            self.assertEqual(contents[1].mimeType,'image/jpeg')
            meta=json.loads(contents[0].text)
            self.assertEqual((meta['image_width'],meta['image_height']),(591,1280))
            self.assertAlmostEqual(meta['scale_x'],1440/591)
            self.assertEqual(meta['device_width'],1440)
    async def test_stdio_handshake_and_tools(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'phone_mcp.py')])
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as client:
                await client.initialize()
                tools=await client.list_tools()
                self.assertEqual({t.name for t in tools.tools},{'connection_info','esp32_status','esp32_mouse','phone_screenshot','adb_tap','adb_swipe','adb_key','adb_type_ascii','phone_ui','phone_click_node','phone_click_text','phone_app_status'})
                status=await client.call_tool('connection_info',{})
                self.assertFalse(status.isError)
                # Startup/listing must not attempt to open a Windows COM port.
                self.assertIn('configured_port',status.content[0].text)

if __name__=='__main__':unittest.main(verbosity=2)
