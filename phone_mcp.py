"""Local stdio MCP bridge for Jimmy's ESP32-S3 v2 and ADB-connected phone."""
from __future__ import annotations
import argparse
from companion import Companion, CompanionError
import atexit
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from typing import Literal

from PIL import Image as PILImage
import serial
from serial.tools import list_ports
from mcp.server.fastmcp import FastMCP, Image
from mcp.types import TextContent, ImageContent

ROOT = Path(__file__).resolve().parent
VERSION = "3.1"
OBSERVATION_TTL = 30.0
observation_lock = threading.RLock()
ui_cache: dict = {}
image_cache: dict = {}
geometry_cache: dict = {}

mcp = FastMCP("galaxy_phone", instructions=(
    "Default mode is read-only ADB observation plus ESP32 BLE mouse input. "
    "Use compressed phone_screenshot for observation and esp32_mouse for relative input. "
    "Do not invoke installation, pairing, UI dump or ADB input in read-only mode. "
    "Only use optional Accessibility/ADB action tools on an explicitly authorized unrestricted setup. "
    "Reuse the current observation, then verify after meaningful actions. "
    "Screenshots are compressed/resized by default; use coordinate_space='image' and its screenshot_id "
    "for image coordinates, or coordinate_space='device' for original Android pixel coordinates. "
    "Never guess a scaled coordinate. ESP32 mouse input remains relative BLE HID, not an absolute tap. "
    "Stop at credential prompts. Screenshots/UI text go to the model through the MCP client."
), log_level="WARNING")


def settings() -> dict:
    path = ROOT / "bridge.json"
    cfg = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    return {"port": cfg.get("port", "COM4"), "baud": 115200,
            "adb": cfg.get("adb", "adb"), "device_serial": cfg.get("device_serial", ""),
            "adb_actions": cfg.get("adb_actions", False),
            "adb_read_only": cfg.get("adb_read_only", True),
            "ui_backend": cfg.get("ui_backend", "auto"),
            "companion_token": cfg.get("companion_token", "")}


def parse_state(line: str) -> dict:
    if not line.startswith("[STATE] "):
        raise ValueError("Expected v2 firmware [STATE] line")
    raw = dict(re.findall(r"(\w+)=([^\s]+)", line))
    names = ("linked", "encrypted", "bonded", "reportSub", "bootSub", "ready")
    if any(raw.get(k) not in {"0", "1"} for k in names):
        raise ValueError("Incomplete or invalid firmware state: " + line)
    return {**{k: raw[k] == "1" for k in names}, "protocol": raw.get("protocol", "unknown")}


class Board:
    def __init__(self):
        self.connection = None
        self.lock = threading.RLock()

    def close(self):
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def _open(self):
        if self.connection is not None and self.connection.is_open:
            return
        cfg = settings()
        port = serial.Serial(port=None, baudrate=cfg["baud"], timeout=0.15, write_timeout=2)
        # Do not assert the CH343 boot/reset handshake lines when opening COM4.
        port.dtr = False
        port.rts = False
        port.port = cfg["port"]
        try:
            port.open()
        except serial.SerialException as exc:
            raise RuntimeError(f"Cannot open {cfg['port']}. Close Arduino Serial Monitor and other apps using it. {exc}") from exc
        self.connection = port
        # Some USB drivers still cause a reset on first open. Wait once, not per command.
        time.sleep(1.8)

    def _exchange(self, command: str, prefix: str, timeout: float = 4) -> list[str]:
        self._open()
        self.connection.reset_input_buffer()
        self.connection.write((command + "\n").encode("ascii"))
        self.connection.flush()
        deadline = time.monotonic() + timeout
        lines = []
        while time.monotonic() < deadline:
            line = self.connection.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            lines.append(line)
            if line.startswith("[ERROR]"):
                raise RuntimeError("Firmware: " + line)
            if line.startswith(prefix):
                return lines
        raise RuntimeError("No firmware acknowledgement; command was NOT retried. "
                           "Check COM4, v2 firmware and phone Bluetooth. Recent output: " + " | ".join(lines[-6:]))

    def status(self) -> dict:
        with self.lock:
            lines = self._exchange("status", "[STATE] ")
            return parse_state(lines[-1])

    def action(self, command: str, count: int = 1) -> dict:
        allowed = {"left", "right", "up", "down", "click", "scrollup", "scrolldown"}
        if command not in allowed or isinstance(count, bool) or not 1 <= count <= 20:
            raise ValueError("Invalid mouse command or count (1..20)")
        if command == "click" and count != 1:
            raise ValueError("Clicks are single actions; count must be 1")
        with self.lock:
            state = self.status()
            if not state["ready"]:
                raise RuntimeError("ESP32 is not ready. Reconnect Jimmy Phone Mouse v2 on the phone. " + json.dumps(state))
            for _ in range(count):
                self._exchange(command, "[TX] ")
                time.sleep(0.08)
            return {"route": "ESP32 BLE HID", "command": command, "count": count,
                    "acknowledged": True, "note": "BLE stack accepted the report; inspect screenshot to confirm the phone result."}

board = Board()
atexit.register(board.close)


def validate_adb_read_only(args: list[str], cfg: dict):
    """Fail closed: permit only the exact observations used by this bridge."""
    if not cfg.get("adb_read_only", True): return
    permitted = (["devices"], ["exec-out", "screencap", "-p"],
                 ["shell", "wm", "size"], ["shell", "dumpsys", "input"])
    if args not in permitted:
        raise RuntimeError("ADB read-only mode blocks this command. No input or phone write was sent. "
                           "Use ESP32 BLE input. Optional App/ADB modes require administrator authorization.")


def adb_run(args: list[str], device: bool = True, timeout: int = 15, target: str = "") -> bytes:
    cfg = settings()
    validate_adb_read_only(args, cfg)
    executable = cfg["adb"]
    if not Path(executable).is_file():
        executable = shutil.which(executable)
    if not executable:
        raise RuntimeError("adb.exe not found. Run SETUP.cmd or set its absolute path in bridge.json.")
    cmd = [str(executable)]
    if device:
        cmd += ["-s", target or device_id()]
    cmd += args
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout, shell=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ADB timed out; action was not retried.") from exc
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or "ADB command failed")
    return result.stdout


companion = Companion(adb_run, settings)
atexit.register(companion.close)


def device_id() -> str:
    lines = adb_run(["devices"], device=False).decode("utf-8", errors="replace").splitlines()
    devices = {}
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[1] in {"device", "unauthorized", "offline", "recovery"}:
            devices[parts[0]] = parts[1]
    selected = settings()["device_serial"]
    if selected:
        if devices.get(selected) != "device":
            raise RuntimeError(f"Configured phone {selected!r} is not authorized/online: {devices.get(selected, 'missing')}")
        return selected
    ready = [key for key, value in devices.items() if value == "device"]
    if len(ready) != 1:
        raise RuntimeError("Connect and authorize exactly one phone, or set device_serial in bridge.json. " + json.dumps(devices))
    return ready[0]


def capture_screen(target: str = "") -> tuple[bytes, int, int]:
    data = adb_run(["exec-out", "screencap", "-p"], target=target)
    if len(data) < 33 or not data.startswith(b"\x89PNG\r\n\x1a\n") or data[12:16] != b"IHDR":
        raise RuntimeError("Phone did not return a valid PNG screenshot.")
    width, height = struct.unpack(">II", data[16:24])
    if not 1 <= width <= 16384 or not 1 <= height <= 16384 or len(data) > 30_000_000:
        raise RuntimeError("Unexpected screenshot dimensions/size")
    return data, width, height


def invalidate_observations():
    # Keep no stale actionable element IDs after our own UI-changing input.
    with observation_lock:
        ui_cache.clear()
        image_cache.clear()
        geometry_cache.clear()


def remember_geometry(width: int, height: int, target: str):
    geometry_cache.update(width=width, height=height, device=target, at=time.monotonic())


def screen_bounds() -> tuple[int, int]:
    """Never capture a PNG just to validate a tap. Reuse recent observation geometry."""
    target = device_id()
    if geometry_cache and geometry_cache.get("device") == target and time.monotonic() - geometry_cache["at"] <= OBSERVATION_TTL:
        return geometry_cache["width"], geometry_cache["height"]
    # wm size is in natural orientation. Adjust with current input orientation.
    sizes = adb_run(["shell", "wm", "size"], target=target).decode(errors="replace")
    matches = re.findall(r"(?:Physical|Override) size:\s*(\d+)x(\d+)", sizes)
    if not matches:
        raise RuntimeError("Cannot read display size. Use phone_screenshot first.")
    width, height = map(int, matches[-1])
    state = adb_run(["shell", "dumpsys", "input"], target=target).decode(errors="replace")
    orientations = re.findall(r"SurfaceOrientation:\s*([0-3])", state)
    if not orientations:
        raise RuntimeError("Cannot determine display rotation. Use phone_screenshot first.")
    if int(orientations[0]) % 2:
        width, height = height, width
    remember_geometry(width, height, target)
    return width, height


def require_image(screenshot_id: str) -> dict:
    if not screenshot_id or image_cache.get("id") != screenshot_id:
        raise ValueError("Use the screenshot_id from the latest phone_screenshot.")
    if time.monotonic() - image_cache["at"] > OBSERVATION_TTL:
        raise ValueError("Screenshot coordinates expired. Observe the phone again.")
    if device_id() != image_cache["device"]:
        raise RuntimeError("ADB device changed; observe the phone again.")
    return image_cache


def translate_point(x: int, y: int, coordinate_space: str, screenshot_id: str) -> tuple[int, int]:
    if coordinate_space == "image":
        snap = require_image(screenshot_id)
        check_point(x, y, snap["image_width"], snap["image_height"])
        dx = min(snap["width"] - 1, round(x * snap["width"] / snap["image_width"]))
        dy = min(snap["height"] - 1, round(y * snap["height"] / snap["image_height"]))
        return dx, dy
    if coordinate_space != "device":
        raise ValueError("coordinate_space must be image or device")
    width, height = screen_bounds()
    check_point(x, y, width, height)
    return x, y


def parse_ui_xml(payload: bytes) -> tuple[list[dict], int]:
    if len(payload) > 4_000_000 or b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("Unsupported UI XML payload")
    start = payload.find(b"<?xml")
    if start < 0: start = payload.find(b"<hierarchy")
    end = payload.rfind(b"</hierarchy>")
    if start < 0 or end < 0:
        raise ValueError("No UI hierarchy returned; use phone_screenshot for this screen.")
    root = ET.fromstring(payload[start:end + len(b"</hierarchy>")])
    nodes = []
    for element in root.iter("node"):
        a = element.attrib
        if a.get("visible-to-user", "true") == "false": continue
        bounds = re.fullmatch(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", a.get("bounds", ""))
        if not bounds: continue
        x1,y1,x2,y2 = map(int, bounds.groups())
        if x1 < 0 or y1 < 0 or x2 <= x1 or y2 <= y1: continue
        password = a.get("password") == "true"
        text = "[password field]" if password else a.get("text", "")
        description = "" if password else a.get("content-desc", "")
        rid = a.get("resource-id", "")
        clickable = a.get("clickable") == "true"
        if not (text or description or rid or clickable or a.get("scrollable") == "true"): continue
        nodes.append({"node_id":str(len(nodes)), "text":text[:400], "description":description[:400],
                      "resource_id":rid[:250], "class":a.get("class", "").split(".")[-1],
                      "clickable":clickable, "enabled":a.get("enabled", "true")=="true",
                      "scrollable":a.get("scrollable")=="true", "password":password,
                      "bounds":[x1,y1,x2,y2], "package":a.get("package", "")})
    rotation = int(root.attrib.get("rotation", "0"))
    return nodes, rotation


def get_legacy_ui_snapshot() -> dict:
    started = time.monotonic()
    target = device_id()
    remote = "/data/local/tmp/galaxy_ui_" + uuid.uuid4().hex + ".xml"
    # Use a private filename, then read and remove it immediately on the phone.
    try:
        adb_run(["shell", "uiautomator", "dump", "--compressed", remote], target=target, timeout=15)
        payload = adb_run(["shell", "cat " + remote + "; rc=$?; rm -f " + remote + "; exit $rc"], target=target)
    except Exception as exc:
        try: adb_run(["shell", "rm", "-f", remote], target=target, timeout=3)
        except Exception: pass
        raise RuntimeError("UI hierarchy unavailable; use phone_screenshot. " + str(exc)) from exc
    nodes, rotation = parse_ui_xml(payload)
    snapshot = {"snapshot_id":uuid.uuid4().hex[:12], "at":time.monotonic(),
                "device":target, "nodes":nodes, "rotation":rotation,
                "elapsed_ms":round((time.monotonic()-started)*1000), "route":"ADB UI hierarchy", "backend":"legacy"}
    ui_cache.clear(); ui_cache.update(snapshot)
    return snapshot


def get_ui_snapshot(backend: str = "auto") -> dict:
    if settings().get("adb_read_only", True):
        raise RuntimeError("UI backends are disabled in ADB read-only mode; use phone_screenshot and ESP32 BLE input.")
    if backend == "auto": backend = settings()["ui_backend"]
    if backend == "auto": backend = "accessibility" if companion.configured() else "legacy"
    if backend == "legacy": return get_legacy_ui_snapshot()
    if backend != "accessibility": raise ValueError("backend must be auto, accessibility or legacy")
    started=time.monotonic();target=device_id()
    try: raw=companion.call("ui",target)
    except CompanionError as exc:
        raise RuntimeError(str(exc)+" For an explicit fallback call phone_ui(backend='legacy') or phone_screenshot. No slow dump was started automatically.") from exc
    nodes=raw.get("nodes")
    if not isinstance(nodes,list) or len(nodes)>600: raise RuntimeError("Invalid App node list")
    ids=set()
    for n in nodes:
        if not isinstance(n,dict) or not isinstance(n.get("node_id"),str) or n["node_id"] in ids:
            raise RuntimeError("Invalid/duplicate App node ID")
        ids.add(n["node_id"])
        if not all(isinstance(n.get(k),str) for k in ("text","description","resource_id","class","package")):
            raise RuntimeError("Invalid App text data")
        if not all(isinstance(n.get(k),bool) for k in ("enabled","password","clickable","scrollable")):
            raise RuntimeError("Invalid App node state")
        b=n.get("bounds")
        if not isinstance(b,list) or len(b)!=4 or not all(type(v) is int for v in b) or b[2]<=b[0] or b[3]<=b[1]:
            raise RuntimeError("Invalid App node bounds")
        if n["password"]: n["text"]="[password field]"; n["description"]=""
    if not isinstance(raw.get("snapshot_id"),str) or not raw["snapshot_id"]: raise RuntimeError("Invalid App snapshot")
    snap={"snapshot_id":uuid.uuid4().hex[:12],"remote_snapshot_id":raw["snapshot_id"],
          "at":time.monotonic(),"device":target,"nodes":nodes,"rotation":raw.get("rotation",0),
          "revision":raw.get("revision"),"package":raw.get("package",""),
          "backend":"accessibility","route":"USB Accessibility App",
          "elapsed_ms":round((time.monotonic()-started)*1000),"service_ms":raw.get("elapsed_ms"),
          "source_truncated":raw.get("truncated",False)}
    ui_cache.clear();ui_cache.update(snap)
    return snap


def require_ui(snapshot_id: str) -> dict:
    if not snapshot_id or ui_cache.get("snapshot_id") != snapshot_id:
        raise ValueError("Use snapshot_id from the latest phone_ui; previous IDs expire after input.")
    if time.monotonic() - ui_cache["at"] > OBSERVATION_TTL:
        raise ValueError("UI snapshot expired; call phone_ui again.")
    if device_id() != ui_cache["device"]:
        raise RuntimeError("ADB device changed; call phone_ui again.")
    return ui_cache


def tap_ui_node(node: dict, snapshot: dict) -> dict:
    if not node["enabled"] or node["password"]:
        raise ValueError("Disabled or password nodes cannot be clicked with this tool.")
    if snapshot.get("backend")=="accessibility":
        # Never fall back to a coordinate tap after a failed/uncertain semantic action.
        try:
            return companion.call("click",snapshot["device"],snapshot_id=snapshot["remote_snapshot_id"],node_id=node["node_id"])
        finally:
            invalidate_observations()
    x1,y1,x2,y2=node["bounds"]
    x,y=(x1+x2)//2,(y1+y2)//2
    adb_run(["shell", "input", "tap", str(x), str(y)], target=snapshot["device"])
    result={"route":"ADB UI bounds", "clicked":True, "text":node["text"],
            "description":node["description"], "tap":[x,y],
            "note":"Input submitted; verify using phone_ui. No screenshot was taken."}
    invalidate_observations()
    return result


def compact_node(node: dict) -> dict:
    result={"node_id":node["node_id"],"bounds":node["bounds"]}
    for key in ("text","description","resource_id"):
        if node[key]: result[key]=node[key]
    if node["clickable"]: result["clickable"]=True
    if node["scrollable"]: result["scrollable"]=True
    if not node["enabled"]: result["enabled"]=False
    if node["password"]: result["password"]=True
    return result


@mcp.tool()
def phone_ui(query: str = "", max_nodes: int = 80, backend: Literal["auto","accessibility","legacy"] = "auto") -> dict:
    """Preferred first observation: fresh native UI text, descriptions, IDs and bounds, without an image.
    Auto uses the paired Accessibility App when configured; otherwise legacy UI Automator.
    query filters returned nodes. Pass snapshot_id plus node_id to click. App detects stale nodes/events.
    If the App is unavailable, explicitly choose backend='legacy' or phone_screenshot; no automatic slow dump.
    Legacy can take seconds. Custom-drawn/secure screens may need screenshot fallback.
    """
    if not 1 <= max_nodes <= 250 or len(query)>200: raise ValueError("max_nodes 1..250; query max 200 characters")
    with observation_lock:
        snap=get_ui_snapshot() if backend=="auto" else get_ui_snapshot(backend)
        nodes=snap["nodes"]
        if query:
            q=query.casefold()
            nodes=[n for n in nodes if any(q in n[k].casefold() for k in ("text","description","resource_id"))]
        return {"snapshot_id":snap["snapshot_id"], "rotation":snap["rotation"],
                "route":snap.get("route","ADB UI hierarchy"), "elapsed_ms":snap["elapsed_ms"],
                "backend":snap.get("backend","legacy"), "service_ms":snap.get("service_ms"),
                "revision":snap.get("revision"), "package":snap.get("package",""),
                "total_nodes":len(snap["nodes"]), "matching_nodes":len(nodes),
                "truncated":len(nodes)>max_nodes or snap.get("source_truncated",False), "nodes":[compact_node(n) for n in nodes[:max_nodes]],
                "note":"Prefer UI click tools. Use screenshot only if this does not describe the target."}


@mcp.tool()
def phone_click_node(snapshot_id: str, node_id: str) -> dict:
    """Click a recent phone_ui node. App uses semantic ACTION_CLICK and rejects stale UI;
    legacy uses ADB bounds. No extra dump or screenshot. No automatic fallback/retry on failure.
    IDs expire after any input or 30 seconds. Caller must re-observe after the action.
    """
    check_adb_actions()
    with observation_lock:
        snap=require_ui(snapshot_id)
        node=next((n for n in snap["nodes"] if n["node_id"]==node_id),None)
        if node is None: raise ValueError("Unknown node_id")
        return tap_ui_node(node,snap)


@mcp.tool()
def phone_click_text(text: str = "", resource_id: str = "", snapshot_id: str = "", exact: bool = True) -> dict:
    """Click unique native UI text/content-description or resource ID. Use the phone_ui snapshot_id
    to avoid a second hierarchy dump. Omit snapshot_id only when you want a fresh dump inside this tool.
    Ambiguous matches never click automatically; choose a returned node_id with phone_click_node.
    Uses the snapshot's Accessibility or legacy ADB route, NOT ESP32 BLE.
    """
    check_adb_actions()
    if not (text or resource_id) or len(text)>400 or len(resource_id)>250:
        raise ValueError("Provide text and/or resource_id")
    with observation_lock:
        snap=require_ui(snapshot_id) if snapshot_id else get_ui_snapshot()
        matches=[]
        for n in snap["nodes"]:
            if not n["enabled"] or n["password"]: continue
            labels=(n["text"],n["description"])
            text_match=not text or any((text.casefold()==v.casefold() if exact else text.casefold() in v.casefold()) for v in labels if v)
            if text_match and (not resource_id or n["resource_id"]==resource_id): matches.append(n)
        if len(matches)!=1:
            return {"clicked":False,"reason":"not_found" if not matches else "ambiguous",
                    "snapshot_id":snap["snapshot_id"],"matches":[compact_node(n) for n in matches[:30]],
                    "note":"No input sent. Select a node_id or observe another screen."}
        return tap_ui_node(matches[0],snap)


def check_adb_actions():
    if settings().get("adb_read_only", True) or not settings()["adb_actions"]:
        raise RuntimeError("ADB input is disabled in bridge.json; ESP32 tools remain available.")


def check_point(x: int, y: int, width: int, height: int):
    if isinstance(x, bool) or isinstance(y, bool) or not 0 <= x < width or not 0 <= y < height:
        raise ValueError(f"Coordinates must be within the original screenshot: x 0..{width-1}, y 0..{height-1}")


@mcp.tool()
def connection_info() -> dict:
    """List local COM ports and authorized ADB phones without opening/resetting ESP32."""
    info = {"bridge_version": VERSION, "configured_port": settings()["port"],
            "ports": [{"port": p.device, "description": p.description} for p in list_ports.comports()],
            "adb_input_enabled": settings()["adb_actions"] and not settings()["adb_read_only"],
            "ui_backend":settings()["ui_backend"], "phone_app_paired":companion.configured(),
            "adb_read_only":settings()["adb_read_only"]}
    try:
        info["phone_serial"] = device_id()
    except Exception as exc:
        info["adb_error"] = str(exc)
    return info


@mcp.tool()
def phone_app_status() -> dict:
    """Check the paired USB Accessibility App: enabled, paused, locked and revision. No UI content or click."""
    if settings().get("adb_read_only", True):
        return {"available":False,"adb_read_only":True,"note":"Optional App disabled; use screenshots + ESP32 BLE."}
    if not companion.configured():
        return {"paired":False,"note":"Run INSTALL_PHONE_APP.cmd; manually enable the service and Allow computer."}
    return {"paired":True,**companion.call("status",device_id())}


@mcp.tool()
def esp32_status() -> dict:
    """Read v2 firmware BLE/encryption/subscription readiness over COM4. Close Arduino Serial Monitor first."""
    return board.status()


@mcp.tool()
def esp32_mouse(command: Literal["left", "right", "up", "down", "click", "scrollup", "scrolldown"], count: int = 1) -> dict:
    """Send relative mouse input via ESP32 BLE HID. Each move is 40 HID units, NOT necessarily 40 screen pixels.
    count 1..20; click must use count=1. Cursor may be absent in screenshots. Never infer absolute coordinates.
    """
    result = board.action(command, count)
    invalidate_observations()
    return result


@mcp.tool()
def phone_screenshot(full_resolution: bool = False, max_side: int = 1280, quality: int = 65) -> list[TextContent | ImageContent]:
    """Fallback visual observation. Default: JPEG, longest edge 1280 pixels, quality 65.
    In read-only mode, use ESP32 mouse input. For resized IMAGE coordinates supply screenshot_id and coordinate_space='image'
    to adb_tap/adb_swipe. full_resolution=True returns original PNG for small text/detail. Not stored on disk.
    """
    if not 640 <= max_side <= 3120 or not 40 <= quality <= 95:
        raise ValueError("max_side 640..3120; quality 40..95")
    with observation_lock:
        started=time.monotonic()
        target=device_id()
        data,width,height=capture_screen(target)
        capture_ms=round((time.monotonic()-started)*1000)
        if full_resolution:
            encoded=data; iw,ih=width,height; fmt="png"
        else:
            with PILImage.open(io.BytesIO(data)) as source:
                if source.size!=(width,height): raise RuntimeError("Inconsistent screenshot dimensions")
                image=source.convert("RGB")
                image.thumbnail((max_side,max_side),PILImage.Resampling.LANCZOS)
                iw,ih=image.size
                out=io.BytesIO(); image.save(out,format="JPEG",quality=quality,optimize=True)
                encoded=out.getvalue(); fmt="jpeg"
        identifier=uuid.uuid4().hex[:12]
        image_cache.clear(); image_cache.update(id=identifier,at=time.monotonic(),device=target,
            width=width,height=height,image_width=iw,image_height=ih)
        remember_geometry(width,height,target)
        meta={"screenshot_id":identifier,"coordinate_space":"image", "image_width":iw,"image_height":ih,
              "device_width":width,"device_height":height,"scale_x":width/iw,"scale_y":height/ih,
              "format":fmt,"original_bytes":len(data),"returned_bytes":len(encoded),
              "capture_ms":capture_ms,"total_ms":round((time.monotonic()-started)*1000),
              "note":("Read-only mode: use ESP32 relative BLE input; image pixels are not HID units."
                      if settings()["adb_read_only"] else "Use adb_tap(x,y,coordinate_space='image',screenshot_id=...) for points on this image.")}
        return [TextContent(type="text",text=json.dumps(meta)),Image(data=encoded,format=fmt).to_image_content()]


@mcp.tool()
def adb_tap(x: int, y: int, coordinate_space: Literal["device","image"] = "device", screenshot_id: str = "") -> dict:
    """ADB coordinate tap without an extra screenshot. Prefer UI text/node tools.
    For points on a compressed screenshot use coordinate_space='image' plus its screenshot_id.
    'device' means original Android pixels. Verify with phone_ui or a screenshot afterward.
    """
    check_adb_actions()
    with observation_lock:
        dx,dy=translate_point(x,y,coordinate_space,screenshot_id)
        target=require_image(screenshot_id)["device"] if coordinate_space=="image" else device_id()
        adb_run(["shell","input","tap",str(dx),str(dy)],target=target)
        invalidate_observations()
        return {"route":"ADB","tap_device_pixels":[dx,dy],"extra_screenshots":0,"note":"Verify with phone_ui."}


@mcp.tool()
def adb_swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 400,
              coordinate_space: Literal["device","image"] = "device", screenshot_id: str = "") -> dict:
    """ADB swipe without an extra screenshot. Original device pixels by default.
    For compressed image coordinates supply coordinate_space='image' and screenshot_id. Duration 100..2000 ms.
    """
    check_adb_actions()
    if isinstance(duration_ms,bool) or not 100<=duration_ms<=2000: raise ValueError("duration_ms 100..2000")
    with observation_lock:
        a,b=translate_point(x1,y1,coordinate_space,screenshot_id)
        c,d=translate_point(x2,y2,coordinate_space,screenshot_id)
        target=require_image(screenshot_id)["device"] if coordinate_space=="image" else device_id()
        adb_run(["shell","input","swipe",str(a),str(b),str(c),str(d),str(duration_ms)],target=target)
        invalidate_observations()
        return {"route":"ADB","swipe_device_pixels":[a,b,c,d],"duration_ms":duration_ms,"extra_screenshots":0}


@mcp.tool()
def adb_key(key: Literal["HOME", "BACK", "RECENTS", "ENTER", "VOLUME_UP", "VOLUME_DOWN"]) -> dict:
    """Press a navigation key using ADB, NOT ESP32. No lock-screen bypass is provided."""
    check_adb_actions()
    mapping = {"HOME": 3, "BACK": 4, "RECENTS": 187, "ENTER": 66, "VOLUME_UP": 24, "VOLUME_DOWN": 25}
    if key not in mapping:
        raise ValueError("Unsupported navigation key")
    adb_run(["shell", "input", "keyevent", str(mapping[key])])
    invalidate_observations()
    return {"route": "ADB", "key": key}


@mcp.tool()
def adb_type_ascii(text: str) -> dict:
    """Type plain English ASCII into the focused field using ADB. Chinese/emoji are not supported here.
    Do not use for passwords. Does not press Enter or send/submit.
    """
    check_adb_actions()
    if not text or len(text) > 500 or any(ord(c) < 32 or ord(c) > 126 for c in text) or "%" in text:
        raise ValueError("Use 1..500 printable ASCII characters, excluding %. Chinese/emoji require a different input method.")
    encoded = text.replace(" ", "%s")
    # adb shell builds a remote shell command; POSIX-quote that argument explicitly.
    adb_run(["shell", "input text " + shlex.quote(encoded)])
    invalidate_observations()
    return {"route": "ADB", "characters": len(text), "submitted": False}


def doctor() -> dict:
    return connection_info()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--doctor", action="store_true")
    args = parser.parse_args()
    if args.doctor:
        print(json.dumps(doctor(), indent=2, ensure_ascii=False))
    else:
        mcp.run(transport="stdio")
