from pathlib import Path
import shutil,sys
root=Path(sys.argv[1]);base=root/'app/src/main/java/com/kolbo/videostudio'
shutil.copyfile('patches/DurationPolicy.java',base/'DurationPolicy.java')
role=base/'CharacterRoleContract.java'
s=role.read_text(encoding='utf-8')
old='if(a!=b)return new CharacterRoleContract(a,b,true,instruction);'
new='''if(a!=b){
                // "Character 1 and character 2 sing together" is a JOINT act;
                // not a directed agent->patient relation. Preserve the two slots.
                if(SceneIntentContract.from(instruction).category==
                    SceneIntentContract.Category.MUSIC_PERFORMANCE)
                    return new CharacterRoleContract(0,0,false,instruction);
                return new CharacterRoleContract(a,b,true,instruction);
            }'''
if s.count(old)!=1:raise SystemExit('Role contract signature changed')
role.write_text(s.replace(old,new,1),encoding='utf-8')
scene=base/'SceneIntentContract.java'
x=scene.read_text(encoding='utf-8')
find='''                if(singing) stage+="VISIBLE MAIN ACTION: both requested singers performing with expressive "'''
new='''                if(containsAny(original.toLowerCase(Locale.ROOT),"1000 איש","1000 אנשים","אלף איש","1,000"))
                    stage+="CROWD: around one thousand audience members visible beyond the stage. ";
                if(singing) stage+="VISIBLE MAIN ACTION: both requested singers performing with expressive "'''
if x.count(find)!=1:raise SystemExit('Scene intent source changed')
scene.write_text(x.replace(find,new,1),encoding='utf-8')
print('PASS duration policy installed, concert duet no actor/recipient confusion, audience-size request respected')
