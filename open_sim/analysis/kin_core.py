"""Core loaders + kinematics for the wrist-IMU vs OpenCap feasibility study."""
import numpy as np, pandas as pd

# ---------- loaders ----------
def load_mot(path):
    lines = open(path).readlines()
    hi = next(i for i,l in enumerate(lines) if l.strip()=="endheader")
    cols = lines[hi+1].split()
    data = np.array([[float(x) for x in l.split()] for l in lines[hi+2:] if l.strip()])
    return pd.DataFrame(data, columns=cols)

def load_trc(path):
    lines = open(path).readlines()
    hdr = dict(zip(lines[1].split('\t'), lines[2].replace('\n','').split('\t')))
    names = [n for n in lines[3].strip().split('\t') if n]
    markers = names[2:]
    rows=[[float(v) for v in l.strip().split('\t')] for l in lines[6:] if l.strip()]
    arr = np.array(rows)
    t = arr[:,1]
    M = {}
    for i,name in enumerate(markers):
        M[name] = arr[:, 2+3*i:5+3*i]   # (n,3) mm
    rate = float(hdr.get('DataRate', 60))
    return t, M, rate

def load_imu(path):
    d = pd.read_csv(path)
    d["gmag"] = np.sqrt(d.gx**2+d.gy**2+d.gz**2)
    return d

# ---------- smoothing / kinematics ----------
def smooth(x, win=7):
    if x.ndim==1:
        k=np.ones(win)/win
        return np.convolve(x, k, mode='same')
    return np.column_stack([smooth(x[:,j],win) for j in range(x.shape[1])])

def marker_speed(M, name, rate):
    p = smooth(M[name], 9)
    v = np.gradient(p, 1/rate, axis=0)
    return np.linalg.norm(v, axis=1)   # mm/s

def wrist_frame(M, side="L"):
    """Full 3D forearm/wrist frame from 4 anatomical markers → R(t) (n,3,3)."""
    le = (M[f"{side}_lelbow_study"] + M[f"{side}_melbow_study"])/2
    wr = (M[f"{side}_lwrist_study"] + M[f"{side}_mwrist_study"])/2
    width = M[f"{side}_lwrist_study"] - M[f"{side}_mwrist_study"]
    z = wr - le                                   # forearm long axis
    z /= np.linalg.norm(z, axis=1, keepdims=True)
    w = width
    x = w - (np.sum(w*z,axis=1,keepdims=True))*z  # across-wrist, perp to forearm
    x /= np.linalg.norm(x, axis=1, keepdims=True)
    y = np.cross(z, x)
    R = np.stack([x,y,z], axis=2)                 # columns are axes
    return R, wr

def ang_vel_from_R(R, rate):
    """Angular velocity magnitude (deg/s) from a rotation-matrix time series."""
    Rs = R.copy()
    dR = np.gradient(Rs, 1/rate, axis=0)          # (n,3,3)
    n = R.shape[0]; w = np.zeros(n)
    wl = np.zeros((n,3))
    for i in range(n):
        W = dR[i] @ R[i].T                         # world-frame skew
        wl[i] = [W[2,1]-W[1,2], W[0,2]-W[2,0], W[1,0]-W[0,1]]
    wl *= 0.5
    return np.degrees(np.linalg.norm(wl, axis=1)), np.degrees(wl)

def trunk_from_markers(M):
    """Pelvis & shoulder transverse-plane yaw and X-factor (deg), from markers.
    OpenCap frame: Y up; transverse plane = X-Z."""
    hipL, hipR = M["LHJC_study"], M["RHJC_study"]
    shL, shR   = M["L_shoulder_study"], M["r_shoulder_study"]
    def yaw(a,b):
        v = b - a
        return np.degrees(np.arctan2(v[:,0], v[:,2]))   # azimuth in X-Z plane
    hip = np.unwrap(np.radians(yaw(hipL,hipR)))
    sho = np.unwrap(np.radians(yaw(shL,shR)))
    hip = np.degrees(hip); sho = np.degrees(sho)
    xfac = sho - hip
    return hip, sho, xfac

# ---------- swing segmentation ----------
def find_swings(speed, rate, thr, min_gap_s=2.0, halo=150):
    """Return impact indices = local maxima of `speed` above thr, separated."""
    idx=[]; i=0; n=len(speed); gap=int(min_gap_s*rate)
    while i<n:
        if speed[i]>thr:
            j=i
            while j<n and speed[j]>thr*0.4: j+=1
            pk=i+int(np.argmax(speed[i:max(j,i+1)]))
            idx.append(pk); i=pk+gap
        else: i+=1
    return idx

if __name__=="__main__":
    for tag in ["D1","5i"]:
        t,M,rate = load_trc(f"{tag}.trc")
        R,wr = wrist_frame(M,"L")
        wmag,_ = ang_vel_from_R(R, rate)
        wmag = smooth(wmag,5)
        hsp = marker_speed(M,"LWrist",rate)/1000  # m/s
        hip,sho,xf = trunk_from_markers(M)
        imp = find_swings(hsp, rate, thr=np.percentile(hsp,99)*0.6)
        print(f"\n=== {tag} (mocap) {t[-1]:.1f}s @ {rate}Hz ===")
        print(f"  swings detected: {len(imp)} at t≈{[round(t[k],1) for k in imp]}")
        print(f"  hand speed peak {hsp.max():.1f} m/s · wrist angvel peak {wmag.max():.0f} deg/s")
        print(f"  X-factor range {xf.min():.0f}..{xf.max():.0f}°  pelvis-yaw range {hip.min():.0f}..{hip.max():.0f}°")
        m = load_mot(f"{tag}.mot")
        print(f"  .mot lumbar_rotation range {m.lumbar_rotation.min():.0f}..{m.lumbar_rotation.max():.0f}°  pelvis_rotation {m.pelvis_rotation.min():.0f}..{m.pelvis_rotation.max():.0f}°")
