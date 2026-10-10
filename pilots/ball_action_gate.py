"""Explainable, deliberately conservative ball-bounce visual gate.

Checks visible reversals of an orange object's vertical path. Not a semantic
video-language model; camera motion, occlusion, stylized balls can fool it.
Only use with synthetic/orange-ball-on-meadow pilot, never generic people.
"""
from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np
from scipy.signal import savgol_filter, find_peaks


def detect_bounces(path:Path,expected_minimum:int=2)->dict:
    capture=cv2.VideoCapture(str(path))
    if not capture.isOpened():return {'pass':False,'reason':'VIDEO_DECODE_FAILED'}
    fps=float(capture.get(cv2.CAP_PROP_FPS))
    series=[];total=0;height=None
    while True:
        ok,frame=capture.read()
        if not ok:break
        total+=1;height=frame.shape[0]
        hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
        mask=cv2.inRange(hsv,np.array([4,90,60]),np.array([27,255,255]))
        count,_,components,centres=cv2.connectedComponentsWithStats(mask,connectivity=8)
        if count>1:
            k=1+np.argmax(components[1:,cv2.CC_STAT_AREA])
            area=int(components[k,cv2.CC_STAT_AREA])
            if area>max(700,round(0.003*frame.shape[0]*frame.shape[1])):
                series.append((total-1,float(centres[k,1])))
    capture.release()
    if not total or fps<=0:return {'pass':False,'reason':'INVALID_VIDEO_TIMESTAMPS'}
    coverage=len(series)/total
    if coverage<.80:return {'pass':False,'reason':'ORANGE_OBJECT_NOT_TRACKABLE','tracking_coverage_pct':round(coverage*100,1)}
    frame_ids=np.array([q[0] for q in series],dtype=float)
    y=np.array([q[1] for q in series],dtype=float)
    # Fill occasional missing observations, smoothing a noisy color mask.
    x=np.arange(total,dtype=float)
    y=np.interp(x,frame_ids,y)
    length=min(19,total if total%2 else total-1)
    if length<7:return {'pass':False,'reason':'INSUFFICIENT_FRAMES'}
    smoothed=savgol_filter(y,length,2)
    min_prominence=max(12,.028*height)
    peaks,meta=find_peaks(smoothed,prominence=min_prominence,distance=max(8,round(.55*fps)))
    events=[]
    for idx,k in enumerate(peaks):
        future=smoothed[k+1:min(len(smoothed),k+1+round(.55*fps))]
        if len(future)<3:continue
        rebound=float(smoothed[k]-np.min(future))
        if rebound<max(12,.023*height):continue
        events.append({'seconds':round(float(k/fps),2),
                       'vertical_rebound_pixels':round(rebound,1),
                       'peak_prominence_pixels':round(float(meta['prominences'][idx]),1)})
    passed=len(events)>=expected_minimum
    return {'pass':passed,'reason':'MINIMUM_VISIBLE_BOUNCES' if passed else 'BOUNCE_ACTION_NOT_VERIFIED',
            'detected_rebound_candidates':len(events),'required_minimum':expected_minimum,
            'tracking_coverage_pct':round(100*coverage,1), 'candidate_events':events[:20],
            'semantic_verification':False,'caveat':'Color-tracking heuristic, not verified semantic action recognition'}