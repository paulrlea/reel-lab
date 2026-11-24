"""Lightweight CPU-only onset/tempo estimation and constrained beat snapping."""
from array import array
from copy import deepcopy
import math
import statistics
import subprocess
import sys


def analyze_beats(path):
    # Decode a bounded mono preview of a locally licensed track. No GPU or ML dependency.
    raw = subprocess.check_output(['ffmpeg','-nostdin','-v','error','-i',str(path),'-t','180',
        '-vn','-ac','1','-ar','8000','-f','s16le','pipe:1'], timeout=180)
    samples=array('h'); samples.frombytes(raw)
    if sys.byteorder!='little': samples.byteswap()
    step=80  # 10 ms energy windows
    energy=[math.log1p(sum(int(x)*int(x) for x in samples[i:i+step])/step) for i in range(0,len(samples)-step+1,step)]
    if len(energy)<100: return {'bpm':None,'beats':[],'confidence':0.0}
    flux=[0.0]+[max(0.0,b-a) for a,b in zip(energy,energy[1:])]
    baseline=statistics.median(flux); threshold=max(0.8,baseline+3*statistics.median(abs(x-baseline) for x in flux))
    peaks=[]
    for i in range(1,len(flux)-1):
        if flux[i]<threshold or flux[i]<flux[i-1] or flux[i]<flux[i+1]: continue
        if peaks and i-peaks[-1]<18:
            if flux[i]>flux[peaks[-1]]: peaks[-1]=i
        else: peaks.append(i)
    if len(peaks)<5: return {'bpm':None,'beats':[],'confidence':0.0}
    # Choose the inter-onset interval in a reasonable tempo range. Confidence
    # reflects how regularly adjacent transients follow that interval.
    intervals=[(b-a)/100 for a,b in zip(peaks,peaks[1:])]
    usable=[x for x in intervals if .33<=x<=1.0]
    if len(usable)<4: return {'bpm':None,'beats':[],'confidence':0.0}
    period=statistics.median(usable)
    confidence=sum(abs(x-period)<=max(.035,period*.12) for x in intervals)/len(intervals)
    if confidence<.65: return {'bpm':None,'beats':[],'confidence':round(confidence,3)}
    return {'bpm':round(60/period,1),'beats':[round(i/100,3) for i in peaks], 'confidence':round(confidence,3)}


def snap_plan(plan,available,beats,offset=0,max_shift=.35):
    """Move internal cuts to nearby measured beats: keep total and overlay times fixed."""
    result=deepcopy(plan); clips=result['clips']; shifts=[]
    timeline=0.0
    for i in range(len(clips)-1):
        a,b=clips[i],clips[i+1]; timeline+=a['duration']
        possible=sorted((t-offset for t in beats if abs(t-offset-timeline)<=max_shift),key=lambda t:abs(t-timeline))
        for t in possible:
            delta=round(t-timeline,3)
            da=round(a['duration']+delta,3); db=round(b['duration']-delta,3)
            if da<1 or db<1: continue
            if a['start']+da>available[a['id']]['duration_seconds']+.001 or b['start']+db>available[b['id']]['duration_seconds']+.001: continue
            if abs(delta)<.001: break
            a['duration'],b['duration']=da,db; timeline+=delta
            shifts.append({'cut':i+1,'at':round(timeline,3),'shift':delta}); break
    result['duration']=round(sum(c['duration'] for c in clips),3)
    return result,shifts
