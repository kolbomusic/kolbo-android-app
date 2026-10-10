from pathlib import Path
import shutil,sys
root=Path(sys.argv[1])
base=root/'app/src/main/java/com/kolbo/videostudio'
main=base/'MainActivity.java'
gradle=root/'app/build.gradle'
s=main.read_text(encoding='utf-8')

def change(old,new):
    global s
    count=s.count(old)
    if count!=1: raise SystemExit(f'v405 patch mismatch {count} for: {old[:115]!r}')
    s=s.replace(old,new,1)

# Reuse the source-local and request-scoped classes. Never draw unwanted
# visual concepts into the provider prompt from blanket negative phrases.
shutil.copyfile('patches/SceneIntentContract.java',base/'SceneIntentContract.java')
shutil.copyfile('patches/CharacterRoleContract.java',base/'CharacterRoleContract.java')

change('private Button generate, pick, pickTwo, download;',
       'private Button generate, pick, pickTwo, download, diagnostics;')
change('private volatile boolean useMultiReferenceProvider;',
       'private volatile boolean useMultiReferenceProvider;\n'
       '    private volatile String lastSubmittedPrompt="";\n'
       '    private volatile String originalForDiagnostics="";')
change('download = button("הורד MP4");download.setVisibility(View.GONE);root.addView(download);',
       'download = button("הורד MP4");download.setVisibility(View.GONE);root.addView(download);\n'
       '        diagnostics=button("אבחון ההנחיה שנשלחה");root.addView(diagnostics);\n'
       '        diagnostics.setOnClickListener(v -> {\n'
       '            String request=prompt.getText().toString().trim();\n'
       '            String previous=lastSubmittedPrompt;\n'
       '            String details="ההנחיה הנוכחית: "+request+"\\n\\n"\n'
       '                +SceneIntentContract.from(request).reviewHebrew()+"\\n"\n'
       '                +CharacterRoleContract.from(request).preview()+"\\n\\n"\n'
       '                +(previous.isEmpty()?"עדיין לא נשלחה הפקה במפגש הנוכחי.":"ההנחיה האחרונה שהוכנה לשליחה לספק:\\n"+previous);\n'
       '            new AlertDialog.Builder(this).setTitle("אבחון ההפקה").setMessage(details)\n'
       '                .setPositiveButton("סגור",(d,w)->{}).show();\n'
       '        });')
change('if(running)return;\n        identityReviewRequired=(second!=null);',
       'if(running)return;\n        identityReviewRequired=(second!=null);\n'
       '        lastSubmittedPrompt="";originalForDiagnostics=instruction;')
change('CharacterRoleContract.from(instruction).preview()+"\\n"+StoryboardPlanner.plan(instruction,desired).preview()',
       'SceneIntentContract.from(instruction).reviewHebrew()+"\\n"\n'
       '                    +CharacterRoleContract.from(instruction).preview()+"\\n"\n'
       '                    +StoryboardPlanner.plan(instruction,desired).preview()')
change('CharacterRoleContract roleLock=CharacterRoleContract.from(originalInstruction);',
       'CharacterRoleContract roleLock=CharacterRoleContract.from(originalInstruction);\n'
       '                SceneIntentContract sceneIntent=SceneIntentContract.from(originalInstruction);')
original='''                String styleConstraints="Film both distinct people in ONE coherent physical location. "
                    +(wantsGroupDance(originalInstruction)?
                      "If the scene demands dancing, show coordinated full-body movement. ":"")
                    +(originalRequestIsBukharianSinging(originalInstruction)?
                      "If the scene demands singing, the target language is Bukhori, not English. ":"");'''
replacement='''                // Use only this request's explicitly inferred SCENE.
                // In particular no globally injected police/uniform imagery!
                String styleConstraints="Preserve BOTH separate visual subjects from the references. "
                    +sceneIntent.sceneSetting()
                    +(originalRequestIsBukharianSinging(originalInstruction)?
                      "If singing is requested, use Bukhori rather than English lyrics. ":"");'''
change(original,replacement)
change('String scenePrompt=styleConstraints+roleLock.prompt(scene.action,scene.index,plan.scenes.size());',
       'String scenePrompt=styleConstraints+roleLock.prompt(scene.action,scene.index,plan.scenes.size());\n'
       '                        recordSubmittedPrompt("MSR reference slots 1+2",scenePrompt);')
change('String review="הופקו "+plan.scenes.size()+" מקטעי תוכנית עם נעילת תפקידים בהנחיה בלבד. אין בדיקה אוטומטית אמינה שמזהה מי פעל על מי או האם נשמרה זהות הפנים; התוצאה טיוטה לביקורת בלבד.";',
       'String review="הופקו "+plan.scenes.size()+" מקטעי תוכנית. "+sceneIntent.reviewHebrew()\n'
       '                    +" זהות הדמויות, הרקע, ביצוע הפעולות והצלילים לא אומתו חזותית או שמיעתית. טיוטה לבדיקה בלבד.";')
change('String chunkPrompt=plan.scenes.size()==1\n                            ?scenePrompt\n                            :StoryboardPlanner.stagePrompt(scene,plan.scenes.size(),second!=null);',
       'String chunkPrompt=plan.scenes.size()==1\n                            ?scenePrompt\n                            :StoryboardPlanner.stagePrompt(scene,plan.scenes.size(),second!=null);\n'
       '                        chunkPrompt=SceneIntentContract.from(originalInstruction).sceneSetting()+chunkPrompt;')
change('String event=submit(chunkPrompt,imageMeta,seconds);',
       'recordSubmittedPrompt("LTX base provider",chunkPrompt);\n'
       '                        String event=submit(chunkPrompt,imageMeta,seconds);')
change('private void startMSRVideo(String translatedPrompt,Uri first,Uri second,',
       '''private void recordSubmittedPrompt(String route,String compiled) {
        // Diagnostics lives only in this Activity memory; it is not sent elsewhere.
        String next="ספק: "+route+"\\nהנחיה:\\n"+compiled;
        lastSubmittedPrompt=next.length()>10000?next.substring(0,10000):next;
    }
    private void startMSRVideo(String translatedPrompt,Uri first,Uri second,''')
g=gradle.read_text(encoding='utf-8')
for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview404'","applicationId 'com.kolbo.videostudio.preview405'"),
    ("versionCode 404","versionCode 405"),
    ("versionName '4.0.4'","versionName '4.0.5'")
]:
    if g.count(old)!=1:raise SystemExit('Metadata expected one: '+old)
    g=g.replace(old,new,1)
gradle.write_text(g,encoding='utf-8')
main.write_text(s,encoding='utf-8')
assert 'sceneIntent.sceneSetting()' in s
assert 'recordSubmittedPrompt("MSR reference slots 1+2"' in s
assert 'recordSubmittedPrompt("LTX base provider"' in s
assert 'lastSubmittedPrompt="";originalForDiagnostics=instruction' in s
print('PASS v4.0.5: scene semantics isolated, request-scoped contract, diagnostic prompt visibility')
