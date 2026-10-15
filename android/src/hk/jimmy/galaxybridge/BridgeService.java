package hk.jimmy.galaxybridge;

import android.accessibilityservice.AccessibilityService;
import android.app.KeyguardManager;
import android.content.Context;
import android.graphics.Rect;
import android.net.LocalServerSocket;
import android.net.LocalSocket;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.util.DisplayMetrics;
import android.view.WindowManager;
import org.json.*;
import java.io.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class BridgeService extends AccessibilityService {
 static BridgeService instance;
 private volatile boolean running=false;
 private LocalServerSocket listener;
 private volatile LocalSocket active;
 private final Handler main=new Handler(Looper.getMainLooper());
 private long revision=0,snapshotRevision=-1,snapshotAt=0;
 private String snapshotId="";
 private final ArrayList<AccessibilityNodeInfo> saved=new ArrayList<>();
 private final ArrayList<String> fingerprints=new ArrayList<>();
 private static final int MAX_NODES=600;
 private long traversalDeadline;
 private int visited;

 @Override protected void onServiceConnected(){
  instance=this;
  if(running)return;
  running=true;
  new Thread(()->serve(),"galaxy-usb-bridge").start();
 }
 @Override public void onAccessibilityEvent(AccessibilityEvent event){revision++;}
 @Override public void onInterrupt(){revision++;clearNodes();}
 @Override public void onDestroy(){running=false;instance=null;try{if(listener!=null)listener.close();}catch(Exception e){}try{if(active!=null)active.close();}catch(Exception e){}clearNodes();super.onDestroy();}
 void clearNodes(){for(AccessibilityNodeInfo n:saved)n.recycle();saved.clear();fingerprints.clear();snapshotId="";}
 private static String s(CharSequence c){String v=c==null?"":c.toString();return v.length()>400?v.substring(0,400):v;}
 private boolean paused(){return getSharedPreferences("bridge",0).getBoolean("paused",true);}
 private boolean locked(){KeyguardManager k=(KeyguardManager)getSystemService(Context.KEYGUARD_SERVICE);return k!=null&&k.isKeyguardLocked();}
 private String token()throws Exception{
  File f=new File(getFilesDir(),"bridge_token");if(!f.exists()||f.length()>200)return "";
  ByteArrayOutputStream out=new ByteArrayOutputStream();try(InputStream in=new FileInputStream(f)){byte[] b=new byte[200];int n;while((n=in.read(b))!=-1)out.write(b,0,n);}return out.toString("UTF-8").trim();
 }
 private JSONObject fail(String message){JSONObject o=new JSONObject();try{o.put("ok",false);o.put("error",message);}catch(Exception e){}return o;}
 private boolean authenticated(JSONObject req)throws Exception{
  String secret=token(),given=req.optString("token","");
  return secret.length()==64&&MessageDigest.isEqual(secret.getBytes("UTF-8"),given.getBytes("UTF-8"));
 }
 private void serve(){
  try{
   listener=new LocalServerSocket("galaxy_phone_access_v3");
   while(running){
    LocalSocket socket=listener.accept();active=socket;
    try{
     socket.setSoTimeout(4000);
     InputStream in=socket.getInputStream();ByteArrayOutputStream data=new ByteArrayOutputStream();int c;
     while((c=in.read())!=-1&&c!='\n'){if(data.size()>=16384)throw new IOException("request too large");data.write(c);}
     JSONObject req=new JSONObject(data.toString("UTF-8"));
     JSONObject result;
     if(!authenticated(req))result=fail("Pairing required or invalid token");
     else{
      CountDownLatch done=new CountDownLatch(1);JSONObject[] output=new JSONObject[1];
      long deadline=SystemClock.uptimeMillis()+3000;
      Runnable job=()->{
       try{output[0]=SystemClock.uptimeMillis()>deadline?fail("Request expired; no input sent"):handle(req);}catch(Exception e){output[0]=fail(e.getMessage()==null?"Bridge error":e.getMessage());}finally{done.countDown();}
      };
      main.post(job);
      if(!done.await(3500,TimeUnit.MILLISECONDS)){main.removeCallbacks(job);result=fail("Service busy; outcome unknown; do not retry clicks automatically");}
      else result=output[0];
     }
     byte[] bytes=(result.toString()+"\n").getBytes("UTF-8");socket.getOutputStream().write(bytes);socket.getOutputStream().flush();
    }catch(Exception e){/* Never log UI content or authentication tokens. */}
    finally{try{socket.close();}catch(Exception e){}active=null;}
   }
  }catch(Exception e){running=false;}
 }
 private JSONObject handle(JSONObject req)throws Exception{
  String op=req.optString("op","");
  if(op.equals("status"))return new JSONObject().put("ok",true).put("version","3.0").put("enabled",true).put("paused",paused()).put("locked",locked()).put("revision",revision);
  if(paused())return fail("Bridge paused: open Galaxy Phone Bridge and tap Allow computer");
  if(locked())return fail("Phone locked: unlock it manually");
  if(op.equals("ui"))return snapshot();
  if(op.equals("click"))return click(req);
  return fail("Unsupported operation");
 }
 private String fingerprint(AccessibilityNodeInfo n){Rect r=new Rect();n.getBoundsInScreen(r);return n.getWindowId()+"|"+s(n.getPackageName())+"|"+s(n.getViewIdResourceName())+"|"+s(n.getClassName())+"|"+s(n.getText())+"|"+s(n.getContentDescription())+"|"+r.flattenToString()+"|"+n.isPassword()+"|"+n.isEnabled();}
 private boolean passwordContext(AccessibilityNodeInfo n){
  AccessibilityNodeInfo p=AccessibilityNodeInfo.obtain(n);
  try{for(int i=0;i<50&&p!=null;i++){if(p.isPassword())return true;AccessibilityNodeInfo next=p.getParent();p.recycle();p=next;}}finally{if(p!=null)p.recycle();}return false;
 }
 private void walk(AccessibilityNodeInfo n,JSONArray nodes,int depth,boolean secret)throws Exception{
  if(n==null)return;
  try{
   if(++visited>2000||depth>40||saved.size()>=MAX_NODES||SystemClock.uptimeMillis()>traversalDeadline)return;
   secret=secret||n.isPassword();
   Rect b=new Rect();n.getBoundsInScreen(b);
   if(n.isVisibleToUser()&&!b.isEmpty()&&(secret||n.getText()!=null||n.getContentDescription()!=null||n.getViewIdResourceName()!=null||n.isClickable()||n.isScrollable())){
    int id=saved.size();saved.add(AccessibilityNodeInfo.obtain(n));fingerprints.add(fingerprint(n));
    JSONObject o=new JSONObject().put("node_id",String.valueOf(id)).put("text",secret?"[password field]":s(n.getText())).put("description",secret?"":s(n.getContentDescription())).put("resource_id",s(n.getViewIdResourceName())).put("class",s(n.getClassName())).put("package",s(n.getPackageName())).put("enabled",n.isEnabled()).put("password",secret).put("clickable",n.isClickable()).put("scrollable",n.isScrollable()).put("bounds",new JSONArray(new int[]{b.left,b.top,b.right,b.bottom}));nodes.put(o);
   }
   for(int i=0;i<n.getChildCount();i++){if(saved.size()>=MAX_NODES||visited>2000||SystemClock.uptimeMillis()>traversalDeadline)break;walk(n.getChild(i),nodes,depth+1,secret);}
  }finally{n.recycle();}
 }
 private JSONObject snapshot()throws Exception{
  clearNodes();long start=SystemClock.uptimeMillis();
  AccessibilityNodeInfo root=getRootInActiveWindow();if(root==null)return fail("No active accessible window; use screenshot fallback");
  String pkg=s(root.getPackageName());int window=root.getWindowId();
  snapshotRevision=revision;visited=0;traversalDeadline=start+1200;
  JSONArray nodes=new JSONArray();walk(root,nodes,0,false);
  snapshotId=UUID.randomUUID().toString();snapshotAt=SystemClock.uptimeMillis();
  DisplayMetrics metrics=new DisplayMetrics();WindowManager wm=(WindowManager)getSystemService(Context.WINDOW_SERVICE);wm.getDefaultDisplay().getRealMetrics(metrics);
  return new JSONObject().put("ok",true).put("snapshot_id",snapshotId).put("revision",snapshotRevision).put("package",pkg).put("window_id",window).put("nodes",nodes).put("rotation",wm.getDefaultDisplay().getRotation()).put("width",metrics.widthPixels).put("height",metrics.heightPixels).put("elapsed_ms",SystemClock.uptimeMillis()-start).put("truncated",saved.size()>=MAX_NODES||visited>2000||SystemClock.uptimeMillis()>traversalDeadline);
 }
 private JSONObject click(JSONObject req)throws Exception{
  if(!req.optString("snapshot_id").equals(snapshotId)||snapshotId.isEmpty()||SystemClock.uptimeMillis()-snapshotAt>30000)return fail("Snapshot expired; call phone_ui again");
  if(revision!=snapshotRevision)return fail("UI changed since observation; call phone_ui again");
  int id=req.optInt("node_id",-1);if(id<0||id>=saved.size())return fail("Unknown node");
  AccessibilityNodeInfo n=saved.get(id);
  if(!n.refresh()||!n.isVisibleToUser()||!n.isEnabled()||passwordContext(n)||!fingerprint(n).equals(fingerprints.get(id)))return fail("Element changed or protected; observe again");
  AccessibilityNodeInfo root=getRootInActiveWindow();
  if(root==null)return fail("No active window");
  boolean same=root.getWindowId()==n.getWindowId()&&s(root.getPackageName()).equals(s(n.getPackageName()));root.recycle();
  if(!same)return fail("Active window changed; observe again");
  AccessibilityNodeInfo target=AccessibilityNodeInfo.obtain(n);boolean accepted=false;
  try{
   // Text labels often delegate clicks to their enclosing row. Never use an arbitrary screen tap.
   for(int i=0;i<8&&target!=null;i++){
    if(target.getWindowId()!=n.getWindowId()||!target.isEnabled()||!target.isVisibleToUser()||target.isPassword())break;
    if(target.isClickable()){accepted=target.performAction(AccessibilityNodeInfo.ACTION_CLICK);break;}
    AccessibilityNodeInfo parent=target.getParent();target.recycle();target=parent;
   }
  }finally{if(target!=null)target.recycle();clearNodes();revision++;}
  return new JSONObject().put("ok",true).put("clicked",accepted).put("route","Accessibility ACTION_CLICK").put("note",accepted?"Action accepted; verify with phone_ui":"No accessible click handler; inspect screenshot before an explicit ADB tap");
 }
}
