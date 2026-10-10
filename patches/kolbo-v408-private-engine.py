from pathlib import Path
import shutil,sys
root=Path(sys.argv[1])
base=root/'app/src/main/java/com/kolbo/videostudio'
main=base/'MainActivity.java'
gradle=root/'app/build.gradle'
s=main.read_text(encoding='utf-8')
def once(old,new):
    global s
    n=s.count(old)
    if n!=1:raise SystemExit("v408 patch expected one match, found "+str(n)+": "+old[:120])
    s=s.replace(old,new,1)

shutil.copyfile('patches/PrivateRenderClient.java',base/'PrivateRenderClient.java')
once('''        diagnostics=button("הצג אבחון טכני");''',
    '''        Button privateSettings=button("חיבור מנוע הפקה עצמאי");
        advancedPanel.addView(privateSettings,StudioVisuals.spaced(this,52,8));
        privateSettings.setOnClickListener(v->showPrivateEngineSettings());
        diagnostics=button("הצג אבחון טכני");''')
once('''    private TextView sectionLabel(String heading){''',
    '''    private void showPrivateEngineSettings(){
        LinearLayout form=new LinearLayout(this);
        form.setPadding(dp(20),dp(10),dp(20),0);
        form.setOrientation(LinearLayout.VERTICAL);
        TextView instruction=label("שרת GPU בשליטתך, עם ComfyUI ומודל וידאו. נדרש HTTPS. אין מכסת קרדיטים בתוך האפליקציה, אך חומרת השרת מגבילה ביצועים. לא קיים שרת מובנה שמופעל בחינם.",13,false);
        instruction.setTextColor(StudioVisuals.MUTED);
        form.addView(instruction);
        EditText address=new EditText(this);
        address.setHint("https://video.example.com");
        address.setSingleLine(true);
        address.setInputType(android.text.InputType.TYPE_CLASS_TEXT
            |android.text.InputType.TYPE_TEXT_VARIATION_URI);
        address.setText(PrivateRenderClient.configuredUrl(this));
        form.addView(address,StudioVisuals.spaced(this,54,9));
        EditText secret=new EditText(this);
        secret.setHint("מפתח חיבור פרטי");
        secret.setSingleLine(true);
        secret.setInputType(android.text.InputType.TYPE_CLASS_TEXT
            |android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD);
        form.addView(secret,StudioVisuals.spaced(this,54,6));
        new AlertDialog.Builder(this)
            .setTitle("מנוע וידאו עצמאי")
            .setView(form)
            .setPositiveButton("שמור ובדוק חיבור",(d,w)->{
                try {
                    PrivateRenderClient.save(this,address.getText().toString(),
                        secret.getText().toString());
                    message("בודק את המנוע העצמאי...");
                    executor.execute(()->{
                        try{
                            org.json.JSONObject check=PrivateRenderClient.check(this);
                            if("ready".equals(check.optString("status")))
                                message("השרת הפרטי מחובר ומוכן ליצירה");
                            else message("החיבור נשמר, אבל המנוע עדיין לא מוכן: "
                                +check.optString("detail","נדרש GPU ו־Workflow"));
                        }catch(Exception e){message("בדיקת השרת הפרטי לא הצליחה: "+e.getMessage());}
                    });
                }catch(Exception e){message("פרטי החיבור לא נשמרו: "+e.getMessage());}
            })
            .setNeutralButton("נתק שרת פרטי",(d,w)->{
                PrivateRenderClient.clear(this);
                message("החיבור הפרטי נותק. אין שרת הפקה עצמאי פעיל.");
            })
            .setNegativeButton("ביטול",(d,w)->{})
            .show();
    }
    private void startPrivateVideo(String translated,String original,Uri first,Uri second,int seconds){
        executor.execute(()->{
            try{
                message("מכינים סרטון במנוע הפרטי...");
                // Unlike Gradio demos, both image references are preserved as
                // independent inputs all the way to the owner's workflow.
                String compiled=SceneIntentContract.from(original).sceneSetting()
                    +(second!=null?CharacterRoleContract.from(original).immutableSubjects()
                        +CharacterRoleContract.from(original).actionDirection()
                        :"")+translated;
                recordSubmittedPrompt("שרת וידאו עצמאי",compiled);
                File output=PrivateRenderClient.render(this,compiled,first,second,
                    seconds,getCacheDir(),stage->message(stage));
                OutputLengthGate.verify(output,seconds);
                showResult(output,"נוצר במנוע פרטי. הפנים, התוכן והשמע עדיין דורשים בדיקה.");
            }catch(Exception e){
                message("ההפקה במנוע הפרטי לא הושלמה: "+e.getMessage());
                busy(false);
            }
        });
    }
    private TextView sectionLabel(String heading){''')
once('''        final int desired=durationSeconds;
        if(second!=null){''',
    '''        final int desired=durationSeconds;
        if(PrivateRenderClient.configured(this)){
            new AlertDialog.Builder(this)
                .setTitle("יצירה במנוע הפרטי")
                .setMessage("התמונות וההנחיה יישלחו רק לשרת העצמאי שהגדרת. להמשיך?")
                .setPositiveButton("צור סרטון",(d,w)->beginGeneration(instruction,chosen,second,desired))
                .setNegativeButton("ביטול",(d,w)->{})
                .show();
            return;
        }
        if(second!=null){''')
once('''        if(!hasHebrew(instruction)) {''',
    '''        if(PrivateRenderClient.configured(this) && !hasHebrew(instruction)){
            startPrivateVideo(instruction,instruction,chosen,second,requestedSeconds);
            return;
        }
        if(!hasHebrew(instruction)) {''')
# Route translated Hebrew to the independent GPU engine (not raw Hebrew).
before_translation='''                  if(second!=null&&useMultiReferenceProvider){'''
after_translation='''                  if(PrivateRenderClient.configured(this)){
                      startPrivateVideo(enhanced,instruction,chosen,second,requestedSeconds);
                      return;
                  }
                  if(second!=null&&useMultiReferenceProvider){'''
if s.count(before_translation)!=1:raise SystemExit('No unique post-translation route')
s=s.replace(before_translation,after_translation,1)
g=gradle.read_text(encoding='utf-8')
for a,b in [
    ("applicationId 'com.kolbo.videostudio.preview407'","applicationId 'com.kolbo.videostudio.preview408'"),
    ("versionCode 407","versionCode 408"),
    ("versionName '4.0.7'","versionName '4.0.8'")
]:
    if g.count(a)!=1:raise SystemExit('missing Android version '+a)
    g=g.replace(a,b,1)
gradle.write_text(g,encoding='utf-8')
main.write_text(s,encoding='utf-8')
assert 'PrivateRenderClient.render(this,compiled,first,second' in s
assert 'OutputLengthGate.verify(output,seconds)' in s
assert 'privateSettings.setOnClickListener' in s
assert 'if(PrivateRenderClient.configured(this))' in s
print('PASS v408: optional private HTTPS render engine, secure setup, distinct sources and length gate')
