"""Part A — validate the real DOT wrist signal against mocap-derived wrist motion.
Impact-aligned representative swings (driver + 5i)."""
import numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from kin_core import *

INK="#23221c"; LODEN="#3c4a30"; CLAY="#b4632f"; MUTED="#8a8577"; PAPER="#f0ede2"; LINE="#ddd7c4"
plt.rcParams.update({"font.size":10,"axes.edgecolor":LINE,"axes.labelcolor":INK,
    "xtick.color":MUTED,"ytick.color":MUTED,"text.color":INK,"figure.facecolor":"white","axes.facecolor":"white"})

def mocap_wrist_angvel(tag):
    t,M,rate = load_trc(f"{tag}.trc")
    R,wr = wrist_frame(M,"L")
    wmag,_ = ang_vel_from_R(R,rate); wmag=smooth(wmag,5)
    return t,wmag,rate

def dot_swing(csv, t_center, half=1.3):
    d = load_imu(csv)
    m=(d.t>t_center-half)&(d.t<t_center+half)
    seg=d[m].reset_index(drop=True)
    return seg.t.values-seg.t.values[0], seg.gmag.values

def window_on_impact(t,y,rate,t_imp,pre=1.2,post=0.6):
    i0=int((t_imp-pre)*rate); i1=int((t_imp+post)*rate)
    i0=max(0,i0); i1=min(len(y),i1)
    seg=y[i0:i1]; tt=(np.arange(len(seg))-(int(t_imp*rate)-i0))/rate
    return tt,seg

fig,axes=plt.subplots(1,2,figsize=(11,4.2))
results={}
plans=[("D1","driver","e3923d6a-1789197372030_swingcoach-session-2026-09-11-18-52-51.csv",79.585),
       ("5i","5i","e3923d6a-1789197372030_swingcoach-session-2026-09-11-18-52-51.csv",40.634)]
for ax,(tag,label,csv,dot_t) in zip(axes,plans):
    t,wmag,rate = mocap_wrist_angvel(tag)
    imps = find_swings(wmag, rate, thr=max(500,np.percentile(wmag,99)*0.5), min_gap_s=2.5)
    # pick the swing with the largest peak as the representative
    best = max(imps, key=lambda k: wmag[k]); t_imp=t[best]
    tm,ym = window_on_impact(t,wmag,rate,t_imp)
    td,yd = dot_swing(csv,dot_t)
    # align DOT on its own peak to t=0
    td = td - td[int(np.argmax(yd))]
    ax.plot(tm,ym,color=LODEN,lw=2,label="mocap wrist (virtual IMU)")
    ax.plot(td,yd,color=CLAY,lw=2,label="Downrange DOT gyro")
    ax.axvline(0,color=MUTED,ls="--",lw=1)
    ax.set_title(f"{label}: wrist angular speed, impact-aligned",color=INK,fontsize=11)
    ax.set_xlabel("time from impact (s)"); ax.set_ylabel("|angular velocity| (°/s)")
    ax.set_xlim(-1.2,0.6); ax.legend(frameon=False,fontsize=8)
    results[label]={"mocap_peak":round(float(ym.max())), "dot_peak":round(float(yd.max())),
                    "mocap_impact_t":round(float(t_imp),2)}
plt.tight_layout(); plt.savefig("figA_sensor_validation.png",dpi=130,facecolor="white")
print("Part A results:", results)
print("saved figA_sensor_validation.png")
