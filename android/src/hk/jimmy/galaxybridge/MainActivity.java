package hk.jimmy.galaxybridge;
import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.provider.Settings;
import android.widget.*;
import android.graphics.Color;

public class MainActivity extends Activity {
 private TextView state;
 private boolean enabled() {
  String services=Settings.Secure.getString(getContentResolver(),Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
  return services!=null && services.contains(getPackageName()+"/");
 }
 private void update() {
  boolean paused=getSharedPreferences("bridge",0).getBoolean("paused",true);
  state.setText("無障礙服務："+(enabled()?"已啟用":"未啟用")+"\n電腦連線："+(paused?"已暫停":"已允許")+"\n配對："+(new java.io.File(getFilesDir(),"bridge_token").exists()?"已設定":"請在電腦執行 INSTALL_PHONE_APP.cmd"));
 }
 @Override public void onCreate(Bundle b) {
  super.onCreate(b);
  LinearLayout box=new LinearLayout(this);box.setOrientation(1);box.setPadding(40,70,40,40);box.setBackgroundColor(Color.WHITE);
  ScrollView scroll=new ScrollView(this);scroll.addView(box);setContentView(scroll);
  TextView title=new TextView(this);title.setText("Galaxy Phone Bridge\nv3.0 · USB Accessibility");title.setTextSize(26);box.addView(title);
  TextView notice=new TextView(this);notice.setTextSize(17);notice.setPadding(0,30,0,25);
  notice.setText("此 App 讓已配對電腦讀取目前畫面文字、按鈕及位置，並依照你的指令點擊。\n\n當 OpenCode 使用雲端模型，讀到的 UI 內容會傳到你選用的模型供應商。App 本身沒有網絡權限，不儲存畫面紀錄，並遮蓋密碼欄位。一般畫面仍可能包含個人資料。\n\n只在你要使用手機控制時允許電腦連線。你可以隨時暫停，或停用無障礙服務。\n\n1. 電腦執行安裝腳本\n2. 手動啟用無障礙服務\n3. 返回此頁按「允許電腦連線」\n4. 返回要操作的 App");box.addView(notice);
  state=new TextView(this);state.setTextSize(18);box.addView(state);
  Button settings=new Button(this);settings.setText("開啟無障礙設定 / Accessibility settings");settings.setOnClickListener(v->startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));box.addView(settings);
  Button start=new Button(this);start.setText("允許電腦連線 / Allow computer");start.setOnClickListener(v->{getSharedPreferences("bridge",0).edit().putBoolean("paused",false).apply();update();});box.addView(start);
  Button stop=new Button(this);stop.setText("暫停電腦連線 / Pause");stop.setOnClickListener(v->{getSharedPreferences("bridge",0).edit().putBoolean("paused",true).apply();if(BridgeService.instance!=null)BridgeService.instance.clearNodes();update();});box.addView(stop);
  update();
 }
 @Override public void onResume(){super.onResume();if(state!=null)update();}
}
