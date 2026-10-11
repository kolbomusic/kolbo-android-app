"""CPU-generated sound effects for fully local Kolbo photo video (NO voices).

Illustrative synthetic sound textures, NOT singing, language, lip-sync or
reproduction of events involving a photographed person. No third-party
downloads, pretrained model, copyrighted recording or API usage.
"""
from __future__ import annotations
import math
from pathlib import Path
import random
import re
import struct
import wave

RATE=16000
MAX_SECONDS=12
SFX_KIND=("fart","rain","applause","bird","none")

FART=re.compile(r"(?:\b(?:fart|farts|farting|flatulence)\b|מפליצ|מפליץ|פליצ|נפיח|פלוץ)",re.I)
RAIN=re.compile(r"(?:\b(?:rain|raining|raindrops)\b|גשם|גשמי|טיפות גשם)",re.I)
CLAP=re.compile(r"(?:\b(?:clap|clapping|applause)\b|מחיאות כפיים|מוחאים כפיים|כפיים)",re.I)
BIRD=re.compile(r"(?:\b(?:birdsong|chirp|chirping|tweeting)\b|ציוץ|ציפורים מצייצות)",re.I)

def recognize(text:str)->str:
    """Recognizes very narrow effects, NOT general-language intent."""
    if not isinstance(text,str) or len(text)>3000:
        raise ValueError("Invalid effect description")
    stripped=re.sub(r"(?:\b(?:no|without)\s+(?:sound|fart|rain|applause|birdsongs?|sfx)\b|"
                    r"(?:בלי|ללא)\s+(?:קול|קולות|צלילי?|אפקט|רעשים|סאונד|גשם|נפיחות))",
                    " ",text,flags=re.I)
    for name,pattern in (("fart",FART),("rain",RAIN),
                         ("applause",CLAP),("bird",BIRD)):
        if pattern.search(stripped):
            return name
    return "none"

def synthesize(path:Path,*,seconds:int,kind:str)->None:
    if type(seconds) is not int or not 2<=seconds<=MAX_SECONDS:
        raise ValueError("SFX duration must be 2–12 s")
    if kind not in SFX_KIND or kind=="none":
        raise ValueError("One explicit sound effect is required")
    if path.exists():
        raise ValueError("Cannot overwrite an existing sound")
    random_source=random.Random(108241)
    samples=seconds*RATE
    pcm=bytearray(samples*2)
    last_noise=0.0
    # Controlled waveform dynamics, synth and fades. No real speech or music.
    for i in range(samples):
        t=i/RATE
        v=0.0
        if kind=="fart":
            # A short, wobbling low oscillator with air turbulence.
            distance=abs(t - min(seconds*0.52,2.0))
            if distance<0.78:
                env=(1.0 - distance/0.78)**1.3
                pitch=64+22*math.sin(2*math.pi*4.1*t)+6*math.sin(2*math.pi*14*t)
                noisy=random_source.uniform(-1,1)
                last_noise=last_noise*0.93+noisy*0.07
                v=env*(0.38*math.sin(2*math.pi*pitch*t)+0.27*last_noise)
        elif kind=="rain":
            noisy=random_source.uniform(-1,1)
            last_noise=last_noise*0.985+noisy*0.015
            v=0.26*(noisy-last_noise)
            # occasional pseudo-drops; no source material or audio assets.
            pulse=((i*1103515245 + 12345)%32768)<40
            if pulse:v+=0.16*random_source.uniform(-1,1)
        elif kind=="applause":
            phase=t%0.19
            if phase<0.032:
                envelope=(1.0-phase/0.032)**1.4
                v=0.38*random_source.uniform(-1,1)*envelope
        elif kind=="bird":
            # High, warbling multi-chirp: not a particular species.
            chirp=t%0.88
            if 0.10<chirp<0.36:
                u=(chirp-0.10)/0.26
                freq=980+660*u
                v=0.25*math.sin(2*math.pi*(980*t+600*u*u))*math.sin(math.pi*u)
        fade=min(1.0,t/0.07,(seconds-t)/0.07)
        sample=int(max(-0.85,min(0.85,v*max(0.0,fade)))*26000)
        struct.pack_into("<h",pcm,i*2,sample)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with path.open("xb") as raw:
        with wave.open(raw,"wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(pcm)
