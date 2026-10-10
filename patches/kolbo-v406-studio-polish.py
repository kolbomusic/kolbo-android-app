from pathlib import Path
import shutil,sys
root=Path(sys.argv[1]); base=root/'app/src/main/java/com/kolbo/videostudio'
main=base/'MainActivity.java'; gradle=root/'app/build.gradle'; s=main.read_text(encoding='utf-8')

def one(a,b):
    global s
    n=s.count(a)
    if n!=1: raise SystemExit(f'v406 expected one occurrence ({n}) of {a[:95]!r}')
    s=s.replace(a,b,1)

shutil.copyfile('patches/StudioVisuals.java',base/'StudioVisuals.java')
shutil.copyfile('patches/OutputLengthGate.java',base/'OutputLengthGate.java')
# Retain backend and image picking; replace only construction of the UI.
one('import android.widget.VideoView;', 'import android.widget.VideoView;\nimport android.content.res.ColorStateList;\nimport android.text.InputType;')
one('private ProgressBar progress;', '''private ProgressBar progress;
    private ScrollView studioScroll;
    private LinearLayout waitingCard,resultCard,advancedPanel;
    private StudioVisuals.AmbientMotionView ambient;
    private TextView waitingHeading,waitingSubtitle;
    private Button detailsToggle;
    private volatile String lastPhaseDetail="";
    private volatile int expectedDuration=8;''')

begin=s.index('    @Override public void onCreate(Bundle b) {')
end=s.index('    private void choosePhoto(int slot){',begin)
new_ui=r'''    @Override public void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().setStatusBarColor(StudioVisuals.BG);
        getWindow().setNavigationBarColor(StudioVisuals.BG);
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        getWindow().getDecorView().setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        hebrewVoice = new TextToSpeech(getApplicationContext(),init -> {
            if(init==TextToSpeech.SUCCESS){
                TextToSpeech voice=hebrewVoice;
                if(voice!=null){
                    int result=voice.setLanguage(Locale.forLanguageTag("he-IL"));
                    voiceAvailable=result!=TextToSpeech.LANG_MISSING_DATA && result!=TextToSpeech.LANG_NOT_SUPPORTED;
                }
            }
        });
        studioScroll=new ScrollView(this);
        studioScroll.setFillViewport(true);
        studioScroll.setClipToPadding(false);
        LinearLayout root=new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(dp(18),dp(24),dp(18),dp(38));
        root.setBackgroundColor(StudioVisuals.BG);
        studioScroll.addView(root);
        setContentView(studioScroll);

        TextView badge=label("✦  סטודיו AI",13,true);
        badge.setTextColor(StudioVisuals.PRIMARY);
        badge.setContentDescription("סטודיו בינה מלאכותית");
        root.addView(badge);
        TextView title=label("Kolbo Video",32,true);
        title.setTextColor(StudioVisuals.INK);title.setPadding(0,0,0,dp(4));
        root.addView(title);
        TextView intro=label("מתמונה ורעיון לסרטון משלך",16,false);
        intro.setTextColor(StudioVisuals.MUTED);
        root.addView(intro);

        LinearLayout referenceCard=new LinearLayout(this);
        referenceCard.setOrientation(LinearLayout.VERTICAL);
        StudioVisuals.card(referenceCard,this);
        root.addView(referenceCard,StudioVisuals.spaced(this,-2,18));
        referenceCard.addView(sectionLabel("01  הדמויות שלך"));
        TextView hintImages=label("אפשר ליצור גם מתיאור בלבד",13,false);
        hintImages.setTextColor(StudioVisuals.MUTED);referenceCard.addView(hintImages);
        LinearLayout uploads=new LinearLayout(this);
        uploads.setOrientation(LinearLayout.HORIZONTAL);
        referenceCard.addView(uploads,StudioVisuals.spaced(this,-2,10));
        pick=button("＋  תמונה 1");
        pickTwo=button("＋  תמונה 2");
        LinearLayout.LayoutParams firstButton=new LinearLayout.LayoutParams(0,dp(54),1f);
        firstButton.leftMargin=dp(5);
        uploads.addView(pick,firstButton);
        LinearLayout.LayoutParams secondButton=new LinearLayout.LayoutParams(0,dp(54),1f);
        secondButton.rightMargin=dp(5);
        uploads.addView(pickTwo,secondButton);

        selected=label("דמות 1 — ללא תמונה",13,false);selected.setTextColor(StudioVisuals.MUTED);
        referenceCard.addView(selected);
        photoOnePreview=new android.widget.ImageView(this);
        photoOnePreview.setScaleType(android.widget.ImageView.ScaleType.FIT_CENTER);
        photoOnePreview.setContentDescription("תצוגת תמונת המקור של דמות 1");
        photoOnePreview.setBackground(StudioVisuals.round(0xffF3EFF9,dp(12)));
        photoOnePreview.setVisibility(View.GONE);
        referenceCard.addView(photoOnePreview,StudioVisuals.spaced(this,156,5));
        secondSelected=label("דמות 2 — ללא תמונה",13,false);
        secondSelected.setTextColor(StudioVisuals.MUTED);referenceCard.addView(secondSelected);
        photoTwoPreview=new android.widget.ImageView(this);
        photoTwoPreview.setScaleType(android.widget.ImageView.ScaleType.FIT_CENTER);
        photoTwoPreview.setContentDescription("תצוגת תמונת המקור של דמות 2");
        photoTwoPreview.setBackground(StudioVisuals.round(0xffF3EFF9,dp(12)));
        photoTwoPreview.setVisibility(View.GONE);
        referenceCard.addView(photoTwoPreview,StudioVisuals.spaced(this,156,5));

        LinearLayout scriptCard=new LinearLayout(this);
        scriptCard.setOrientation(LinearLayout.VERTICAL);
        StudioVisuals.card(scriptCard,this);
        root.addView(scriptCard,StudioVisuals.spaced(this,-2,16));
        scriptCard.addView(sectionLabel("02  מה קורה בסרטון?"));
        prompt=new EditText(this);
        prompt.setHint("לדוגמה: שתי הדמויות שרות יחד על הבמה בקיסריה...");
        prompt.setTextSize(17);
        prompt.setSingleLine(false);
        prompt.setMinLines(4);
        prompt.setMaxLines(8);
        prompt.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE|
            InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        prompt.setTextDirection(View.TEXT_DIRECTION_RTL);
        prompt.setGravity(Gravity.TOP|Gravity.RIGHT);
        prompt.setTextColor(StudioVisuals.INK);
        prompt.setHintTextColor(StudioVisuals.MUTED);
        prompt.setPadding(dp(15),dp(13),dp(15),dp(13));
        prompt.setBackground(StudioVisuals.outline(0xffFCFBFE,dp(14),StudioVisuals.STROKE,dp(1)));
        prompt.setContentDescription("תיאור הסרטון שלך בעברית");
        scriptCard.addView(prompt,StudioVisuals.spaced(this,-2,9));
        TextView promptHint=label("תאר מה יקרה, מי משתתף והיכן",12,false);
        promptHint.setTextColor(StudioVisuals.MUTED);scriptCard.addView(promptHint);

        LinearLayout timeCard=new LinearLayout(this);
        timeCard.setOrientation(LinearLayout.VERTICAL);
        StudioVisuals.card(timeCard,this);
        root.addView(timeCard,StudioVisuals.spaced(this,-2,16));
        timeCard.addView(sectionLabel("03  אורך הסרטון"));
        durationLabel=label("8 שניות",22,true);durationLabel.setTextColor(StudioVisuals.PRIMARY);
        timeCard.addView(durationLabel);
        durationBar=new SeekBar(this);
        durationBar.setMax(59);
        durationBar.setProgress(7);
        durationBar.setProgressTintList(ColorStateList.valueOf(StudioVisuals.PRIMARY));
        durationBar.setThumbTintList(ColorStateList.valueOf(StudioVisuals.PRIMARY));
        durationBar.setContentDescription("משך הסרטון בשניות, מאחת עד שישים");
        timeCard.addView(durationBar,StudioVisuals.spaced(this,-2,3));
        LinearLayout presets=new LinearLayout(this);presets.setOrientation(LinearLayout.HORIZONTAL);
        timeCard.addView(presets,StudioVisuals.spaced(this,-2,4));
        for(int number:new int[]{5,10,15,30}){
            Button chip=button(number+" שנ׳");
            chip.setTextSize(13);
            LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(0,dp(46),1f);
            params.rightMargin=dp(4);presets.addView(chip,params);
            chip.setOnClickListener(v->durationBar.setProgress(number-1));
        }
        durationBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){
            public void onProgressChanged(SeekBar bar,int value,boolean user){
                durationSeconds=value+1;
                durationLabel.setText(durationSeconds+" שניות");
            }
            public void onStartTrackingTouch(SeekBar bar){}
            public void onStopTrackingTouch(SeekBar bar){}
        });

        generate=button("✦  צור את הסרטון שלי");
        StudioVisuals.action(generate,this,true);
        generate.setContentDescription("התחל יצירת סרטון מתיאור ותמונות");
        root.addView(generate,StudioVisuals.spaced(this,58,18));

        waitingCard=new LinearLayout(this);
        waitingCard.setOrientation(LinearLayout.VERTICAL);
        StudioVisuals.card(waitingCard,this);
        waitingCard.setGravity(Gravity.CENTER_HORIZONTAL);
        ambient=new StudioVisuals.AmbientMotionView(this);
        waitingCard.addView(ambient,StudioVisuals.spaced(this,130,0));
        waitingHeading=label("מכינים לך משהו יפה...",20,true);
        waitingHeading.setTextColor(StudioVisuals.INK);
        waitingHeading.setGravity(Gravity.CENTER);
        waitingCard.addView(waitingHeading);
        waitingSubtitle=label("ההפקה מתקדמת בשלבים. אפשר להמתין כאן בנחת.",14,false);
        waitingSubtitle.setTextColor(StudioVisuals.MUTED);
        waitingSubtitle.setGravity(Gravity.CENTER);
        waitingCard.addView(waitingSubtitle);
        progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);
        progress.setIndeterminate(true);
        progress.setIndeterminateTintList(ColorStateList.valueOf(StudioVisuals.PRIMARY));
        waitingCard.addView(progress,StudioVisuals.spaced(this,5,12));
        waitingCard.setVisibility(View.GONE);
        root.addView(waitingCard,StudioVisuals.spaced(this,-2,12));

        status=label("מוכן לרעיון הבא שלך",14,false);
        status.setTextColor(StudioVisuals.MUTED);
        status.setGravity(Gravity.CENTER);
        root.addView(status,StudioVisuals.spaced(this,-2,12));

        resultCard=new LinearLayout(this);resultCard.setOrientation(LinearLayout.VERTICAL);
        StudioVisuals.card(resultCard,this);
        resultCard.addView(sectionLabel("התוצאה שלך"));
        TextView resultNote=label("אפשר לצפות ולשמור. בדוק שהסרטון מתאים לבקשה.",13,false);
        resultNote.setTextColor(StudioVisuals.MUTED);resultCard.addView(resultNote);
        player=new VideoView(this);
        player.setVisibility(View.GONE);
        player.setContentDescription("נגן תצוגה מקדימה של הסרטון");
        resultCard.addView(player,StudioVisuals.spaced(this,238,8));
        download=button("שמור וידאו לטלפון");
        StudioVisuals.action(download,this,true);
        download.setVisibility(View.GONE);
        resultCard.addView(download,StudioVisuals.spaced(this,56,10));
        resultCard.setVisibility(View.GONE);
        root.addView(resultCard,StudioVisuals.spaced(this,-2,15));

        detailsToggle=button("ⓘ  פרטים נוספים");
        root.addView(detailsToggle,StudioVisuals.spaced(this,48,14));
        advancedPanel=new LinearLayout(this);
        advancedPanel.setOrientation(LinearLayout.VERTICAL);
        StudioVisuals.card(advancedPanel,this);
        advancedPanel.setVisibility(View.GONE);
        root.addView(advancedPanel,StudioVisuals.spaced(this,-2,4));
        TextView privacy=label("התמונות וההנחיה נשלחות לשירות יצירת וידאו חיצוני רק בהסכמתך. השירות עשוי להיות עמוס או מוגבל. חלק מהתוצאות מחייבות בדיקה ידנית של דמויות, שירה וסצנה.",13,false);
        privacy.setTextColor(StudioVisuals.MUTED);
        advancedPanel.addView(privacy);
        diagnostics=button("הצג אבחון טכני");
        advancedPanel.addView(diagnostics,StudioVisuals.spaced(this,50,8));
        Button statusDetail=button("מידע על הפעולה האחרונה");
        advancedPanel.addView(statusDetail,StudioVisuals.spaced(this,50,7));

        detailsToggle.setOnClickListener(v->{
            boolean visible=advancedPanel.getVisibility()==View.VISIBLE;
            advancedPanel.setVisibility(visible?View.GONE:View.VISIBLE);
            detailsToggle.setText(visible?"ⓘ  פרטים נוספים":"סגור פרטים");
        });
        statusDetail.setOnClickListener(v->new AlertDialog.Builder(this)
            .setTitle("פרטי הפעולה")
            .setMessage(lastPhaseDetail.isEmpty()?"לא בוצעה יצירה עדיין.":lastPhaseDetail)
            .setPositiveButton("סגור",(d,w)->{}).show());
        diagnostics.setOnClickListener(v->{
            String request=prompt.getText().toString().trim();
            String previous=lastSubmittedPrompt;
            String detail=SceneIntentContract.from(request).reviewHebrew()+"\n"
                +CharacterRoleContract.from(request).preview()+"\n\n"
                +(previous.isEmpty()?"עדיין אין הנחיה שנשלחה למנוע.":previous);
            new AlertDialog.Builder(this).setTitle("הנחיית AI בפועל")
                .setMessage(detail).setPositiveButton("סגור",(d,w)->{}).show();
        });

        pick.setOnClickListener(v->choosePhoto(PICK));
        pickTwo.setOnClickListener(v->choosePhoto(PICK_TWO));
        generate.setOnClickListener(v->createVideo());
        download.setOnClickListener(v->{
            if(resultFile==null||!resultFile.exists())return;
            Intent save=new Intent(Intent.ACTION_CREATE_DOCUMENT);
            save.setType("video/mp4");save.addCategory(Intent.CATEGORY_OPENABLE);
            save.putExtra(Intent.EXTRA_TITLE,"Kolbo-Video-"+System.currentTimeMillis()+".mp4");
            startActivityForResult(save,SAVE);
        });
    }
    private TextView sectionLabel(String heading){
        TextView t=label(heading,17,true);
        t.setTextColor(StudioVisuals.INK);return t;
    }
'''
s=s[:begin]+new_ui+s[end:]
one('private TextView label(String s,int size,boolean bold) {',
    'private TextView label(String s,int size,boolean bold) {')
one('t.setPadding(0,dp(12),0,dp(12));return t;','t.setPadding(0,dp(5),0,dp(5));return t;')
one('private Button button(String title) { Button b=new Button(this);b.setText(title);b.setAllCaps(false);return b; }',
    'private Button button(String title) { Button b=new Button(this);b.setText(title);StudioVisuals.action(b,this,false);return b; }')

one('private void message(String s) { ui.post(() -> status.setText(s)); }',
    '''private void message(String s) {
        lastPhaseDetail=s==null?"":s;
        ui.post(() -> {
            String shown=s==null?"":s;
            if(running && waitingHeading!=null){
                String lower=shown.toLowerCase(Locale.ROOT);
                if(lower.contains("תרגום")||lower.contains("מכין"))shown="מכינים את הסצנה...";
                else if(lower.contains("מעלה")||lower.contains("מקור"))shown="מארגנים את התמונות...";
                else if(lower.contains("מחבר")||lower.contains("משלב"))shown="מחברים את הסצנות...";
                else if(lower.contains("בודק"))shown="בודקים את התוצאה...";
                else if(lower.contains("מקטע")||lower.contains("יוצר")||lower.contains("רנדר"))
                    shown="יוצרים את הסרטון...";
                else if(lower.contains("מכסה")||lower.contains("quota"))
                    shown="השירות הגיע למגבלת שימוש";
                else if(lower.contains("שגיאה")||lower.contains("נכשל")||lower.contains("לא הושלמה"))
                    shown="לא ניתן להשלים את ההפקה";
                waitingHeading.setText(shown);
                status.setText("הסרטון בהכנה");
            }else {
                String lower=shown.toLowerCase(Locale.ROOT);
                if(lower.length()>170)shown="ההפקה הסתיימה. ניתן לפתוח פרטים נוספים.";
                status.setText(shown);
            }
        });
    }''')
one('private void busy(boolean b) { running=b;ui.post(() -> {generate.setEnabled(!b);pick.setEnabled(!b);pickTwo.setEnabled(!b);durationBar.setEnabled(!b);progress.setVisibility(b?View.VISIBLE:View.GONE);}); }',
    '''private void busy(boolean b) {
        running=b;
        ui.post(() -> {
            generate.setEnabled(!b);pick.setEnabled(!b);pickTwo.setEnabled(!b);
            durationBar.setEnabled(!b);
            waitingCard.setVisibility(b?View.VISIBLE:View.GONE);
            if(b){ambient.start();waitingHeading.setText("מכינים את הסצנה...");}
            else ambient.stop();
        });
    }''')
# reset any prior file and ensure expected duration attached to THIS generation
one('lastSubmittedPrompt="";originalForDiagnostics=instruction;',
    '''lastSubmittedPrompt="";originalForDiagnostics=instruction;
        expectedDuration=requestedSeconds;
        resultFile=null;
        ui.post(() -> {resultCard.setVisibility(View.GONE);player.setVisibility(View.GONE);
                       download.setVisibility(View.GONE);});''')
# Fail closed: do not display mismatched 3sec partial when 10sec requested.
one('private void showResult(File file,String notice){\n        resultFile=file;',
    '''private void showResult(File file,String notice){
        try{OutputLengthGate.verify(file,expectedDuration);}
        catch(Exception error){
            lastPhaseDetail="הסרטון לא עבר אימות משך: "+error.getMessage();
            message("הסרטון יצא קצר מדי. אפשר לראות פרטים נוספים.");
            busy(false);
            return;
        }
        resultFile=file;''')
one('status.setText(displayNotice);',
    '''lastPhaseDetail=displayNotice;
            status.setText(unverified?"הסרטון מוכן לבדיקה":"הסרטון מוכן");
            resultCard.setVisibility(View.VISIBLE);
            studioScroll.post(() -> studioScroll.smoothScrollTo(0,resultCard.getTop()));''')
# Prevent incorrectly accepting each segment (or showing partial as finished)
one('clips.add(clip);\n                        inScene-=secs;',
    '''OutputLengthGate.verify(clip,secs);
                        clips.add(clip);
                        inScene-=secs;''')
one('File file=getVideo(media);clips.add(file);',
    'File file=getVideo(media);OutputLengthGate.verify(file,seconds);clips.add(file);')
one('''                if(!clips.isEmpty() && clips.get(0).exists()){
                    // Preserve work completed before reaching a provider quota.
                    // Never label partial video as a completed requested film.
                    showResult(clips.get(0),"טיוטה חלקית בלבד, לא באורך המבוקש. "+ProviderFailure.explain(e));
                }else busy(false);''',
    '''                for(File partial:clips)try{partial.delete();}catch(Exception ignored){}
                busy(false);''')
# Explicit preference for an easy UI and a single predictable provider path.
# Consent remains mandatory before photos are uploaded to a third-party service.
start=s.index('            new AlertDialog.Builder(this)\n                .setTitle("שתי דמויות — מנוע רב-ייחוס")')
end=s.index('            return;\n        }',start)
old=s[start:end]
new='''            new AlertDialog.Builder(this)
                .setTitle("מוכנים ליצור?")
                .setMessage("שתי התמונות וההנחיה יישלחו לשירות יצירת וידאו חיצוני. ניתן להמשיך?")
                .setPositiveButton("כן, צור סרטון",(d,w)->{
                    useMultiReferenceProvider=true;
                    approvedComposite=null;
                    beginGeneration(instruction,chosen,second,desired);
                })
                .setNegativeButton("ביטול",(d,w)->{})
                .show();
'''
s=s[:start]+new+s[end:]
# Stop rendering animation if activity destroyed.
one('if(hebrewVoice!=null)hebrewVoice.shutdown();',
    'if(ambient!=null)ambient.stop();\n        if(hebrewVoice!=null)hebrewVoice.shutdown();')
# Streaming messages must be short; no fake progress percentages.
g=gradle.read_text(encoding='utf-8')
for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview405'","applicationId 'com.kolbo.videostudio.preview406'"),
    ("versionCode 405","versionCode 406"),
    ("versionName '4.0.5'","versionName '4.0.6'")
]:
    if g.count(old)!=1:raise SystemExit("gradle mismatch "+old)
    g=g.replace(old,new,1)
gradle.write_text(g,encoding='utf-8')
main.write_text(s,encoding='utf-8')
assert "OutputLengthGate.verify(file,expectedDuration)" in s
assert "OutputLengthGate.verify(clip,secs)" in s
assert "OutputLengthGate.verify(file,seconds)" in s
assert "clips.get(0)" not in s[s.index("private void startMSRVideo("):]
assert "new StudioVisuals.AmbientMotionView(this)" in s
assert "waitingCard.setVisibility(b?View.VISIBLE:View.GONE)" in s
assert "name" not in [] # no-op
print("PASS v4.0.6 studio UI, calm animation, final and segment duration gate, no short partial video")
