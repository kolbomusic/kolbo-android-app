package com.kolbo.videostudio;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

/**
 * Deterministic, on-device planning of short video actions.
 * A lightweight baseline, NOT a general-purpose Hebrew language model.
 * Unknown actions are preserved verbatim rather than silently invented.
 */
public final class StoryboardPlanner {
    private StoryboardPlanner() {}
    private static final Pattern SEQUENCE = Pattern.compile(
        "(?iu)\\s+(?:and\\s+then|after\\s+that|afterwards|next|finally|then|later|meanwhile|"
        + "לאחר\\s+מכן|אחר\\s+כך|ואז|בהמשך|ולבסוף|לבסוף|בסוף|ואחר\\s+כך)\\s+");
    private static final Pattern CLAUSE = Pattern.compile("\\s*[,;.!?؛،]+\\s*");
    private static final Pattern TAIL = Pattern.compile("(?iu)^(?:and\\s+|ו?אז\\s+|then\\s+|ו?לאחר\\s+מכן\\s+)+");
    private static final int MAX_SCENES = 8;
    public static final class Scene {
        public final int index;
        public final String action;
        public final int seconds;
        public Scene(int n, String action, int seconds) {
            this.index=n;this.action=action;this.seconds=seconds;
        }
    }
    public static final class Plan {
        public final List<Scene> scenes;
        public final boolean reduced;
        public final int requestedSeconds;
        Plan(List<Scene> scenes,boolean reduced,int requestedSeconds) {
            this.scenes=Collections.unmodifiableList(scenes);
            this.reduced=reduced;this.requestedSeconds=requestedSeconds;
        }
        public String preview() {
            StringBuilder b=new StringBuilder();
            for(Scene s:scenes) {
                b.append(s.index).append(". ").append(s.action).append(" (").append(s.seconds).append(" שניות)\n");
            }
            if(reduced)b.append("חלק מהפעולות אוחדו כי משך הסרטון קצר.\n");
            b.append("המעברים ואיכות הביצוע אינם מובטחים; זו תוכנית הפקה, לא אימות תוצאה.");
            return b.toString();
        }
    }

    /** Returns a plan preserving source phrases and their chronological order. */
    public static Plan plan(String instruction,int durationSeconds) {
        if(instruction==null||instruction.trim().isEmpty())
            throw new IllegalArgumentException("missing instruction");
        if(durationSeconds<1||durationSeconds>60)
            throw new IllegalArgumentException("duration must be 1..60");
        List<String> clauses = new ArrayList<>();
        String normalized=instruction.replace('\r',' ').replace('\n',' ').trim();
        for(String section:SEQUENCE.split(normalized)) {
            for(String atom:CLAUSE.split(section)) {
                String cleaned=TAIL.matcher(atom.trim()).replaceFirst("").trim();
                if(cleaned.length()>=2)clauses.add(cleaned);
            }
        }
        if(clauses.isEmpty())clauses.add(normalized);
        // Preserve every action even when the requested duration is too short.
        int maxScenes=Math.max(1,Math.min(MAX_SCENES,durationSeconds/2));
        boolean reduced=clauses.size()>maxScenes;
        if(reduced) {
            List<String> compact=new ArrayList<>();
            for(int i=0;i<maxScenes-1;i++)compact.add(clauses.get(i));
            StringBuilder last=new StringBuilder();
            for(int i=maxScenes-1;i<clauses.size();i++){
                if(last.length()>0)last.append("; then ");
                last.append(clauses.get(i));
            }
            compact.add(last.toString());
            clauses=compact;
        }
        // Allocate >=1 second per scene, sum exactly equals user duration.
        int n=clauses.size(),basic=durationSeconds/n,remainder=durationSeconds%n;
        List<Scene> result=new ArrayList<>();
        for(int i=0;i<n;i++)
            result.add(new Scene(i+1,clauses.get(i),basic+(i<remainder?1:0)));
        return new Plan(result,reduced,durationSeconds);
    }
    public static String stagePrompt(Scene scene,int totalStages,boolean twoSubjects) {
        String identity=twoSubjects
            ?"Image 1 is person A, Image 2 is person B. Use these same two people in one continuous physical setting. "
             +"Do not remove, replace, merge, duplicate, swap identities or invent extra people. "
            :"Preserve the characters, appearance and physical setting of the input.";
        String task="Storyboard shot "+scene.index+" of "+totalStages+". "
            +"During THIS shot, visibly execute this exact action: "+scene.action+". "
            +"Show the action on screen, not a reaction, an unrelated pose, or a still portrait. "
            +"Ensure causality, physical interactions and object placement are plausible. "
            +"Maintain continuity of clothing, scale and location. "
            +"No English captions unless explicitly requested.";
        return identity+task;
    }
}
