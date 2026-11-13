import functools, hashlib, http.server, json, os, pathlib, shutil, subprocess, threading, urllib.request
from playwright.sync_api import sync_playwright
from fixture_server import RangeHandler
ROOT=pathlib.Path(os.environ.get('REHEARSAL_OUTPUT',pathlib.Path(__file__).parent/'playback-trial')).resolve()
ffmpeg=os.environ.get('FFMPEG_BIN') or shutil.which('ffmpeg')
if not ffmpeg:
 import imageio_ffmpeg
 ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
subprocess.run([ffmpeg,'-y','-i',str(ROOT/'good/clip.webm'),'-c','copy','-cues_to_front','1',str(ROOT/'good/front.webm')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
servers={}
for label,cls in [('simple',http.server.SimpleHTTPRequestHandler),('range',RangeHandler)]:
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(cls,directory=str(ROOT)))
 threading.Thread(target=server.serve_forever,daemon=True).start();servers[label]=server
results={'sha256_original':hashlib.sha256((ROOT/'good/clip.webm').read_bytes()).hexdigest(),'range_probes':{},'checks':[]}
for label,server in servers.items():
 req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/good/clip.webm',headers={'Range':'bytes=0-15'})
 with urllib.request.urlopen(req) as r: results['range_probes'][label]={'status':r.status,'content_range':r.headers.get('Content-Range'),'bytes':len(r.read())}
with sync_playwright() as p:
 b=p.chromium.launch(headless=True);results['browser']=b.version
 for transport,source in [('simple','clip.webm'),('range','clip.webm'),('simple','front.webm'),('file','clip.webm')]:
  for repeat in range(2):
   page=b.new_page();network=[];console=[]
   page.on('response',lambda r: network.append({'url':r.url,'status':r.status,'content_range':r.headers.get('content-range')}))
   page.on('console',lambda m: console.append(m.text) if m.type=='error' else None)
   url=(ROOT/'good/index.html').as_uri() if transport=='file' else f'http://127.0.0.1:{servers[transport].server_port}/good/index.html'
   page.goto(url)
   page.evaluate('''async src=>{v.src=src;v.load();v.textTracks[0].mode='showing';await v.play()}''',source)
   page.wait_for_function('v.currentTime>1');page.evaluate('v.pause()')
   caption=page.evaluate('''()=>({readyState:t.readyState,cues:Array.from(v.textTracks[0].activeCues||[]).map(c=>c.text)})''')
   page.evaluate('v.currentTime=4')
   try: page.wait_for_function('!v.seeking && Math.abs(v.currentTime-4)<0.1',timeout=3000)
   except Exception: pass
   state=page.evaluate('''()=>({time:v.currentTime,seeking:v.seeking,seekable:Array.from({length:v.seekable.length},(_,i)=>[v.seekable.start(i),v.seekable.end(i)])})''')
   results['checks'].append({'transport':transport,'source':source,'repeat':repeat,'seek_pass':not state['seeking'] and abs(state['time']-4)<.1,'state':state,'caption_before_seek':caption,'network':network,'console_errors':console})
   page.close()
 b.close()
for s in servers.values(): s.shutdown()
(ROOT/'seek-diagnosis.json').write_text(json.dumps(results,indent=2))
for c in results['checks']:print(c['transport'],c['source'],c['repeat'],c['seek_pass'],c['state'],c['caption_before_seek'])
print(results['range_probes'])
