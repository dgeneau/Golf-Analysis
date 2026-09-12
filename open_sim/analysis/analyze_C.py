"""Part C — the coaching payload: trunk kinematics + sequencing for one driver swing."""
import numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from kin_core import *
INK="#23221c"; LODEN="#3c4a30"; CLAY="#b4632f"; MUTED="#8a8577"; MOSS="#8a9270"; LINE="#ddd7c4"
plt.rcParams.update({"font.size":10,"axes.edgecolor":LINE,"xtick.color":MUTED,"ytick.color":MUTED,
    "text.color":INK,"figure.facecolor":"white","axes.facecolor":"white"})
RATE=60.0
t,M,rate=load_trc("D1.trc"); R,wr=wrist_frame(M,"L")
wmag,_=ang_vel_from_R(R,rate); wmag=smooth(wmag,5)
hsp=np.linalg.norm(np.gradient(smooth(wr,9),1/rate,axis=0),axis=1)  # m/s (markers already in metres)
hip,sho,xf=trunk_from_markers(M); m=load_mot("D1.mot")
n=len(t); PRE=int(1.6*RATE); POST=int(0.4*RATE)
# impact = peak HAND SPEED within a swing cluster (reliable impact marker)
imps=[z for z in find_swings(hsp,RATE,thr=max(6,np.percentile(hsp,99)*0.55),min_gap_s=2.5)
      if z-PRE>=0 and z+POST<n]
k=max(imps,key=lambda z:hsp[z]); a,b=k-PRE,k+POST
print(f"impact at t={t[k]:.1f}s, hand speed {hsp[k]:.1f} m/s")
tt=(np.arange(a,b)-k)/RATE
def ref(x): x=np.degrees(np.unwrap(np.radians(x[a:b]))); return x-x[0]
# flip so "turn away from target" reads positive (intuitive for coaching)
sgn=-1 if (ref(sho)[:int(1.2*RATE)].mean()<0) else 1
hipw=sgn*ref(hip); show=sgn*ref(sho); xfw=show-hipw
pelv=m.pelvis_rotation.values[a:b]-m.pelvis_rotation.values[a]
fig,ax=plt.subplots(figsize=(8.4,4.6))
ax.plot(tt,hipw,color=MOSS,lw=2,label="pelvis (hips) turn")
ax.plot(tt,show,color=LODEN,lw=2,label="shoulders turn")
ax.plot(tt,xfw,color=CLAY,lw=2.4,label="X-factor (shoulders − hips)")
ax.axvline(0,color=MUTED,ls="--",lw=1); ax.axhline(0,color=LINE,lw=1)
# mark top of backswing = max |shoulder turn|
top=a+int(np.argmax(np.abs(show)))-a
ax.axvline(tt[top],color=MUTED,ls=":",lw=1)
ax.annotate("top of backswing",(tt[top],show[top]),fontsize=8,color=MUTED,ha="right")
ax.annotate("impact",(0,0),xytext=(0.05,8),fontsize=8,color=MUTED)
ax.set_xlabel("time from impact (s)"); ax.set_ylabel("rotation from address (°)")
ax.set_title("Driver swing — trunk turn & X-factor (OpenCap ground truth)",fontsize=11)
ax.legend(frameon=False,fontsize=9,loc="lower left")
peakxf=xfw[np.argmax(np.abs(xfw))]
ax.text(0.02,0.97,f"peak X-factor ≈ {abs(peakxf):.0f}°",transform=ax.transAxes,fontsize=9,va="top",color=CLAY)
plt.tight_layout(); plt.savefig("figC_trunk_sequence.png",dpi=130,facecolor="white")
print(f"peak X-factor {abs(peakxf):.0f}°  peak shoulder turn {abs(show).max():.0f}°  peak hip turn {abs(hipw).max():.0f}°")
print("saved figC_trunk_sequence.png")
