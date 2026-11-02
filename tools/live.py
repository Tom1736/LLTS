#!/usr/bin/env python3
"""Live view for aligning/focusing the OV9281: open http://<pi>:8000 in a browser.

Runs rpicam-vid as an MJPEG source and serves the newest frame at /frame.jpg.
The page computes a sharpness value (mean squared Laplacian in the centre ROI)
in the browser, so the Pi only has to encode JPEGs.
Usage: python3 live.py [width height fps]
"""
import subprocess, sys, threading, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

W, H, FPS = (sys.argv[1:4] if len(sys.argv) >= 4 else ("1280", "800", "10"))
latest = {"jpg": b"", "n": 0, "t": 0.0}
cond = threading.Condition()
# set by the calibration capture script on the PC (POST /status), shown on the page
status = {"json": b"{}"}


def capture():
    cmd = ["rpicam-vid", "-n", "-t", "0", "--codec", "mjpeg", "--quality", "95",
           "--width", W, "--height", H, "--framerate", FPS, "-o", "-"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    buf = b""
    while True:
        chunk = p.stdout.read(65536)
        if not chunk:
            sys.exit("rpicam-vid stopped")
        buf += chunk
        while True:
            s = buf.find(b"\xff\xd8")
            e = buf.find(b"\xff\xd9", s + 2) if s >= 0 else -1
            if e < 0:
                if s > 0:
                    buf = buf[s:]
                break
            with cond:
                latest["jpg"] = buf[s:e + 2]
                latest["n"] += 1
                latest["t"] = time.time()
                cond.notify_all()
            buf = buf[e + 2:]


PAGE = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>OV9281 live</title>
<style>
body{margin:0;background:#111;color:#eee;font:14px system-ui,sans-serif}
#bar{padding:8px 12px;display:flex;gap:24px;flex-wrap:wrap;align-items:center}
#bar b{font-size:20px;font-variant-numeric:tabular-nums}
#meter{width:300px;height:14px;background:#333;position:relative}
#fill{height:100%;background:#4c9;width:0}
#peak{position:absolute;top:-3px;width:2px;height:20px;background:#fc3;left:0}
canvas{display:block;max-width:100vw;max-height:calc(100vh - 60px);margin:auto}
button{font:inherit}
</style></head><body>
<div id="bar">
 <span>Schärfe (Mitte): <b id="sh">-</b></span>
 <div id="meter"><div id="fill"></div><div id="peak"></div></div>
 <span>Max: <b id="mx">-</b> <button id="rs">Reset</button></span>
 <span>Helligkeit: <b id="br">-</b></span>
 <span>Überbelichtet: <b id="cl">-</b></span>
 <span><b id="fps">-</b> fps</span>
</div>
<div id="cal" style="display:none;padding:6px 12px;background:#222;align-items:center;gap:18px">
 <span>Kalibrierbilder: <b id="cn" style="font-size:26px">0</b></span>
 <table id="grid" style="border-collapse:collapse"></table>
 <span id="cm" style="font-size:20px"></span>
</div>
<canvas id="c"></canvas>
<script>
const c=document.getElementById('c'),x=c.getContext('2d',{willReadFrequently:true});
let peak=0,frames=0,t0=performance.now();
document.getElementById('rs').onclick=()=>{peak=0};
const $=id=>document.getElementById(id);
function analyse(w,h){
  // centre ROI: middle half in each direction
  const rx=w>>2,ry=h>>2,rw=w>>1,rh=h>>1;
  const d=x.getImageData(rx,ry,rw,rh).data;
  const g=new Float32Array(rw*rh);
  for(let i=0;i<rw*rh;i++)g[i]=d[i*4];
  let s=0,n=0;
  for(let yy=1;yy<rh-1;yy++)for(let xx=1;xx<rw-1;xx++){
    const i=yy*rw+xx,l=4*g[i]-g[i-1]-g[i+1]-g[i-rw]-g[i+rw];s+=l*l;n++;}
  const all=x.getImageData(0,0,w,h).data;let sum=0,clip=0;
  for(let i=0;i<all.length;i+=16){sum+=all[i];if(all[i]>=250)clip++;}
  return [s/n,sum/(all.length/16),100*clip/(all.length/16)];
}
function overlay(w,h){
  x.strokeStyle='rgba(255,60,60,.8)';x.lineWidth=1;x.beginPath();
  x.moveTo(w/2,0);x.lineTo(w/2,h);x.moveTo(0,h/2);x.lineTo(w,h/2);x.stroke();
  x.strokeStyle='rgba(80,200,255,.6)';x.strokeRect(w/4,h/4,w/2,h/2);
  x.strokeStyle='rgba(255,255,255,.25)';x.beginPath();
  for(const f of[1/3,2/3]){x.moveTo(w*f,0);x.lineTo(w*f,h);x.moveTo(0,h*f);x.lineTo(w,h*f);}x.stroke();
}
async function loop(){
  try{
    const r=await fetch('/frame.jpg?'+Date.now(),{cache:'no-store'});
    const b=await createImageBitmap(await r.blob());
    if(c.width!==b.width){c.width=b.width;c.height=b.height;}
    x.drawImage(b,0,0);
    const [s,br,cl]=analyse(b.width,b.height);
    overlay(b.width,b.height);
    peak=Math.max(peak,s);
    $('sh').textContent=s.toFixed(1);$('mx').textContent=peak.toFixed(1);
    $('br').textContent=br.toFixed(0)+' / 255';$('cl').textContent=cl.toFixed(1)+' %';
    $('fill').style.width=(peak?100*s/peak:0)+'%';$('peak').style.left='100%';
    frames++;const now=performance.now();
    if(now-t0>1000){$('fps').textContent=(frames*1000/(now-t0)).toFixed(1);frames=0;t0=now;}
  }catch(e){await new Promise(r=>setTimeout(r,500));}
  requestAnimationFrame(loop);
}
loop();
let lastN=-1;
async function cal(){
  try{
    const s=await (await fetch('/status',{cache:'no-store'})).json();
    if(s.n!==undefined){
      $('cal').style.display='flex';$('cn').textContent=s.n;$('cm').textContent=s.msg||'';
      $('cm').style.color=s.color||'#eee';
      // grid is in sensor orientation; the page shows the same orientation
      $('grid').innerHTML=s.grid.map(r=>'<tr>'+r.map(v=>
        `<td style="width:34px;height:22px;border:1px solid #555;text-align:center;background:${v>=3?'#2a6':v>0?'#a82':'#822'}">${v}</td>`).join('')+'</tr>').join('');
      if(lastN>=0&&s.n>lastN){c.style.outline='8px solid #2f6';setTimeout(()=>c.style.outline='',400);}
      lastN=s.n;
    }
  }catch(e){}
  setTimeout(cal,700);
}
cal();
</script></body></html>"""

# Calibration target for the tablet: 10x7 squares (9x6 inner corners), one square white margin.
BOARD = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Board</title><style>html,body{margin:0;height:100%;background:#fff;overflow:hidden}
svg{width:100vw;height:100vh;display:block}#h{position:fixed;top:8px;left:8px;font:16px sans-serif;color:#888}</style></head>
<body><svg viewBox="-1 -1 12 9" preserveAspectRatio="xMidYMid meet" shape-rendering="crispEdges"><g id="g"></g></svg>
<div id="h">Antippen = Vollbild</div>
<script>
let s='';for(let y=0;y<7;y++)for(let x=0;x<10;x++)if((x+y)%2==0)s+=`<rect x="${x}" y="${y}" width="1" height="1"/>`;
document.getElementById('g').innerHTML=s;
document.body.onclick=()=>{const d=document.documentElement;(d.requestFullscreen||d.webkitRequestFullscreen).call(d);document.getElementById('h').remove();};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/frame.jpg"):
            with cond:
                n = latest["n"]
                cond.wait_for(lambda: latest["n"] != n, timeout=2)
                jpg = latest["jpg"]
            if not jpg:
                self.send_error(503, "no frame yet")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(jpg)))
            self.end_headers()
            self.wfile.write(jpg)
        elif self.path in ("/", "/board", "/status"):
            body, ctype = {"/": (PAGE.encode(), "text/html; charset=utf-8"),
                           "/board": (BOARD.encode(), "text/html; charset=utf-8"),
                           "/status": (status["json"], "application/json")}[self.path]
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/status":
            self.send_error(404)
            return
        status["json"] = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(204)
        self.end_headers()


threading.Thread(target=capture, daemon=True).start()
ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
