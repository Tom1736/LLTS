import sys, numpy as np
from PIL import Image
imgs=[np.asarray(Image.open(p).convert('L'),dtype=float) for p in sys.argv[1:]]
a=imgs[-1]; h,w=a.shape
print(f"Größe {w}x{h}")
print(f"Helligkeit: Mittel {a.mean():.1f}, Min {a.min():.0f}, Max {a.max():.0f}, Perzentile 1/50/99: {np.percentile(a,[1,50,99]).round(0)}")
print(f"Pixel >=250: {100*np.mean(a>=250):.3f} %, <=5: {100*np.mean(a<=5):.3f} %")
# checkerboard region
Y0,Y1,X0,X1=[int(v) for v in __import__("os").environ.get("ROI","195,395,395,705").split(",")]
cb=a[Y0:Y1,X0:X1]
print(f"Schachbrett: Weiß ~{np.percentile(cb,90):.0f}, Schwarz ~{np.percentile(cb,10):.0f}, Kontrast {np.percentile(cb,90)-np.percentile(cb,10):.0f}")
def edge_widths(prof):
    # 10-90 % Anstiegsbreite an jedem Übergang (sub-pixel, linear interpoliert)
    lo,hi=np.percentile(prof,10),np.percentile(prof,90); mid=(lo+hi)/2
    res=[]
    for i in np.where(np.diff(np.sign(prof-mid))!=0)[0]:
        s=slice(max(i-8,0),min(i+9,len(prof))); seg=prof[s]
        l,hh=seg.min(),seg.max()
        if hh-l<0.6*(hi-lo): continue
        n=(seg-l)/(hh-l)
        if n[0]>n[-1]: n=n[::-1]
        x=np.arange(len(n))
        def cross(t):
            j=np.argmax(n>=t); return j-1+(t-n[j-1])/(n[j]-n[j-1]) if j>0 else 0
        res.append(cross(0.9)-cross(0.1))
    return res
hw=[]; vw=[]
for y in range(Y0+10,Y1-5,6): hw+=edge_widths(a[y,X0+5:X1-5])
for x in range(X0+5,X1-5,6): vw+=edge_widths(a[Y0+5:Y1-5,x])
hw,vw=np.array(hw),np.array(vw)
print(f"Kantenbreite 10-90% (horizontales Profil): Median {np.median(hw):.2f} px  (n={len(hw)})")
print(f"Kantenbreite 10-90% (vertikales Profil):   Median {np.median(vw):.2f} px  (n={len(vw)})")
# Rauschen: zeitlich (3 Frames) und räumlich auf der Wand
if len(imgs)>=2:
    st=np.std(np.stack(imgs),axis=0)
    print(f"Zeitliches Rauschen (Std über {len(imgs)} Frames): Wand {np.median(st[600:760,700:1050]):.2f}, Schachbrett {np.median(st[Y0:Y1,X0:X1]):.2f}")
wall=a[600:760,700:1050]
print(f"Wand: Mittel {wall.mean():.1f}, räumliche Std {wall.std():.2f}")
# Schärfe-Score wie im Browser (Laplace²) in der Mitte
c=a[h//4:3*h//4,w//4:3*w//4]
lap=4*c[1:-1,1:-1]-c[:-2,1:-1]-c[2:,1:-1]-c[1:-1,:-2]-c[1:-1,2:]
print(f"Schärfe-Score (Mitte, wie Webseite): {np.mean(lap**2):.1f}")
# Blendung: Anteil übersteuerter Pixel auf dem Brett
print(f"Übersteuert auf dem Brett (>=250): {100*np.mean(cb>=250):.1f} %")
