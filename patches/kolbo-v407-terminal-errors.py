from pathlib import Path
import sys,shutil
root=Path(sys.argv[1]);base=root/'app/src/main/java/com/kolbo/videostudio'
main=base/'MainActivity.java'
s=main.read_text(encoding='utf-8')
shutil.copyfile('patches/StudioFailureNotice.java',base/'StudioFailureNotice.java')
def patch(old,new):
    global s
    count=s.count(old)
    if count!=1:raise SystemExit('v407 error UI patch mismatch '+str(count)+': '+old[:100])
    s=s.replace(old,new,1)

patch('private Button detailsToggle;',
      '''private Button detailsToggle;
    private LinearLayout failureCard;
    private TextView failureHeading,failureSubtitle;
    private Button retryCreation;
    private volatile boolean generationInFlight=false;''')

patch('''        root.addView(generate,StudioVisuals.spaced(this,58,18));

        waitingCard''',
      '''        root.addView(generate,StudioVisuals.spaced(this,58,18));

        failureCard=new LinearLayout(this);
        failureCard.setOrientation(LinearLayout.VERTICAL);
        StudioVisuals.card(failureCard,this);
        failureCard.setBackground(StudioVisuals.outline(0xffFFF8FA,dp(20),0xffEDC7D1,dp(1)));
        failureHeading=label("לא נוצר סרטון",18,true);
        failureHeading.setTextColor(StudioVisuals.ERROR);
        failureHeading.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        failureCard.addView(failureHeading);
        failureSubtitle=label("אפשר לנסות שוב.",13,false);
        failureSubtitle.setTextColor(StudioVisuals.MUTED);
        failureCard.addView(failureSubtitle);
        retryCreation=button("↻  נסה שוב");
        StudioVisuals.action(retryCreation,this,true);
        failureCard.addView(retryCreation,StudioVisuals.spaced(this,52,9));
        retryCreation.setOnClickListener(v -> createVideo());
        failureCard.setVisibility(View.GONE);
        root.addView(failureCard,StudioVisuals.spaced(this,-2,11));

        waitingCard''')

patch('''    private void message(String s) {
        lastPhaseDetail=s==null?"":s;''',
      '''    private void message(String s) {
        lastPhaseDetail=s==null?"":s;
        if(generationInFlight && StudioFailureNotice.isFailure(s)){
            showFailure(s);
            return;
        }''')

patch('''    private void busy(boolean b) {
        running=b;
        ui.post(() -> {
            generate.setEnabled(!b);pick.setEnabled(!b);pickTwo.setEnabled(!b);
            durationBar.setEnabled(!b);
            waitingCard.setVisibility(b?View.VISIBLE:View.GONE);
            if(b){ambient.start();waitingHeading.setText("מכינים את הסצנה...");}
            else ambient.stop();
        });
    }''',
      '''    private void busy(boolean b) {
        boolean interruptedWithoutResult=!b && generationInFlight && resultFile==null && !stopping;
        running=b;
        ui.post(() -> {
            generate.setEnabled(!b);pick.setEnabled(!b);pickTwo.setEnabled(!b);
            durationBar.setEnabled(!b);
            waitingCard.setVisibility(b?View.VISIBLE:View.GONE);
            if(b){
                failureCard.setVisibility(View.GONE);
                ambient.start();waitingHeading.setText("מכינים את הסצנה...");
            }else{
                ambient.stop();
                if(interruptedWithoutResult && generationInFlight)
                    showFailureUi("ההפקה הסתיימה ללא קובץ וידאו תקין.");
            }
        });
    }
    private void showFailure(String technical){
        generationInFlight=false;
        String explanation=(technical==null?"שגיאה לא ידועה.":technical);
        lastPhaseDetail=explanation;
        ui.post(() -> showFailureUi(explanation));
    }
    private void showFailureUi(String technical){
        if(stopping||failureCard==null)return;
        generationInFlight=false;
        running=false;
        waitingCard.setVisibility(View.GONE);
        ambient.stop();
        generate.setEnabled(true);
        pick.setEnabled(true);pickTwo.setEnabled(true);
        durationBar.setEnabled(true);
        failureHeading.setText(StudioFailureNotice.title(technical));
        failureSubtitle.setText("לא נוצר סרטון. אפשר לנסות שוב או לפתוח פרטים נוספים.");
        failureCard.setVisibility(View.VISIBLE);
        status.setText("לא נוצר סרטון");
        lastPhaseDetail=technical;
        studioScroll.post(() -> studioScroll.smoothScrollTo(
            0,Math.max(0,failureCard.getTop()-dp(40))));
    }''')

patch('''        if(running)return;
        identityReviewRequired=(second!=null);''',
      '''        if(running)return;
        generationInFlight=true;
        identityReviewRequired=(second!=null);''')

patch('''        resultFile=file;
        final boolean unverified=identityReviewRequired;''',
      '''        generationInFlight=false;
        resultFile=file;
        final boolean unverified=identityReviewRequired;''')

patch('''            message("הסרטון יצא קצר מדי. אפשר לראות פרטים נוספים.");
            busy(false);''',
      '''            showFailure("הסרטון יצא קצר מדי: "+error.getMessage());
            busy(false);''')

main.write_text(s,encoding='utf-8')
assert 'private volatile boolean generationInFlight=false;' in s
assert 'showFailureUi("ההפקה הסתיימה ללא קובץ וידאו תקין.")' in s
assert 'retryCreation.setOnClickListener(v -> createVideo())' in s
assert 'generationInFlight=false;\n        resultFile=file;' in s
print('PASS v407 failure UI catches silent exits, quota failures and invalid durations')
