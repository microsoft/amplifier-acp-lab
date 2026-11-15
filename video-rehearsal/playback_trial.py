import functools, hashlib, http.server, json, os, pathlib, shutil, subprocess, threading
from playwright.sync_api import sync_playwright
from fixture_server import RangeHandler
ROOT = pathlib.Path(os.environ.get('REHEARSAL_OUTPUT', pathlib.Path(__file__).parent / 'playback-trial')).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
ffmpeg = os.environ.get('FFMPEG_BIN') or shutil.which('ffmpeg')
if not ffmpeg:
 import imageio_ffmpeg
 ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
good = ROOT / 'good'; good.mkdir(exist_ok=True)
common = [ffmpeg, '-y', '-f','lavfi','-i','testsrc2=size=640x360:rate=30:duration=6','-f','lavfi','-i','sine=frequency=440:duration=6']
for name, codec in [('clip.webm',['-c:v','libvpx-vp9','-b:v','300k','-c:a','libopus']), ('clip.mp4',['-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac'])]:
 subprocess.run(common + codec + ['-shortest',str(good/name)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
(good/'captions.vtt').write_text('WEBVTT\n\n00:00:00.500 --> 00:00:05.500\nFIXTURE CUE ONE\n')
(good/'index.html').write_text('<!doctype html><html lang="en"><title>Playback fixture</title><video id="v" width="640" height="360" muted controls><source src="clip.mp4" type="video/mp4"><source src="clip.webm" type="video/webm"><track id="t" kind="captions" srclang="en" label="English" src="captions.vtt" default></video></html>')
broken=ROOT/'broken'; shutil.copytree(good,broken,dirs_exist_ok=True); (broken/'captions.vtt').unlink()
# Archive and extract so the second set tests the delivered bytes independently.
shutil.make_archive(str(ROOT/'fixture'),'zip',ROOT,base_dir='good')
shutil.unpack_archive(str(ROOT/'fixture.zip'), ROOT/'extracted')
server_kind=os.environ.get('REHEARSAL_SERVER','simple')
if server_kind not in ('simple','range'): raise ValueError('REHEARSAL_SERVER must be simple or range')
handler=functools.partial(RangeHandler if server_kind=='range' else http.server.SimpleHTTPRequestHandler,directory=str(ROOT))
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
results={'transport':'loopback HTTP; extracted copy is served locally, not file://','server':server_kind,'checks':[], 'fixture_sha256':{name:hashlib.sha256((good/name).read_bytes()).hexdigest() for name in ['index.html','captions.vtt','clip.mp4','clip.webm']}}
with sync_playwright() as p:
 try:
  browser=p.chromium.launch(headless=True)
 except Exception as e:
  results.update(status='not tested', reason='Browser launch failed: '+str(e))
  (ROOT/'results.json').write_text(json.dumps(results,indent=2))
  server.shutdown()
  raise SystemExit(2)
 results['browser']=browser.version
 for package in ['good','broken','extracted/good']:
  for source in ['clip.mp4','clip.webm']:
   page=browser.new_page(viewport={'width':800,'height':500}); errors=[]
   page.on('pageerror', lambda e: errors.append(str(e)))
   page.goto(f'http://127.0.0.1:{server.server_port}/{package}/index.html')
   row={'package':package,'source':source,'canPlayType':page.evaluate('''() => {let v=document.querySelector('video');return {h264:v.canPlayType('video/mp4; codecs="avc1.42E01E"'),vp9:v.canPlayType('video/webm; codecs="vp9"')}}''')}
   try:
    page.evaluate('''async (src) => {let v=document.querySelector('video');v.src=src;v.load();v.textTracks[0].mode='showing';await v.play()}''',source)
    page.wait_for_function('v.currentTime > 0.8')
    frame1=page.evaluate('''() => {let c=document.createElement('canvas');c.width=640;c.height=360;c.getContext('2d').drawImage(v,0,0);return c.toDataURL()}''')
    t1=page.evaluate('v.currentTime'); page.wait_for_timeout(700)
    frame2=page.evaluate('''() => {let c=document.createElement('canvas');c.width=640;c.height=360;c.getContext('2d').drawImage(v,0,0);return c.toDataURL()}''')
    row.update(clock_advanced=page.evaluate('v.currentTime')>t1, decoded_image_changed=frame1!=frame2,decoded_frames=page.evaluate('v.getVideoPlaybackQuality().totalVideoFrames'))
    page.evaluate('v.pause()')
    page.wait_for_timeout(300)
    row['caption']=page.evaluate('''() => ({readyState:t.readyState,mode:v.textTracks[0].mode,cues:Array.from(v.textTracks[0].activeCues||[]).map(c=>c.text)})''')
    page.evaluate('v.controls=false')
    stem=package.replace('/','-')+'-'+source
    shown=page.locator('video').screenshot(path=str(ROOT/(stem+'-captions.png')))
    page.evaluate("v.textTracks[0].mode='hidden'"); page.wait_for_timeout(150)
    hidden=page.locator('video').screenshot(path=str(ROOT/(stem+'-hidden.png')))
    row['caption_render_changes_pixels']=shown!=hidden
    row['video_pass']=row['clock_advanced'] and row['decoded_image_changed'] and row['decoded_frames']>0
    row['caption_pass']='FIXTURE CUE ONE' in row['caption']['cues'] and row['caption_render_changes_pixels']
    page.evaluate('v.currentTime=4')
    try:
     page.wait_for_function('!v.seeking && Math.abs(v.currentTime-4)<0.1', timeout=3000)
     row['seek_pass']=True
    except Exception:
     row['seek_pass']=False
     row['seek_diagnostic']=page.evaluate('''() => ({time:v.currentTime,seeking:v.seeking,duration:v.duration,seekable:Array.from({length:v.seekable.length},(_,i)=>[v.seekable.start(i),v.seekable.end(i)])})''')
    row['seek_seconds']=page.evaluate('v.currentTime')
   except Exception as e: row['failure']=str(e)
   row['page_errors']=errors;results['checks'].append(row);page.close()
 browser.close()
server.shutdown()
(ROOT/'results.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results,indent=2))
