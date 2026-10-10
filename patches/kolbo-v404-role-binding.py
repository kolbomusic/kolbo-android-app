from pathlib import Path
import sys, shutil, re
root=Path(sys.argv[1])
base=root/'app/src/main/java/com/kolbo/videostudio'
main=base/'MainActivity.java'
planner=base/'StoryboardPlanner.java'
gradle=root/'app/build.gradle'
s=main.read_text(encoding='utf-8')

def replace_once(needle,replacement):
    global s
    count=s.count(needle)
    if count!=1:
        raise SystemExit(f'v404 patch expects one match for {needle[:130]!r}, got {count}')
    s=s.replace(needle,replacement,1)

replace_once('StoryboardPlanner.plan(instruction,desired).preview()',
             'CharacterRoleContract.from(instruction).preview()+"\\n"+StoryboardPlanner.plan(instruction,desired).preview()')
# This block previously repeated the entire story in every shot, causing the
# model to prioritize the setting (police) over who arrests whom.
before='''                String common="Generate one cinematic shared scene with exactly TWO distinct characters. "
                    +"Image 1 is character 1; Image 2 is character 2. Preserve visual attributes and clothing "
                    +"of EACH corresponding original person, never swap identities, duplicate a subject, "
                    +"invent an additional person or replace either subject with a uniformed actor. "
                    +"Keep both in one location and show both performing the requested actions. "
                    +(wantsGroupDance(originalInstruction)?
                      "Both people dance together with visibly moving legs, feet and arms. ":"")
                    +(originalRequestIsBukharianSinging(originalInstruction)?
                      "Both sing in the Bukhori language, without English dialogue. ":"")
                    +translatedPrompt;'''
after='''                CharacterRoleContract roleLock=CharacterRoleContract.from(originalInstruction);
                // Reference-image association and action roles are LOCKED across every shot.
                // Never prepend the complete story to each scene.
                String styleConstraints="Film both distinct people in ONE coherent physical location. "
                    +(wantsGroupDance(originalInstruction)?
                      "If the scene demands dancing, show coordinated full-body movement. ":"")
                    +(originalRequestIsBukharianSinging(originalInstruction)?
                      "If the scene demands singing, the target language is Bukhori, not English. ":"");'''
replace_once(before,after)
replace_once('String scenePrompt=common+" "+StoryboardPlanner.stagePrompt(scene,plan.scenes.size(),true);',
             '''String scenePrompt=styleConstraints+roleLock.prompt(scene.action,scene.index,plan.scenes.size());
                        if(scene.index>1)scenePrompt+="This shot follows the previous action: "
                            +plan.scenes.get(scene.index-2).action+". Keep the physical setup consistent. ";''')
# Inform the user of *unverified* roles and of identity ambiguity.
replace_once('String review="הופקו "+plan.scenes.size()+" שלבי תוכנית. זהות האנשים, רצף הפעולות, תנועת השפתיים ושפת השירה לא אומתו. ייתכנו מעברים לא רציפים.";',
             'String review="הופקו "+plan.scenes.size()+" מקטעי תוכנית עם נעילת תפקידים בהנחיה בלבד. אין בדיקה אוטומטית אמינה שמזהה מי פעל על מי או האם נשמרה זהות הפנים; התוצאה טיוטה לביקורת בלבד.";')
# No fabricated identity-match PASS. Face-count checks still run.
shutil.copyfile('patches/CharacterRoleContract.java',base/'CharacterRoleContract.java')
main.write_text(s,encoding='utf-8')

plan_source=planner.read_text(encoding='utf-8')
find='''        for(String section:SEQUENCE.split(normalized)) {
            for(String atom:CLAUSE.split(section)) {
                String cleaned=TAIL.matcher(atom.trim()).replaceFirst("").trim();
                if(cleaned.length()>=2)clauses.add(cleaned);
            }
        }'''
swap='''        for(String section:SEQUENCE.split(normalized)) {
            for(String atom:CLAUSE.split(section)) {
                // Explicit "and then" + common action transitions in both languages.
                // This is a heuristic, not a full natural-language parser.
                for(String partial:ENGLISH_ACTION_BREAK.split(atom)) {
                    for(String step:HEBREW_ACTION_BREAK.split(partial)) {
                        String cleaned=TAIL.matcher(step.trim()).replaceFirst("").trim();
                        if(cleaned.length()>=2)clauses.add(cleaned);
                    }
                }
            }
        }'''
if plan_source.count(find)!=1:raise SystemExit('Storyboard extraction block changed')
plan_source=plan_source.replace(find,swap,1)
# Merge a bare actor label with its action, rather than generating a shot of
# "character 1" alone. The scanner may split before the very first verb.
anchor_context='        if(clauses.isEmpty())clauses.add(normalized);'
replacement_context='''        if(clauses.size()>1 && clauses.get(0).trim().matches("(?iu)(?:דמות|character|person|subject)\\s*[12]")) {
            clauses.set(1,clauses.get(0)+" "+clauses.get(1));
            clauses.remove(0);
        }
        if(clauses.isEmpty())clauses.add(normalized);'''
if plan_source.count(anchor_context)!=1:raise SystemExit('Initial actor context location changed')
plan_source=plan_source.replace(anchor_context,replacement_context,1)
anchor='''    private static final int MAX_SCENES = 8;'''
insertion='''    // Split only on likely *new actions*; never split every Hebrew prefixed vav.
    private static final Pattern HEBREW_ACTION_BREAK = Pattern.compile(
        "(?iu)\\\\s+(?=(?:ו?(?:מכניס(?:ה|ים|ות)?|נוסע(?:ת|ים|ות)?|"
        +"עוצר(?:ת|ים|ות)?|נכנס(?:ת|ים|ות)?|יוצא(?:ת|ים|ות)?|"
        +"פותח(?:ת|ים|ות)?|סוגר(?:ת|ים|ות)?|"
        +"מוביל(?:ה|ים|ות)?|לוקח(?:ת|ים|ות)?|"
        +"תופס(?:ת|ים|ות)?|ניגש(?:ת|ים|ות)?|"
        +"רוקד(?:ת|ים|ות)?|מתחיל(?:ה|ים|ות)?|"
        +"מתיישב(?:ת|ים|ות)?|מחייכ(?:ת|ים|ות)?|"
        +"מצלם(?:ת|ים|ות)?|מפעיל(?:ה|ים|ות)?|"
        +"עולה|יורד(?:ת|ים|ות)?|מתרחק(?:ת|ים|ות)?))(?=\\\\s|$))");
    private static final Pattern ENGLISH_ACTION_BREAK = Pattern.compile(
        "(?iu)\\\\s+(?:and\\\\s+)?(?=(?:drives?|walks?|runs?|opens?|closes?|"
        +"enters?|exits?|arrests?|escorts?|puts?|loads?|takes?|"
        +"starts?|smiles?|dances?|sings?|turns?|stops?)\\\\s)");
'''+anchor
if plan_source.count(anchor)!=1:raise SystemExit('Storyboard planner header changed')
plan_source=plan_source.replace(anchor,insertion,1)
# Restore actor subject context to short clauses: the role contract does the binding,
# so we leave actions verbatim instead of hallucinating the object's profession.
planner.write_text(plan_source,encoding='utf-8')

g=gradle.read_text(encoding='utf-8')
for needle,new in [
    ("applicationId 'com.kolbo.videostudio.preview403'","applicationId 'com.kolbo.videostudio.preview404'"),
    ("versionCode 403","versionCode 404"),
    ("versionName '4.0.3'","versionName '4.0.4'")
]:
    if g.count(needle)!=1:raise SystemExit('Gradle metadata mismatch '+needle)
    g=g.replace(needle,new,1)
gradle.write_text(g,encoding='utf-8')
assert 'CharacterRoleContract.from(originalInstruction)' in s
assert 'styleConstraints+roleLock.prompt(scene.action' in s
assert 'CharacterRoleContract.from(instruction).preview()' in s
assert 'String scenePrompt=common+' not in s
assert 'HEBREW_ACTION_BREAK.split(partial)' in plan_source
print('PASS v4.0.4 role binding and action-scoped prompts without repeating the whole story')
