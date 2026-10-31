"""Kolbo Storyboard Studio: original frame-by-frame 2D animated MP4.

No static-slide trick: every frame includes character motion, lips synced to
the vocal envelope, gestures, moving props, camera parallax and transitions.
Meaning-based scenes require an actual transcript; otherwise the storyboard
honestly uses a music-and-voice-reactive concept instead of invented words.
"""
import json, math, os, re, subprocess
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SIZE=(360,640)
FPS=10
PALETTES=((14,11,43),(22,20,64),(9,33,51),(42,15,49),(20,35,51))
HEBREW={
    'car': ('רכב','מכונית','אוטו','נהג','משאית','כביש','לנסוע','נסיעה','מנוע'),
    'home': ('בית','דירה','חדר','משפחה','סלון','מטבח','חזרתי'),
    'water': ('מים','ים','בריכה','נהר','נחל','גשם','מקלחת'),
    'animal': ('חמור','כלב','חתול','אריה','סוס','ציפור','פרה','חיה'),
    'food': ('אוכל','לאכול','רעב','פיצה','בשר','חומוס','לחם','ארוחה'),
    'love': ('אהבה','אוהב','נשיקה','חיבוק','לב','מתגעגע'),
    'music': ('מוזיקה','שיר','שרים','טראנס','מיקס','ריקוד','לרקוד','מסיבה'),
    'money': ('כסף','שקל','משכורת','מחיר','עבודה','לקנות','קניתי'),
    'sport': ('כדור','כדורגל','משחק','לרוץ','לקפוץ','גול')
}
LABELS={'car':'בדרך','home':'בבית','water':'מים ותנועה','animal':'חיות',
        'food':'זמן לאכול','love':'אהבה','music':'המסיבה מתחילה',
        'money':'עסקים','sport':'אקשן','party':'טראנס וקול'}
def storyboard(transcript, duration, max_scenes=10):
    """Split an actual Hebrew transcript into grounded scene directions.

    No transcript -> music-reactive story, explicitly tagged untranscribed.
    """
    duration=float(duration)
    if not .5<=duration<=360:raise ValueError('video duration is invalid')
    clean=re.sub(r'[\\x00-\\x1f]',' ',str(transcript or ''))[:4000].strip()
    sentences=[v.strip() for v in re.split(r'[.!?;\\n]+',clean) if v.strip()]
    if not sentences:
        count=min(max_scenes,max(2,int(math.ceil(duration/7))))
        scenes=[{'start':round(i*duration/count,2),'end':round((i+1)*duration/count,2),
                 'kind':'party','caption':'','basis':'audio_reactive'}
                for i in range(count)]
        return {'source':'audio_reactive_no_transcript','transcript':'','scenes':scenes}
    if len(sentences)>max_scenes:
        step=math.ceil(len(sentences)/max_scenes)
        sentences=[' '.join(sentences[i:i+step]) for i in range(0,len(sentences),step)]
    weights=[max(1,len(v.split())) for v in sentences]
    weight_sum=sum(weights)
    time=0.;scenes=[]
    for i,(sentence,weight) in enumerate(zip(sentences,weights)):
        end=duration if i==len(sentences)-1 else time+duration*weight/weight_sum
        matches={}
        for kind,words in HEBREW.items():
            matches[kind]=sum(1 for word in words if word in sentence)
        kind=max(matches,key=matches.get) if max(matches.values())>0 else 'party'
        scenes.append({'start':round(time,2),'end':round(end,2),'kind':kind,
                       'caption':sentence[:100],'basis':'provided_transcript'})
        time=end
    return {'source':'provided_transcript_approximate_timing',
            'transcript':clean,'scenes':scenes}

def _color(rgb,amount):
    return tuple(max(0,min(255,int(c*amount))) for c in rgb)
def _circle(d,xy,r,fill,outline=None,width=2):
    d.ellipse((int(xy[0]-r),int(xy[1]-r),int(xy[0]+r),int(xy[1]+r)),
              fill=fill,outline=outline,width=width)
def _font(size):
    for path in ('/usr/share/fonts/truetype/noto/NotoSansHebrew-Bold.ttf',
                 '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        if os.path.exists(path):
            try:return ImageFont.truetype(path,size)
            except OSError:pass
    return ImageFont.load_default()

def _character(d,x,y,t,energy,kind,color,scale=1):
    """Articulated original vector character; explicit animation per frame."""
    swing=math.sin(t*6)*int(7*scale)*(0.25+energy)
    bob=math.sin(t*9)*(2+9*energy)*scale
    x=float(x);y=float(y+bob);r=25*scale
    body_top=y+25*scale;body_bottom=y+106*scale
    # legs with walking/dancing cadence
    for j,dx in enumerate((-12,12)):
        stride=math.sin(t*8+j*math.pi)*(7+17*energy)*scale
        d.line((int(x+dx),int(body_bottom),int(x+dx+stride),int(body_bottom+43*scale)),
               fill=(240,220,255),width=max(3,int(9*scale)))
        _circle(d,(x+dx+stride,y+151*scale),9*scale,(247,153,227))
    d.rounded_rectangle((int(x-24*scale),int(body_top),int(x+24*scale),int(body_bottom)),
                        radius=int(17*scale),fill=color)
    for dx,sign in ((-20,-1),(20,1)):
        d.line((int(x+dx),int(y+53*scale),
                int(x+dx+sign*(17+swing)*scale),int(y+91*scale-14*energy)),
               fill=color,width=max(3,int(10*scale)))
        _circle(d,(x+dx+sign*(17+swing)*scale,y+91*scale-14*energy),
                6*scale,(247,215,238))
    _circle(d,(x,y),r,(251,214,183))
    for dx in (-9,9):_circle(d,(x+dx*scale,y-5*scale),2.7*scale,(26,22,44))
    mouth=max(2,4+energy*12)*scale
    d.ellipse((int(x-7*scale),int(y+8*scale),
               int(x+7*scale),int(y+8*scale+mouth)),fill=(111,30,67))
    if kind=='animal':
        _circle(d,(x-20*scale,y-20*scale),9*scale,(251,214,183))
        _circle(d,(x+20*scale,y-20*scale),9*scale,(251,214,183))

def _scene_props(d,kind,t,energy):
    shift=math.sin(t*1.4)*8
    if kind=='car':
        d.rounded_rectangle((61+shift,408,302+shift,468),radius=20,fill=(244,95,141))
        d.polygon(((97+shift,405),(129+shift,374),(240+shift,374),(273+shift,405)),
                  fill=(87,188,235))
        for x in (111+shift,254+shift):_circle(d,(x,472),20,(18,25,55))
        for x in (43,118,197,272):
            off=(t*110)%75
            d.line((int((x-off)%400),511,int((x+27-off)%400),511),
                   fill=(255,227,120),width=5)
    elif kind=='water':
        for j in range(4):
            pts=[(x,int(466+j*17+9*math.sin((x/42)+t*2.1+j)))
                 for x in range(0,361,8)]
            d.line(pts,fill=(29+32*j,182,245),width=7)
        for j in range(6):
            x=(j*67+t*22)%360;y=395+(j*29)%82
            _circle(d,(x,y+math.sin(t*3+j)*8),3+j%3,(180,236,255))
    elif kind=='home':
        d.polygon(((35,401),(178,292+shift),(325,401)),fill=(235,125,153))
        d.rectangle((72,394,288,508),fill=(246,190,118))
        d.rectangle((158,444,199,508),fill=(89,65,101))
        d.rectangle((91,417,130,449),fill=(79,196,240))
    elif kind=='animal':
        d.ellipse((76,387+shift,282,468+shift),fill=(189,153,116))
        d.ellipse((225,348+shift,308,422+shift),fill=(204,169,135))
        for k in (120,230):d.line((k,458+shift,k-11,502),fill=(189,153,116),width=13)
        _circle(d,(284,369+shift),4,(21,24,34))
    elif kind=='food':
        d.ellipse((85,387,278,493),fill=(243,234,238))
        d.polygon(((109,408),(210,380+shift),(253,463)),fill=(246,184,59))
        for px,py in ((177,416),(202,438),(170,452)):
            _circle(d,(px,py),10,(207,64,69))
    elif kind=='love':
        for j in range(5):
            xx=45+j*65+15*math.sin(t+j);yy=410+23*math.sin(t*2+j)
            d.polygon(((xx,yy+12),(xx-17,yy-1),(xx-12,yy-17),
                       (xx,yy-7),(xx+12,yy-17),(xx+17,yy-1)),
                      fill=(248,69,131))
    elif kind=='money':
        for j in range(5):
            xx=45+j*65;yy=425+15*math.sin(t*2+j)
            d.ellipse((xx-20,yy-20,xx+20,yy+20),fill=(255,199,75),
                      outline=(255,245,197),width=3)
            d.line((xx,yy-12,xx,yy+12),fill=(157,92,37),width=4)
    elif kind=='sport':
        cx=int(178+110*math.sin(t*2))
        cy=int(440-abs(math.sin(t*4))*115)
        _circle(d,(cx,cy),28,(243,244,255),outline=(43,58,93),width=4)
        _circle(d,(cx,cy),11,(38,56,98))
    else:
        for j in range(4):
            x=42+j*83
            height=43+45*energy+25*math.sin(t*4+j)
            d.rounded_rectangle((x,488-height,x+26,488),radius=7,
                                fill=((86+25*j)%250,130+15*j,247-18*j))
        for j in range(8):
            x=int((j*51+math.sin(t*.8+j)*32)%360)
            y=int(350+44*math.sin(t*2+j))
            _circle(d,(x,y),3+j%3,(247,179,243))

def render_frame(time,story,energy,frame_index):
    w,h=SIZE
    current=next((s for s in story['scenes'] if s['start']<=time<s['end']),
                 story['scenes'][-1])
    kind=current['kind']
    section=next((i for i,s in enumerate(story['scenes']) if s is current),0)
    bg=PALETTES[section%len(PALETTES)]
    im=Image.new('RGB',SIZE,bg)
    d=ImageDraw.Draw(im)
    # Constant per-frame camera/parallax motion, including during speech pauses.
    for j in range(7):
        xx=(j*77+math.sin(time*.23+j)*35)%420-30
        yy=55+j*57+math.sin(time*.47+j)*19
        _circle(d,(xx,yy),18+j*4,_color(bg,1.25+j*.12))
    d.rounded_rectangle((18,22,w-18,93),radius=23,fill=(32,30,69))
    d.text((w//2,55),'KOLBO · TRANCE STORY',font=_font(19),
           fill=(240,219,251),anchor='mm')
    phase=time-current['start']
    # Eye, body, hands and lips move at *every* frame, not just crossfades.
    _scene_props(d,kind,time,energy)
    _character(d,115,249,time,energy,kind,(88,162,245),scale=.92)
    _character(d,246,263,time+1.3,energy*.78,kind,(224,85,157),scale=.80)
    if current['caption']:
        caption=current['caption'][:42]
    else:
        caption=LABELS[kind]
    d.rounded_rectangle((22,545,w-22,603),radius=17,fill=(33,26,73))
    try:
        d.text((w//2,571),caption,font=_font(22),anchor='mm',
               fill=(255,250,254),direction='rtl',stroke_width=0)
    except (ValueError,KeyError,TypeError):
        d.text((w//2,571),caption,font=_font(20),anchor='mm',fill=(255,250,254))
    # Simple moving progress meter and beat flash.
    progress=min(1,max(0,time/max(1,story['scenes'][-1]['end'])))
    d.rounded_rectangle((25,614,335,621),radius=3,fill=(67,59,113))
    d.rounded_rectangle((25,614,25+max(1,int(310*progress)),621),
                        radius=3,fill=(234,132,246))
    if energy>.17:
        pulse=3+energy*8
        _circle(d,(180,123),pulse,(236,182,253))
    return im

def export_animation(mp3_path,mp4_path,story,audio,voice,sr=32000,
                     progress=None,width=360,height=640,fps=10):
    """Stream frames without buffering the full film in RAM."""
    if (width,height)!=(360,640):raise ValueError('unsupported profile')
    if not 6<=fps<=15:raise ValueError('unsupported fps')
    total=len(audio)/sr
    if not .5<=total<=360:raise ValueError('unsupported duration')
    total_frames=max(1,int(math.ceil(total*fps)))
    # Envelope comes only from SPOKEN VOICE, not the instrumental.
    e=np.asarray(voice,dtype=np.float32)
    if len(e)!=len(audio):raise ValueError('voice alignment mismatch')
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y',
         '-f','rawvideo','-pix_fmt','rgb24','-s','360x640',
         '-r',str(fps),'-i','pipe:0','-i',str(mp3_path),
         '-map','0:v:0','-map','1:a:0',
         '-c:v','libx264','-preset','ultrafast','-crf','27',
         '-pix_fmt','yuv420p','-c:a','aac','-b:a','160k',
         '-movflags','+faststart','-shortest',str(mp4_path)]
    process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,
                             stderr=subprocess.PIPE)
    try:
        for frame in range(total_frames):
            t=frame/fps
            lo=int(t*sr);hi=min(len(e),lo+max(1,int(.09*sr)))
            strength=float(np.sqrt(np.mean(e[lo:hi]**2))) if hi>lo else 0.
            energy=min(1.,strength*5.4)
            im=render_frame(t,story,energy,frame)
            process.stdin.write(im.tobytes())
            if progress and frame%max(1,total_frames//20)==0:
                progress(91+min(7,int(7*frame/max(1,total_frames))),
                         'מנפיש את הסטוריבורד ומפיק MP4')
        process.stdin.close()
        process.stdin=None
        _,stderr=process.communicate(timeout=180)
        if process.returncode:
            raise RuntimeError('FFmpeg animation encoding: '+stderr[-400:].decode(errors='replace'))
        p=Path(mp4_path)
        if not p.exists() or p.stat().st_size<1000:raise RuntimeError('empty video')
        return p
    except Exception:
        if process.poll() is None:process.kill()
        process.communicate()
        raise
