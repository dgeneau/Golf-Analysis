"""Part B — feasibility: predict trunk kinematics from a wrist-only signal.
Virtual IMU (orientation 6D + angular velocity + linear accel, referenced to the
address pose) -> X-factor / pelvis rotation / thorax rotation. Ridge regression,
leave-one-swing-out across all driver+iron swings. A LINEAR lower bound on the
WIT-KinNet premise, on Dan's subject/hardware."""
import numpy as np, json, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from kin_core import *
from numpy.linalg import lstsq

INK="#23221c"; LODEN="#3c4a30"; CLAY="#b4632f"; MUTED="#8a8577"; LINE="#ddd7c4"
plt.rcParams.update({"font.size":10,"axes.edgecolor":LINE,"xtick.color":MUTED,"ytick.color":MUTED,
    "text.color":INK,"figure.facecolor":"white","axes.facecolor":"white"})

RATE=60.0; PRE=int(1.4*RATE); POST=int(0.5*RATE)

def trunk_signals(tag):
    t,M,rate = load_trc(f"{tag}.trc")
    R,wr = wrist_frame(M,"L")
    wmag,wl = ang_vel_from_R(R,rate)              # wl: world angvel vec (deg/s)
    wr_s = smooth(wr,9)
    acc = np.gradient(np.gradient(wr_s,1/rate,axis=0),1/rate,axis=0)/1000.0  # m/s^2 world
    hip,sho,xf = trunk_from_markers(M)
    m = load_mot(f"{tag}.mot")
    n=min(len(t),len(m))
    pelv=m.pelvis_rotation.values[:n]; lumb=m.lumbar_rotation.values[:n]
    return dict(t=t[:n],R=R[:n],wr=wr_s[:n],wl=wl[:n],acc=acc[:n],wmag=wmag[:n],
                hip=hip[:n],sho=sho[:n],pelv=pelv,lumb=lumb)

def swings_windows(S):
    imps=find_swings(S["wmag"],RATE,thr=max(500,np.percentile(S["wmag"],99)*0.5),min_gap_s=2.5)
    out=[]
    for k in imps:
        a,b=k-PRE,k+POST
        if a<1 or b>=len(S["t"])-1: continue
        out.append((a,k,b))
    return out

def feats_targets(S,a,k,b):
    Ra=S["R"][a]                                  # address frame (window start)
    X=[]; xf=[]; pe=[]; th=[]
    # local-unwrapped trunk yaw referenced to address
    hipw=np.degrees(np.unwrap(np.radians(S["hip"][a:b]))); hipw-=hipw[0]
    show=np.degrees(np.unwrap(np.radians(S["sho"][a:b]))); show-=show[0]
    xfw = show-hipw
    pew = S["pelv"][a:b]-S["pelv"][a]
    lumw= S["lumb"][a:b]
    thw = (S["pelv"][a:b]+S["lumb"][a:b]); thw-=thw[0]
    for j,i in enumerate(range(a,b)):
        Rrel=Ra.T@S["R"][i]
        o6=Rrel[:, :2].flatten()                  # 6D orientation rel address
        w =Ra.T@S["wl"][i]/1000.0                 # angvel (deg/s /1000) in address frame
        ac=Ra.T@S["acc"][i]/10.0                  # accel (m/s^2 /10) in address frame
        X.append(np.concatenate([o6,w,ac]))
        xf.append(xfw[j]); pe.append(pew[j]); th.append(thw[j])
    return np.array(X),np.array(xf),np.array(pe),np.array(th)

def add_context(X,ctx=3):
    n,f=X.shape
    padded=np.vstack([np.repeat(X[:1],ctx,axis=0),X,np.repeat(X[-1:],ctx,axis=0)])
    out=np.zeros((n,f*(2*ctx+1)))
    for d in range(2*ctx+1):
        out[:,d*f:(d+1)*f]=padded[d:d+n]
    return out

# build dataset
data=[]; sid=0
for tag in ["D1","5i"]:
    S=trunk_signals(tag)
    for (a,k,b) in swings_windows(S):
        X,xf,pe,th=feats_targets(S,a,k,b)
        Xc=add_context(X,3)
        data.append(dict(sid=sid,tag=tag,X=Xc,xf=xf,pe=pe,th=th,n=len(xf)))
        sid+=1
print(f"swings used: {len(data)}  (driver {sum(d['tag']=='D1' for d in data)}, 5i {sum(d['tag']=='5i' for d in data)})")

def ridge_fit(Xtr,ytr,lam=50.0):
    A=Xtr.T@Xtr+lam*np.eye(Xtr.shape[1]); return np.linalg.solve(A,Xtr.T@ytr)

def loso(target):
    preds=[];acts=[]
    for i in range(len(data)):
        tr=[d for j,d in enumerate(data) if j!=i]
        Xtr=np.vstack([d["X"] for d in tr]); ytr=np.concatenate([d[target] for d in tr])
        mu=Xtr.mean(0); sd=Xtr.std(0)+1e-6
        Xtr=(Xtr-mu)/sd; Xtr=np.column_stack([Xtr,np.ones(len(Xtr))])
        ym=ytr.mean(); w=ridge_fit(Xtr,ytr-ym)
        te=data[i]; Xte=(te["X"]-mu)/sd; Xte=np.column_stack([Xte,np.ones(len(Xte))])
        yp=Xte@w+ym
        preds.append(yp); acts.append(te[target])
    P=np.concatenate(preds); A=np.concatenate(acts)
    r=np.corrcoef(P,A)[0,1]; ss=1-np.sum((A-P)**2)/np.sum((A-A.mean())**2)
    mae=np.mean(np.abs(A-P))
    return dict(r=round(float(r),3),R2=round(float(ss),3),mae=round(float(mae),2)), preds,acts

res={}
for tgt,lab in [("xf","X-factor"),("pe","pelvis rotation"),("th","thorax rotation")]:
    metrics,preds,acts=loso(tgt); res[lab]=metrics
    if tgt=="xf": xf_preds,xf_acts=preds,acts
print("Part B leave-one-swing-out:", json.dumps(res,indent=2))
json.dump(res,open("partB_metrics.json","w"),indent=2)

# figure: predicted vs actual X-factor for 3 held-out swings (1 driver, 2 iron)
fig,axes=plt.subplots(1,3,figsize=(12,3.6))
picks=[0, len(data)//2, len(data)-1]
for ax,pi in zip(axes,picks):
    tt=np.arange(len(xf_acts[pi]))/RATE-PRE/RATE
    ax.plot(tt,xf_acts[pi],color=LODEN,lw=2,label="mocap X-factor (truth)")
    ax.plot(tt,xf_preds[pi],color=CLAY,lw=2,ls="--",label="predicted from wrist")
    ax.axvline(0,color=MUTED,ls=":",lw=1); ax.set_xlabel("time from impact (s)")
    ax.set_title(f"held-out {data[pi]['tag']} swing",fontsize=10)
    ax.set_ylabel("X-factor (°)")
axes[0].legend(frameon=False,fontsize=8)
plt.suptitle(f"Predicting X-factor from the wrist signal alone (leave-one-swing-out)  ·  pooled r={res['X-factor']['r']}",fontsize=11)
plt.tight_layout(); plt.savefig("figB_xfactor_pred.png",dpi=130,facecolor="white")
print("saved figB_xfactor_pred.png")
