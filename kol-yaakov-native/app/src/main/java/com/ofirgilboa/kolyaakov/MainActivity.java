package com.ofirgilboa.kolyaakov;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.content.Context;
import android.widget.*;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.*;

public class MainActivity extends Activity {
    static final int BG=Color.rgb(9,13,24), PANEL=Color.rgb(17,24,42), PANEL2=Color.rgb(24,33,55);
    static final int TEXT=Color.rgb(248,249,253), MUTED=Color.rgb(167,177,202), PURPLE=Color.rgb(139,92,246);
    static final int PURPLE2=Color.rgb(196,181,253), GREEN=Color.rgb(73,216,165), AMBER=Color.rgb(245,189,104), RED=Color.rgb(255,123,141);
    static final String PREFS="kol_yaakov_native", STATE_KEY="state_v4";
    static final int RC_EXPORT=401, RC_IMPORT=402;

    LinearLayout root, content, nav;
    TextView headerTitle, headerSub;
    SharedPreferences prefs;
    AppState state;
    String view="home";
    String practiceSongId=null;
    TrainingTask task=null;
    boolean revealed=false;
    EditText answerInput=null;
    PerformanceSession performance=null;
    String pendingExport=null;
    Vibrator vibrator;

    @Override public void onCreate(Bundle b){
        super.onCreate(b);
        getWindow().setStatusBarColor(BG); getWindow().setNavigationBarColor(BG);
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        prefs=getSharedPreferences(PREFS,MODE_PRIVATE); vibrator=(Vibrator)getSystemService(VIBRATOR_SERVICE);
        state=AppState.load(prefs.getString(STATE_KEY,null));
        buildShell(); render();
    }

    int dp(int v){return Math.round(v*getResources().getDisplayMetrics().density);} int sp(int v){return v;}
    GradientDrawable bg(int color,int radius){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(radius));return d;}
    GradientDrawable stroke(int color,int radius,int strokeColor){GradientDrawable d=bg(color,radius);d.setStroke(dp(1),strokeColor);return d;}
    TextView tv(String text,int size,int color,boolean bold){TextView v=new TextView(this);v.setText(text);v.setTextSize(size);v.setTextColor(color);v.setGravity(Gravity.RIGHT);v.setTextDirection(View.TEXT_DIRECTION_RTL);v.setLineSpacing(0,1.18f); if(bold)v.setTypeface(Typeface.DEFAULT,Typeface.BOLD); return v;}
    LinearLayout vertical(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.VERTICAL);l.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);return l;}
    LinearLayout horizontal(){LinearLayout l=new LinearLayout(this);l.setOrientation(LinearLayout.HORIZONTAL);l.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);l.setGravity(Gravity.CENTER_VERTICAL);return l;}
    void pad(View v,int x,int y){v.setPadding(dp(x),dp(y),dp(x),dp(y));}
    Space gap(int h){Space s=new Space(this);s.setLayoutParams(new LinearLayout.LayoutParams(1,dp(h)));return s;}
    Button button(String text,boolean primary){Button b=new Button(this);b.setText(text);b.setTextSize(16);b.setTextColor(TEXT);b.setAllCaps(false);b.setMinHeight(dp(52));b.setGravity(Gravity.CENTER);b.setBackground(primary?bg(PURPLE,15):stroke(PANEL2,15,Color.rgb(53,63,86)));return b;}
    LinearLayout card(){LinearLayout c=vertical();c.setBackground(stroke(PANEL,22,Color.rgb(38,48,70)));pad(c,16,16);return c;}
    LinearLayout.LayoutParams mp(){return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT);}

    void buildShell(){
        root=vertical();root.setBackgroundColor(BG);root.setLayoutParams(new ViewGroup.LayoutParams(-1,-1));
        LinearLayout top=horizontal();top.setBackgroundColor(BG);pad(top,16,14); top.setMinimumHeight(dp(78));
        TextView logo=tv("🎙",28,TEXT,true);logo.setGravity(Gravity.CENTER);logo.setBackground(bg(PURPLE,15));logo.setLayoutParams(new LinearLayout.LayoutParams(dp(50),dp(50)));top.addView(logo);
        LinearLayout titles=vertical();LinearLayout.LayoutParams tp=new LinearLayout.LayoutParams(0,-2,1);tp.setMargins(dp(12),0,dp(12),0);titles.setLayoutParams(tp);
        headerSub=tv("מאמן הזיכרון לאמנים",12,PURPLE2,true);headerTitle=tv("היום",23,TEXT,true);titles.addView(headerSub);titles.addView(headerTitle);top.addView(titles);
        Button add=button("＋",false);add.setContentDescription("הוסף שיר");add.setTextSize(24);add.setLayoutParams(new LinearLayout.LayoutParams(dp(52),dp(52)));add.setOnClickListener(v->songDialog(null));top.addView(add);root.addView(top);
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setBackgroundColor(BG);content=vertical();pad(content,14,14);scroll.addView(content,new ScrollView.LayoutParams(-1,-2));root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        nav=horizontal();nav.setBackgroundColor(Color.rgb(8,12,22));pad(nav,6,6);String[][] ns={{"⌂","היום","home"},{"♫","שירים","library"},{"◎","אימון","practice"},{"↗","זיכרון","progress"},{"⚙","עוד","more"}};
        for(String[] n:ns){Button b=new Button(this);b.setAllCaps(false);b.setText(n[0]+"\n"+n[1]);b.setTextSize(12);b.setTag(n[2]);b.setTextColor(MUTED);b.setBackgroundColor(Color.TRANSPARENT);b.setMinHeight(dp(64));b.setOnClickListener(v->{view=(String)v.getTag();task=null;revealed=false;render();});nav.addView(b,new LinearLayout.LayoutParams(0,dp(66),1));}
        root.addView(nav);setContentView(root);
    }

    void setHead(String title,String sub){headerTitle.setText(title);headerSub.setText(sub);}
    void markNav(){for(int i=0;i<nav.getChildCount();i++){Button b=(Button)nav.getChildAt(i);boolean on=view.equals(b.getTag());b.setTextColor(on?PURPLE2:MUTED);b.setBackground(on?bg(Color.rgb(29,23,54),14):bg(Color.TRANSPARENT,14));}}
    void render(){content.removeAllViews();markNav();switch(view){case "library":renderLibrary();break;case "practice":renderPractice();break;case "progress":renderProgress();break;case "more":renderMore();break;case "performance":renderPerformance();break;default:renderHome();}}
    void persist(){state.updatedAt=System.currentTimeMillis();prefs.edit().putString(STATE_KEY,state.toJson().toString()).apply();}

    void renderHome(){
        setHead("היום","קול יעקב · חזרה חכמה לפני במה"); Song smart=smartSong();
        LinearLayout hero=card(); TextView badge=tv("אימון קצר שמתקדם לפי מה שאתה באמת זוכר",12,PURPLE2,true);hero.addView(badge);hero.addView(gap(8));
        hero.addView(tv(smart!=null?"השיר הבא שלך: "+smart.title:"מתחילים משיר אחד",25,TEXT,true));hero.addView(gap(7));hero.addView(tv(smart!=null?"המערכת תאתר את השורות והמעברים החלשים ותתרגל אותם לפני מה שכבר יושב טוב.":"הוסף שיר, והאפליקציה תהפוך אותו למסלול זיכרון מדורג — מקריאה ועד שליפה בלי רמז.",16,MUTED,false));hero.addView(gap(16));
        Button go=button(smart!=null?"התחל אימון חכם":"הוסף שיר ראשון",true);go.setOnClickListener(v->{if(smart==null)songDialog(null);else{practiceSongId=smart.id;task=null;view="practice";render();}});hero.addView(go,mp());content.addView(hero,mp());content.addView(gap(14));
        LinearLayout metrics=horizontal();metrics.addView(metric(avgReady()+"%","מוכנות"),new LinearLayout.LayoutParams(0,-2,1));metrics.addView(metric(totalDue()+"","לחזרה"),new LinearLayout.LayoutParams(0,-2,1));metrics.addView(metric(state.songs.size()+"","שירים"),new LinearLayout.LayoutParams(0,-2,1));content.addView(metrics,mp());
        if(smart!=null){content.addView(gap(18));TextView h=tv("המשך מומלץ",19,TEXT,true);content.addView(h);content.addView(gap(9));content.addView(songCard(smart),mp());}
    }
    LinearLayout metric(String n,String l){LinearLayout c=vertical();c.setGravity(Gravity.CENTER);pad(c,8,14);c.setBackground(stroke(PANEL,17,Color.rgb(37,47,67)));TextView a=tv(n,22,TEXT,true);a.setGravity(Gravity.CENTER);TextView b=tv(l,12,MUTED,false);b.setGravity(Gravity.CENTER);c.addView(a);c.addView(b);return c;}

    void renderLibrary(){setHead("השירים שלי","ספריית החזרות");Button add=button("＋ הוסף שיר",true);add.setOnClickListener(v->songDialog(null));content.addView(add,mp());content.addView(gap(13));if(state.songs.isEmpty()){LinearLayout e=card();e.setGravity(Gravity.CENTER);e.addView(tv("עדיין אין שירים",22,TEXT,true));e.addView(gap(7));e.addView(tv("הדבק את מילות השיר. אפשר לסמן [בית 1], [פזמון], [גשר] כדי שהאימון יבין את המבנה.",15,MUTED,false));content.addView(e,mp());return;}for(Song s:state.songs){content.addView(songCard(s),mp());content.addView(gap(10));}}
    LinearLayout songCard(Song s){LinearLayout c=card();LinearLayout top=horizontal();LinearLayout txt=vertical();txt.setLayoutParams(new LinearLayout.LayoutParams(0,-2,1));txt.addView(tv(s.title,19,TEXT,true));txt.addView(tv(s.artist.isEmpty()?"ללא שם אמן":s.artist,13,MUTED,false));top.addView(txt);TextView score=tv(readiness(s)+"%",15,PURPLE2,true);score.setGravity(Gravity.CENTER);pad(score,10,7);score.setBackground(bg(Color.rgb(33,26,57),99));top.addView(score);c.addView(top);c.addView(gap(11));ProgressBar pb=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);pb.setMax(100);pb.setProgress(readiness(s));pb.setProgressTintList(android.content.res.ColorStateList.valueOf(PURPLE));pb.setProgressBackgroundTintList(android.content.res.ColorStateList.valueOf(Color.rgb(38,46,67)));c.addView(pb,new LinearLayout.LayoutParams(-1,dp(8)));c.addView(gap(10));c.addView(tv(s.lines.size()+" שורות · "+dueCount(s)+" לחזרה",13,MUTED,false));c.addView(gap(12));LinearLayout acts=horizontal();Button train=button("אימון",true);train.setOnClickListener(v->{practiceSongId=s.id;task=null;view="practice";render();});Button stage=button("חזרת במה",false);stage.setOnClickListener(v->startPerformance(s));Button edit=button("עריכה",false);edit.setOnClickListener(v->songDialog(s));acts.addView(train,new LinearLayout.LayoutParams(0,-2,1));acts.addView(stage,new LinearLayout.LayoutParams(0,-2,1));acts.addView(edit,new LinearLayout.LayoutParams(0,-2,1));c.addView(acts);return c;}

    void renderPractice(){
        setHead("אימון חכם","שליפה פעילה · לא רק קריאה"); if(state.songs.isEmpty()){emptyPractice();return;} Song s=getSong(practiceSongId);if(s==null){s=smartSong();practiceSongId=s.id;}if(task==null)task=nextTask(s);
        LinearLayout choose=horizontal();Spinner spinner=new Spinner(this);ArrayAdapter<String> ad=new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,songTitles());spinner.setAdapter(ad);spinner.setSelection(indexOfSong(s.id));spinner.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){public void onNothingSelected(android.widget.AdapterView<?> p){}public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){Song x=state.songs.get(pos);if(!x.id.equals(practiceSongId)){practiceSongId=x.id;task=null;revealed=false;render();}}});choose.addView(spinner,new LinearLayout.LayoutParams(0,dp(50),1));content.addView(choose);content.addView(gap(10));
        if(task==null){content.addView(tv("אין שורות לתרגול.",18,TEXT,true));return;}
        LinearLayout c=card();c.addView(tv(s.title+" · "+task.section+" · שורה "+(task.index+1)+"/"+s.lines.size(),12,PURPLE2,true));c.addView(gap(8));c.addView(tv(task.prompt,21,TEXT,true));c.addView(gap(14));if(!task.cue.isEmpty()){TextView cue=tv(task.cue,19,TEXT,true);cue.setGravity(Gravity.CENTER);pad(cue,16,16);cue.setBackground(stroke(Color.rgb(25,24,46),16,Color.rgb(68,54,104)));c.addView(cue);c.addView(gap(10));}
        if(task.guided){TextView full=tv(task.expected,23,TEXT,true);full.setGravity(Gravity.CENTER);pad(full,16,19);full.setBackground(stroke(PANEL2,17,Color.rgb(53,63,86)));c.addView(full);c.addView(gap(12));Button remember=button("קראתי וזכרתי",true);remember.setOnClickListener(v->submitGuided(true));Button again=button("צריך עוד חזרה",false);again.setOnClickListener(v->submitGuided(false));c.addView(remember,mp());c.addView(gap(7));c.addView(again,mp());}else{
            answerInput=new EditText(this);answerInput.setTextColor(TEXT);answerInput.setHintTextColor(Color.rgb(111,123,151));answerInput.setHint("כתוב כאן מהזיכרון…");answerInput.setTextSize(18);answerInput.setMinHeight(dp(120));answerInput.setGravity(Gravity.TOP|Gravity.RIGHT);answerInput.setTextDirection(View.TEXT_DIRECTION_RTL);answerInput.setBackground(stroke(Color.rgb(11,16,32),16,Color.rgb(54,64,88)));pad(answerInput,14,14);c.addView(answerInput,mp());c.addView(gap(10));Button check=button("בדוק אותי",true);check.setOnClickListener(v->submitAnswer());c.addView(check,mp());Button reveal=button(revealed?"התשובה מוצגת":"הצג תשובה",false);reveal.setEnabled(!revealed);reveal.setOnClickListener(v->{revealed=true;render();});c.addView(gap(7));c.addView(reveal,mp());if(revealed){TextView sol=tv("התשובה: "+task.expected,17,AMBER,true);pad(sol,13,13);sol.setBackground(stroke(Color.rgb(42,31,23),14,Color.rgb(94,70,35)));c.addView(gap(10));c.addView(sol);}}
        content.addView(c,mp());content.addView(gap(10));Button change=button("בחר שיר אחר",false);change.setOnClickListener(v->{view="library";render();});content.addView(change,mp());
    }
    void emptyPractice(){LinearLayout e=card();e.addView(tv("אין עדיין שיר לאימון",21,TEXT,true));e.addView(tv("הוסף שיר אחד כדי להתחיל מסלול זיכרון חכם.",15,MUTED,false));Button b=button("הוסף שיר",true);b.setOnClickListener(v->songDialog(null));e.addView(gap(12));e.addView(b);content.addView(e);}
    String[] songTitles(){String[] a=new String[state.songs.size()];for(int i=0;i<a.length;i++)a[i]=state.songs.get(i).title;return a;}
    int indexOfSong(String id){for(int i=0;i<state.songs.size();i++)if(state.songs.get(i).id.equals(id))return i;return 0;}

    void submitGuided(boolean good){Song s=getSong(task.songId);Line line=s.lines.get(task.index);Progress p=s.progress(line.id);p.exposures++;p.lastSeen=System.currentTimeMillis();p.dueAt=System.currentTimeMillis()+(good?10*60*1000:60*1000);p.score=good?Math.max(p.score,.35):Math.max(p.score,.15);persist();vibrate(good);showFeedback(good?"מצוין — עכשיו ננסה להוציא את זה מהזיכרון.":"בסדר — נחזור על השורה מוקדם יותר.",good?GREEN:AMBER);}
    void submitAnswer(){Song s=getSong(task.songId);String ans=answerInput==null?"":answerInput.getText().toString();if(ans.trim().isEmpty()&&!revealed){toast("כתוב קודם מה אתה זוכר");return;}double sim=revealed?.35:similarity(ans,task.expected);Progress p=s.progress(s.lines.get(task.index).id);p.attempts++;p.lastSeen=System.currentTimeMillis();p.lastScore=sim;if(sim>=.82&&!revealed){p.successes++;p.streak++;}else{p.streak=0;p.lapses++;}p.score=p.attempts==1?sim:p.score*.64+sim*.36;p.best=Math.max(p.best,sim);long delay=sim>=.9?Math.min(7,1+p.streak/2)*86400000L:sim>=.78?4*3600000L:sim>=.6?30*60000L:5*60000L;p.dueAt=System.currentTimeMillis()+delay;if(task.transition&&task.index>0){String key=s.lines.get(task.index-1).id+">"+s.lines.get(task.index).id;Progress tr=s.transitions.get(key);if(tr==null){tr=new Progress();s.transitions.put(key,tr);}tr.attempts++;tr.score=tr.attempts==1?sim:tr.score*.6+sim*.4;tr.dueAt=p.dueAt;}state.recallChecks++;persist();boolean good=sim>=.8&&!revealed;vibrate(good);String msg=revealed?"הצגת תשובה: השורה תחזור שוב מוקדם.":sim>=.92?"שליפה מצוינת.":sim>=.8?"טוב מאוד — עוד חזרה קטנה תחזק אותה.":sim>=.62?"כמעט. שים לב למילים החסרות ולסדר.":"זו שורה שצריך לחזק — והיא תחזור אליך מוקדם יותר.";showFeedback(msg,good?GREEN:AMBER);}
    void showFeedback(String msg,int color){new AlertDialog.Builder(this).setTitle("תוצאת האימון").setMessage(msg+"\n\nהשורה הנכונה:\n"+task.expected).setPositiveButton("הבא",(d,w)->{task=null;revealed=false;render();}).setNegativeButton("סיום",(d,w)->{task=null;revealed=false;view="home";render();}).show();}

    TrainingTask nextTask(Song s){if(s.lines.isEmpty())return null;long now=System.currentTimeMillis();int best=0;double bw=-1;for(int i=0;i<s.lines.size();i++){Progress p=s.progress(s.lines.get(i).id);double w=(p.exposures==0?100:0)+(p.attempts==0?45:0)+(1-p.score)*75+(p.dueAt<=now?35:0)+p.lapses*4;if(w>bw){bw=w;best=i;}}Line line=s.lines.get(best);Progress p=s.progress(line.id);TrainingTask t=new TrainingTask();t.songId=s.id;t.index=best;t.section=line.section;t.expected=line.text;if(p.exposures==0){t.guided=true;t.prompt="קרא את השורה בקול. אחר כך נסתיר אותה ונבקש ממך לשלוף אותה.";return t;}if(best>0&&p.attempts>0&&Math.random()<.35){Progress tr=s.transitions.get(s.lines.get(best-1).id+">"+line.id);if(tr==null||tr.score<.82){t.transition=true;t.prompt="מה בא מיד אחרי השורה הזאת?";t.cue=s.lines.get(best-1).text;return t;}}if(p.attempts==0){t.prompt="השלם את השורה מהזיכרון";t.cue=maskWords(line.text);return t;}if(p.score<.65){t.prompt="כתוב את השורה בעזרת האותיות הראשונות";t.cue=initials(line.text);return t;}t.prompt="שליפה נקייה — כתוב את כל השורה בלי רמז";return t;}
    String maskWords(String s){String[] w=s.split("\\s+");StringBuilder b=new StringBuilder();for(int i=0;i<w.length;i++)b.append(i%2==0?w[i]:"＿＿").append(' ');return b.toString().trim();}
    String initials(String s){String[] w=s.split("\\s+");StringBuilder b=new StringBuilder();for(String x:w){String n=normalize(x);if(!n.isEmpty())b.append(n.charAt(0)).append("׳ ");}return b.toString().trim();}

    void renderProgress(){setHead("מפת הזיכרון","איפה השיר יושב ואיפה הוא עדיין נופל");if(state.songs.isEmpty()){content.addView(tv("הוסף שיר כדי לראות מפת זיכרון.",18,MUTED,false));return;}for(Song s:state.songs){LinearLayout c=card();c.addView(tv(s.title+" · "+readiness(s)+"%",20,TEXT,true));c.addView(gap(9));for(Line l:s.lines){Progress p=s.progress(l.id);LinearLayout row=vertical();row.addView(tv(l.text,14,TEXT,true));ProgressBar pb=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);pb.setMax(100);pb.setProgress((int)Math.round(p.score*100));pb.setProgressTintList(android.content.res.ColorStateList.valueOf(p.score>=.8?GREEN:p.score>=.55?AMBER:PURPLE));row.addView(pb,new LinearLayout.LayoutParams(-1,dp(7)));row.addView(tv((int)Math.round(p.score*100)+"% · "+(p.attempts==0?"טרם נבדקה":p.streak+" הצלחות רצופות"),11,MUTED,false));c.addView(row);c.addView(gap(9));}content.addView(c,mp());content.addView(gap(12));}}

    void renderMore(){setHead("עוד","הגדרות · גיבוי · אודות");LinearLayout c=card();c.addView(tv("הנתונים שלך",20,TEXT,true));c.addView(tv("השירים וההתקדמות נשמרים מקומית במכשיר. אפשר לייצא גיבוי JSON ולהחזיר אותו בכל עת.",14,MUTED,false));c.addView(gap(12));Button ex=button("ייצא גיבוי",false);ex.setOnClickListener(v->exportBackup());Button im=button("ייבא גיבוי",false);im.setOnClickListener(v->importBackup());c.addView(ex,mp());c.addView(gap(7));c.addView(im,mp());content.addView(c);content.addView(gap(12));LinearLayout about=card();about.addView(tv("קול יעקב",24,TEXT,true));about.addView(tv("מאמן זיכרון ביצועי לאמנים",15,PURPLE2,true));about.addView(gap(12));about.addView(tv("בהשראת יעקב ישראל אבוטבול",16,TEXT,true));about.addView(tv("נבנה על ידי אופיר גלבוע",16,TEXT,true));about.addView(gap(8));about.addView(tv("ofirgilboa2050@gmail.com",14,MUTED,false));about.addView(tv("054-924-9925",14,MUTED,false));about.addView(gap(10));about.addView(tv("Android Native · v0.4.1",12,MUTED,false));content.addView(about);}

    void startPerformance(Song s){performance=new PerformanceSession();performance.songId=s.id;performance.index=0;performance.revealed=false;getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);view="performance";render();}
    void renderPerformance(){setHead("חזרת במה","מסך נקי · מעבר בין שורות");if(performance==null){view="library";render();return;}Song s=getSong(performance.songId);if(s==null){endPerformance();return;}LinearLayout c=card();TextView count=tv((performance.index+1)+" / "+s.lines.size(),12,MUTED,true);count.setGravity(Gravity.CENTER);c.addView(count);c.addView(gap(16));Line l=s.lines.get(Math.min(performance.index,s.lines.size()-1));TextView sec=tv(l.section,14,PURPLE2,true);sec.setGravity(Gravity.CENTER);c.addView(sec);TextView line=tv(performance.revealed?l.text:"נסה לשיר את השורה הבאה מהזיכרון…",27,performance.revealed?TEXT:Color.rgb(110,121,145),true);line.setGravity(Gravity.CENTER);line.setMinHeight(dp(190));line.setGravity(Gravity.CENTER);c.addView(line,mp());Button reveal=button(performance.revealed?"המשך לשורה הבאה":"הצג שורה",true);reveal.setOnClickListener(v->{if(!performance.revealed){performance.revealed=true;performance.rescues++;render();}else{performance.index++;performance.revealed=false;if(performance.index>=s.lines.size()){new AlertDialog.Builder(this).setTitle("חזרת במה הושלמה").setMessage("סיימת את "+s.title+" עם "+performance.rescues+" הצצות לטקסט.").setPositiveButton("סיום",(d,w)->endPerformance()).show();}else render();}});c.addView(reveal,mp());content.addView(c);content.addView(gap(10));Button end=button("סיים חזרה",false);end.setOnClickListener(v->endPerformance());content.addView(end,mp());}
    void endPerformance(){getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);performance=null;view="library";render();}

    void songDialog(Song existing){LinearLayout box=vertical();pad(box,16,6);EditText title=new EditText(this);title.setHint("שם השיר");title.setText(existing==null?"":existing.title);EditText artist=new EditText(this);artist.setHint("אמן / מבצע");artist.setText(existing==null?"":existing.artist);EditText lyrics=new EditText(this);lyrics.setHint("[בית 1]\nשורה ראשונה...\nשורה שנייה...\n\n[פזמון]\n...");lyrics.setGravity(Gravity.TOP|Gravity.RIGHT);lyrics.setMinLines(10);lyrics.setText(existing==null?"":existing.lyrics);box.addView(title);box.addView(artist);box.addView(lyrics);AlertDialog d=new AlertDialog.Builder(this).setTitle(existing==null?"הוסף שיר":"עריכת שיר").setView(box).setPositiveButton("שמור",null).setNegativeButton("ביטול",null).create();if(existing!=null)d.setButton(AlertDialog.BUTTON_NEUTRAL,"מחק",(x,w)->{});d.setOnShowListener(x->{d.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{String t=title.getText().toString().trim(),a=artist.getText().toString().trim(),ly=lyrics.getText().toString().trim();if(t.isEmpty()||ly.isEmpty()){toast("נדרש שם שיר ומילים");return;}if(existing==null){Song s=new Song();s.id=UUID.randomUUID().toString();s.title=t;s.artist=a;s.lyrics=ly;s.rebuildLines(null);state.songs.add(s);}else{Map<String,Progress> old=new HashMap<>();for(Line l:existing.lines)old.put(l.text,existing.progress(l.id));existing.title=t;existing.artist=a;existing.lyrics=ly;existing.rebuildLines(old);}persist();d.dismiss();view="library";render();});if(existing!=null){d.getButton(AlertDialog.BUTTON_NEUTRAL).setTextColor(RED);d.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener(v->new AlertDialog.Builder(this).setTitle("למחוק את השיר?").setMessage(existing.title).setPositiveButton("מחק",(q,w)->{state.songs.remove(existing);persist();d.dismiss();render();}).setNegativeButton("ביטול",null).show());}});d.show();}

    void exportBackup(){pendingExport=state.toJson().toString();Intent i=new Intent(Intent.ACTION_CREATE_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("application/json");i.putExtra(Intent.EXTRA_TITLE,"kol-yaakov-backup.json");startActivityForResult(i,RC_EXPORT);}
    void importBackup(){Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);i.addCategory(Intent.CATEGORY_OPENABLE);i.setType("application/json");startActivityForResult(i,RC_IMPORT);}
    @Override protected void onActivityResult(int req,int res,Intent data){super.onActivityResult(req,res,data);if(res!=RESULT_OK||data==null||data.getData()==null)return;Uri u=data.getData();try{if(req==RC_EXPORT){try(OutputStream o=getContentResolver().openOutputStream(u)){o.write(pendingExport.getBytes(StandardCharsets.UTF_8));}toast("הגיבוי נשמר");}else if(req==RC_IMPORT){StringBuilder b=new StringBuilder();try(BufferedReader r=new BufferedReader(new InputStreamReader(getContentResolver().openInputStream(u),StandardCharsets.UTF_8))){String line;while((line=r.readLine())!=null)b.append(line);}AppState n=AppState.load(b.toString());if(n.songs==null)throw new Exception("invalid");state=n;persist();toast("הגיבוי יובא בהצלחה");render();}}catch(Exception e){toast("הפעולה נכשלה: קובץ לא תקין");}}

    Song smartSong(){Song best=null;double bw=-1;for(Song s:state.songs){double w=(100-readiness(s))+dueCount(s)*10;if(w>bw){bw=w;best=s;}}return best;}
    Song getSong(String id){if(id==null)return null;for(Song s:state.songs)if(s.id.equals(id))return s;return null;}
    int avgReady(){if(state.songs.isEmpty())return 0;int x=0;for(Song s:state.songs)x+=readiness(s);return x/state.songs.size();}
    int totalDue(){int x=0;for(Song s:state.songs)x+=dueCount(s);return x;}
    int dueCount(Song s){long n=System.currentTimeMillis();int x=0;for(Line l:s.lines){Progress p=s.progress(l.id);if(p.exposures==0||p.dueAt<=n)x++;}return x;}
    int readiness(Song s){if(s.lines.isEmpty())return 0;double sum=0;int tested=0;for(Line l:s.lines){Progress p=s.progress(l.id);sum+=Math.min(1,.8*p.score+.2*Math.min(1,p.streak/3.0));if(p.attempts>0)tested++;}double cov=tested/(double)s.lines.size(),score=.85*(sum/s.lines.size())+.15*cov;if(cov<.5)score=Math.min(score,.49);else if(cov<.8)score=Math.min(score,.69);return (int)Math.round(score*100);}
    void vibrate(boolean good){try{if(vibrator!=null&&vibrator.hasVibrator())vibrator.vibrate(VibrationEffect.createOneShot(good?45:70,VibrationEffect.DEFAULT_AMPLITUDE));}catch(Exception ignored){}}
    void toast(String m){Toast.makeText(this,m,Toast.LENGTH_SHORT).show();}

    static String normalize(String s){if(s==null)return "";String x=Normalizer.normalize(s.toLowerCase(Locale.ROOT).trim(),Normalizer.Form.NFD).replaceAll("[\\u0591-\\u05C7]","").replaceAll("[^\\p{L}\\p{N}]+"," ").trim().replaceAll("\\s+"," ");return x;}
    static double similarity(String a,String b){a=normalize(a);b=normalize(b);if(a.equals(b))return 1;if(a.isEmpty()||b.isEmpty())return 0;int[][] d=new int[a.length()+1][b.length()+1];for(int i=0;i<=a.length();i++)d[i][0]=i;for(int j=0;j<=b.length();j++)d[0][j]=j;for(int i=1;i<=a.length();i++)for(int j=1;j<=b.length();j++)d[i][j]=Math.min(Math.min(d[i-1][j]+1,d[i][j-1]+1),d[i-1][j-1]+(a.charAt(i-1)==b.charAt(j-1)?0:1));return Math.max(0,1-d[a.length()][b.length()]/(double)Math.max(a.length(),b.length()));}

    static class TrainingTask {String songId,section="",expected="",prompt="",cue="";int index;boolean guided=false,transition=false;}
    static class PerformanceSession {String songId;int index,rescues;boolean revealed;}
    static class Line {String id,text,section;Line(String t,String s){id=UUID.randomUUID().toString();text=t;section=s;}}
    static class Progress {int exposures=0,attempts=0,successes=0,streak=0,lapses=0;double score=0,best=0,lastScore=0;long dueAt=0,lastSeen=0;
        JSONObject json(){try{JSONObject o=new JSONObject();o.put("exposures",exposures);o.put("attempts",attempts);o.put("successes",successes);o.put("streak",streak);o.put("lapses",lapses);o.put("score",score);o.put("best",best);o.put("lastScore",lastScore);o.put("dueAt",dueAt);o.put("lastSeen",lastSeen);return o;}catch(Exception e){return new JSONObject();}}
        static Progress from(JSONObject o){Progress p=new Progress();if(o==null)return p;p.exposures=o.optInt("exposures");p.attempts=o.optInt("attempts");p.successes=o.optInt("successes");p.streak=o.optInt("streak");p.lapses=o.optInt("lapses");p.score=o.optDouble("score");p.best=o.optDouble("best");p.lastScore=o.optDouble("lastScore");p.dueAt=o.optLong("dueAt");p.lastSeen=o.optLong("lastSeen");return p;}}
    static class Song {String id="",title="",artist="",lyrics="";ArrayList<Line> lines=new ArrayList<>();HashMap<String,Progress> prog=new HashMap<>(),transitions=new HashMap<>();
        Progress progress(String id){Progress p=prog.get(id);if(p==null){p=new Progress();prog.put(id,p);}return p;}
        void rebuildLines(Map<String,Progress> byText){lines.clear();prog.clear();String section="בית 1";for(String raw:lyrics.replace("\r","").split("\n")){String t=raw.trim();if(t.isEmpty())continue;if((t.startsWith("[")&&t.endsWith("]"))||(t.startsWith("(")&&t.endsWith(")"))){section=t.substring(1,t.length()-1).trim();continue;}Line l=new Line(t,section);lines.add(l);if(byText!=null&&byText.get(t)!=null)prog.put(l.id,byText.get(t));else prog.put(l.id,new Progress());}}
        JSONObject json(){try{JSONObject o=new JSONObject();o.put("id",id);o.put("title",title);o.put("artist",artist);o.put("lyrics",lyrics);JSONArray la=new JSONArray();for(Line l:lines){JSONObject x=new JSONObject();x.put("id",l.id);x.put("text",l.text);x.put("section",l.section);la.put(x);}o.put("lines",la);JSONObject po=new JSONObject();for(Map.Entry<String,Progress> e:prog.entrySet())po.put(e.getKey(),e.getValue().json());o.put("progress",po);JSONObject tr=new JSONObject();for(Map.Entry<String,Progress> e:transitions.entrySet())tr.put(e.getKey(),e.getValue().json());o.put("transitions",tr);return o;}catch(Exception e){return new JSONObject();}}
        static Song from(JSONObject o){Song s=new Song();s.id=o.optString("id",UUID.randomUUID().toString());s.title=o.optString("title","שיר");s.artist=o.optString("artist","");s.lyrics=o.optString("lyrics","");JSONArray la=o.optJSONArray("lines");if(la!=null)for(int i=0;i<la.length();i++){JSONObject x=la.optJSONObject(i);Line l=new Line(x.optString("text"),x.optString("section","בית 1"));l.id=x.optString("id",l.id);s.lines.add(l);}if(s.lines.isEmpty())s.rebuildLines(null);JSONObject po=o.optJSONObject("progress");if(po!=null){Iterator<String> it=po.keys();while(it.hasNext()){String k=it.next();s.prog.put(k,Progress.from(po.optJSONObject(k)));}}for(Line l:s.lines)s.progress(l.id);JSONObject tr=o.optJSONObject("transitions");if(tr!=null){Iterator<String> it=tr.keys();while(it.hasNext()){String k=it.next();s.transitions.put(k,Progress.from(tr.optJSONObject(k)));}}return s;}}
    static class AppState {ArrayList<Song> songs=new ArrayList<>();long createdAt=System.currentTimeMillis(),updatedAt=createdAt;int recallChecks=0;
        JSONObject toJson(){try{JSONObject o=new JSONObject();o.put("schema",4);o.put("createdAt",createdAt);o.put("updatedAt",updatedAt);o.put("recallChecks",recallChecks);JSONArray a=new JSONArray();for(Song s:songs)a.put(s.json());o.put("songs",a);return o;}catch(Exception e){return new JSONObject();}}
        static AppState load(String json){AppState s=new AppState();if(json==null||json.trim().isEmpty())return s;try{JSONObject o=new JSONObject(json);s.createdAt=o.optLong("createdAt",System.currentTimeMillis());s.updatedAt=o.optLong("updatedAt",s.createdAt);s.recallChecks=o.optInt("recallChecks");JSONArray a=o.optJSONArray("songs");if(a!=null)for(int i=0;i<a.length();i++)s.songs.add(Song.from(a.getJSONObject(i)));return s;}catch(Exception e){return new AppState();}}
    }
}