from pathlib import Path
import shutil,sys
root=Path(sys.argv[1])
base=root/'app/src/main/java/com/kolbo/videostudio'
main=base/'MainActivity.java'
gradle=root/'app/build.gradle'
s=main.read_text(encoding='utf-8')
def once(old,new):
    global s
    matches=s.count(old)
    if matches!=1:raise SystemExit(f'Expected one {old[:105]!r} but found {matches}')
    s=s.replace(old,new,1)

shutil.copyfile('patches/VideoEvidenceAudit.java',base/'VideoEvidenceAudit.java')

once('private volatile int expectedDuration=8;',
    '''private volatile int expectedDuration=8;
    private volatile String lastQualityEvidence="";
    private volatile String lastQualityHeadline="הסרטון מוכן לבדיקה";''')
once('lastSubmittedPrompt="";originalForDiagnostics=instruction;',
    'lastSubmittedPrompt="";originalForDiagnostics=instruction;lastQualityEvidence="";')
once('''        resultFile=file;
        final boolean unverified=identityReviewRequired;''',
    '''        String quality="הסרטון מוכן לבדיקה";
        try {
            VideoEvidenceAudit.Result evidence=VideoEvidenceAudit.inspect(
                file,expectedDuration,identityReviewRequired,
                VideoEvidenceAuditRequest.requiresSinging(originalForDiagnostics));
            lastQualityEvidence=evidence.details();
            quality=evidence.status();
        } catch(Exception qaFailure){
            lastQualityEvidence="לא ניתן לבצע בדיקת ראיות: "+qaFailure.getMessage()
                +"\\nאורך הסרטון אומת בנפרד. זהות הדמויות וביצוע ההנחיה לא אומתו.";
            quality="הסרטון מוכן לבדיקה";
        }
        final String qualityHeadline=quality;
        lastQualityHeadline=quality;
        resultFile=file;
        final boolean unverified=identityReviewRequired;''')
once('lastPhaseDetail=displayNotice;\n            status.setText(unverified?"הסרטון מוכן לבדיקה":"הסרטון מוכן");',
    'lastPhaseDetail=displayNotice+"\\n\\n"+lastQualityEvidence;\n            status.setText(qualityHeadline);')
# Make the UI explicit about intended duration without showing detailed log.
once('resultCard.setVisibility(View.VISIBLE);\n            studioScroll.post',
    '''resultCard.setVisibility(View.VISIBLE);
            download.setContentDescription("שמור סרטון "+expectedDuration+
                " שניות. זהות הדמויות והפעולות לא אומתו.");
            studioScroll.post''')
# Add an accessible, collapsible per-video evidence detail via existing UI.
once('String detail=SceneIntentContract.from(request).reviewHebrew()+"\\n"',
    'String detail=SceneIntentContract.from(request).reviewHebrew()+"\\n"')
once('+(previous.isEmpty()?"עדיין אין הנחיה שנשלחה למנוע.":previous);',
    '+(previous.isEmpty()?"עדיין אין הנחיה שנשלחה למנוע.":previous)\n                +"\\n\\nדוח בדיקת הסרטון:\\n"+(lastQualityEvidence.isEmpty()?"טרם הופק סרטון לבדיקה.":lastQualityEvidence);')
# No reattempt on exhausted quotas or a failed identity presence audit.
# Preserve quality info even when TTS is absent.
shutil.copyfile('patches/VideoEvidenceAuditRequest.java',base/'VideoEvidenceAuditRequest.java')
main.write_text(s,encoding='utf-8')
g=gradle.read_text(encoding='utf-8')
for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview406'","applicationId 'com.kolbo.videostudio.preview407'"),
    ("versionCode 406","versionCode 407"),
    ("versionName '4.0.6'","versionName '4.0.7'")
]:
    if g.count(old)!=1:raise SystemExit(f'Version key missing {old}')
    g=g.replace(old,new)
gradle.write_text(g,encoding='utf-8')
assert 'VideoEvidenceAudit.inspect(' in s
assert 'lastQualityEvidence=evidence.details()' in s
assert 'status.setText(qualityHeadline)' in s
print('PASS v407: native offline evidence QA in simple delivery UI')
