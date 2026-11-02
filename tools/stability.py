"""Split-half stability check for calib_solve.py output. Usage: python stability.py <dir>"""
import glob, json, sys, numpy as np, cv2
obj=np.zeros((54,3),np.float32); obj[:,:2]=np.mgrid[0:9,0:6].T.reshape(-1,2)
fs=sorted(glob.glob(sys.argv[1]+'/img_*.json')); C=[]
for f in fs:
    img=cv2.imread(f[:-5]+'.jpg',0); c=np.array(json.load(open(f))['corners'],np.float32).reshape(-1,1,2)
    C.append(cv2.cornerSubPix(img,c,(5,5),(-1,-1),(3,50,0.01)))
w,h=1280,800; allp=np.concatenate(C).reshape(-1,2)
cx,cy=630,430; r=np.hypot(allp[:,0]-cx,allp[:,1]-cy); rc=np.hypot(cx,cy)
print(f"Messpunkte: max Radius {r.max():.0f}/{rc:.0f} px ({100*r.max()/rc:.0f} %), r>600: {np.sum(r>600)}, x<80: {np.sum(allp[:,0]<80)}, x>1200: {np.sum(allp[:,0]>1200)}, y<60: {np.sum(allp[:,1]<60)}, y>740: {np.sum(allp[:,1]>740)}, y>680: {np.sum(allp[:,1]>680)}")
def cal(idx,flags=0):
    rms,K,d,_,_=cv2.calibrateCamera([obj]*len(idx),[C[i] for i in idx],(w,h),None,None,flags=flags); return rms,K,d.ravel()
def dc(K,d):
    p=np.array([[[0.,0.]],[[w-1.,0.]],[[0.,h-1.]],[[w-1.,h-1.]],[[0.,h/2]],[[w-1.,h/2]],[[w/2,0.]],[[w/2,h-1.]]])
    u=cv2.undistortPoints(p,K,d,P=K).reshape(-1,2); return np.linalg.norm(u-p.reshape(-1,2),axis=1)
n=len(C); rng=np.random.default_rng(0)
for name,flags in [("k1,k2,k3",0),("k1,k2",cv2.CALIB_FIX_K3)]:
    res=[]
    for lab,idx in [("alle",list(range(n))),("gerade",list(range(0,n,2))),("ungerade",list(range(1,n,2)))]+[(f"zufall{i}",sorted(rng.choice(n,n//2,replace=False))) for i in range(4)]:
        rms,K,d=cal(idx,flags); v=dc(K,d); res.append((K[0,0],v,rms))
    fxs=np.array([r[0] for r in res[1:]]); V=np.array([r[1] for r in res[1:]])
    print(f"Modell {name}: RMS {res[0][2]:.3f}, fx {res[0][0]:.1f}, Ecken {res[0][1][:4].round(1)} | Streuung: fx ±{fxs.std():.1f} px, Ecken ±{V[:,:4].std(0).mean():.1f} px (pro Ecke {V[:,:4].std(0).round(1)}), Ränder ±{V[:,4:].std(0).mean():.1f} px")
