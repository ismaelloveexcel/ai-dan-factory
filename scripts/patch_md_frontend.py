#!/usr/bin/env python3
"""
patch_md_frontend.py - Patches aidan-managing-director/main.py
with social card generator, promo video trigger, and region insights UI.

Runs via GitHub Actions using FACTORY_GITHUB_TOKEN.
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

TOKEN = os.environ.get("GH_TOKEN", "")
if not TOKEN:
    print("ERROR: GH_TOKEN (FACTORY_GITHUB_TOKEN) secret not set!", file=sys.stderr)
    sys.exit(1)

OWNER = "ismaelloveexcel"
REPO = "aidan-managing-director"
PATH = "main.py"
BRANCH = "main"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def github_get(path: str) -> dict:
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{path}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def github_put(path: str, content: str, sha: str, message: str) -> dict:
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{path}"
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    payload = json.dumps(
        {"message": message, "content": encoded, "sha": sha, "branch": BRANCH}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=HEADERS, method="PUT")
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"HTTP {e.code}: {body[:500]}", file=sys.stderr)
        raise


def rep(label: str, old: str, new: str, content: str) -> str:
    if old not in content:
        print(f"  SKIP {label}")
        return content
    result = content.replace(old, new, 1)
    print(f"  OK   {label}")
    return result


print(f"Fetching {REPO}/{PATH}...")
data = github_get(PATH)
sha = data["sha"]
content = base64.b64decode(data["content"]).decode("utf-8")
print(f"Fetched {len(content)} chars (sha={sha[:8]})")

# -------------------------------------------------------------------------
# Change 1: Region selector in Launch Kit tab
# -------------------------------------------------------------------------
OLD1 = (
    '        <label for="launch-cta">Call to action</label>\n'
    '        <input type="text" id="launch-cta" placeholder="e.g. Get early access free"/>\n\n'
    '        <div style="margin-top:1rem">\n'
    '          <button class="btn btn-primary btn-full" id="launch-btn" onclick="generateLaunch()">\n'
    '            &#9889; Generate All Content\n'
    '          </button>\n'
    '        </div>\n'
    '        <div id="launch-error" class="alert alert-error" style="display:none"></div>'
)
NEW1 = (
    '        <label for="launch-cta">Call to action</label>\n'
    '        <input type="text" id="launch-cta" placeholder="e.g. Get early access free"/>\n\n'
    '        <label for="launch-region">&#127758; Target Region</label>\n'
    '        <select id="launch-region" onchange="onRegionChange()">\n'
    '          <option value="global">&#127758; Global (All regions)</option>\n'
    '          <option value="mena">MENA (Middle East &amp; North Africa)</option>\n'
    '          <option value="africa">Sub-Saharan Africa</option>\n'
    '          <option value="south_asia">South Asia (India, Pakistan, BD)</option>\n'
    '          <option value="southeast_asia">Southeast Asia</option>\n'
    '          <option value="latam">Latin America</option>\n'
    '          <option value="europe">Western Europe</option>\n'
    '          <option value="north_america">North America</option>\n'
    '        </select>\n'
    '        <div id="region-insight" class="alert alert-info" style="display:none;font-size:.78rem;margin:.5rem 0"></div>\n\n'
    '        <div style="margin-top:1rem">\n'
    '          <button class="btn btn-primary btn-full" id="launch-btn" onclick="generateLaunch()">\n'
    '            &#9889; Generate All Content\n'
    '          </button>\n'
    '        </div>\n'
    '        <div id="launch-error" class="alert alert-error" style="display:none"></div>'
)
content = rep("region selector", OLD1, NEW1, content)

# -------------------------------------------------------------------------
# Change 2: Social card + video HTML (inject before TAB 6)
# -------------------------------------------------------------------------
BOUNDARY = "</div>\n</div>\n\n<!-- "
idx = content.find(BOUNDARY)
while idx != -1:
    chunk = content[idx : idx + 150]
    if "TAB 6" in chunk or "REVENUE" in chunk:
        break
    idx = content.find(BOUNDARY, idx + 1)

if idx != -1:
    INJECTION = (
        "\n\n  <!-- SOCIAL CARD GENERATOR -->\n"
        '  <div class="card" style="margin-top:1.2rem">\n'
        '    <div class="card-title">&#127912; Animated Social Card Generator</div>\n'
        '    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.2rem;align-items:start">\n'
        "      <div>\n"
        '        <label for="card-size">Card Size</label>\n'
        '        <select id="card-size" onchange="updateCardPreview()">\n'
        '          <option value="square">Instagram Square (1080x1080)</option>\n'
        '          <option value="landscape">Twitter/LinkedIn (1200x630)</option>\n'
        '          <option value="story">Story / TikTok (1080x1920)</option>\n'
        "        </select>\n"
        '        <label for="card-style">Background Style</label>\n'
        '        <select id="card-style" onchange="updateCardPreview()">\n'
        '          <option value="purple">Gradient Purple</option>\n'
        '          <option value="dark">Gradient Dark</option>\n'
        '          <option value="sunset">Gradient Sunset</option>\n'
        '          <option value="ocean">Gradient Ocean</option>\n'
        '          <option value="black">Solid Black</option>\n'
        "        </select>\n"
        '        <label for="card-name">Product Name</label>\n'
        '        <input type="text" id="card-name" placeholder="e.g. GameForge" oninput="updateCardPreview()"/>\n'
        '        <label for="card-tagline">Tagline (max 60 chars)</label>\n'
        '        <input type="text" id="card-tagline" maxlength="60" placeholder="e.g. Send games, not just gifts" oninput="updateCardPreview()"/>\n'
        '        <label for="card-url">URL (short)</label>\n'
        '        <input type="text" id="card-url" placeholder="e.g. gameforge.app" oninput="updateCardPreview()"/>\n'
        '        <label for="card-accent">Accent Colour</label>\n'
        '        <input type="color" id="card-accent" value="#5b6ef7" oninput="updateCardPreview()" style="width:60px;height:32px;padding:2px;cursor:pointer"/>\n'
        '        <div style="margin-top:.8rem;display:flex;gap:.5rem">\n'
        '          <button class="btn btn-secondary" style="flex:1" onclick="updateCardPreview()">&#128065; Preview</button>\n'
        '          <button class="btn btn-success" style="flex:1" onclick="downloadSocialCard()">&#11123; Download PNG</button>\n'
        "        </div>\n"
        "      </div>\n"
        '      <div style="text-align:center">\n'
        '        <canvas id="social-card-canvas" width="300" height="300"\n'
        '          style="border-radius:12px;width:100%;max-width:300px;border:1px solid var(--border2);cursor:pointer"\n'
        '          onclick="downloadSocialCard()" title="Click to download full-size PNG"></canvas>\n'
        '        <div style="font-size:.72rem;color:var(--text4);margin-top:.4rem">Click to download full-size PNG</div>\n'
        '        <div style="margin-top:.5rem;font-size:.72rem;color:var(--text3)">&#128039; AI-DAN Dodo mascot included</div>\n'
        "      </div>\n"
        "    </div>\n"
        "  </div>\n\n"
        "  <!-- PROMO VIDEO GENERATOR -->\n"
        '  <div class="card" style="margin-top:1.2rem">\n'
        '    <div class="card-title">&#127916; AI Promo Video Generator '
        '<span style="font-size:.7rem;color:var(--text3);font-weight:400;margin-left:.5rem">'
        "Free &bull; GitHub Actions &bull; ~3 min</span></div>\n"
        '    <div class="alert alert-info" style="font-size:.78rem;margin-bottom:.8rem">\n'
        "      &#128161; AI writes a creative video script (Grok/OpenAI), then renders a free MP4 via GitHub Actions.\n"
        "    </div>\n"
        '    <div style="display:grid;grid-template-columns:1fr 1fr;gap:.8rem">\n'
        "      <div>\n"
        '        <label for="vid-product">Product Name</label>\n'
        '        <input type="text" id="vid-product" placeholder="e.g. GameForge"/>\n'
        '        <label for="vid-tagline">Tagline</label>\n'
        '        <input type="text" id="vid-tagline" placeholder="e.g. Send games, not just gifts"/>\n'
        '        <label for="vid-url">Product URL</label>\n'
        '        <input type="url" id="vid-url" placeholder="https://..."/>\n'
        "      </div>\n"
        "      <div>\n"
        '        <label for="vid-region">Target Region</label>\n'
        '        <select id="vid-region">\n'
        '          <option value="global">&#127758; Global</option>\n'
        '          <option value="mena">MENA</option>\n'
        '          <option value="africa">Africa</option>\n'
        '          <option value="south_asia">South Asia</option>\n'
        '          <option value="southeast_asia">Southeast Asia</option>\n'
        '          <option value="latam">Latin America</option>\n'
        '          <option value="europe">Europe</option>\n'
        '          <option value="north_america">North America</option>\n'
        "        </select>\n"
        '        <div style="margin-top:.6rem">\n'
        '          <label style="display:flex;align-items:center;gap:.5rem;cursor:pointer;font-weight:normal;font-size:.85rem">\n'
        '            <input type="checkbox" id="vid-ai-concept" checked style="width:auto;margin:0"/>\n'
        "            &#10024; Use AI to write video script\n"
        "          </label>\n"
        "        </div>\n"
        '        <div style="margin-top:.8rem">\n'
        '          <button class="btn btn-primary btn-full" id="vid-btn" onclick="triggerVideoGeneration()">\n'
        "            &#127916; Generate Free Promo Video\n"
        "          </button>\n"
        "        </div>\n"
        '        <div id="vid-result" style="margin-top:.6rem;font-size:.78rem"></div>\n'
        "      </div>\n"
        "    </div>\n"
        "  </div>"
    )
    content = content[:idx] + INJECTION + content[idx:]
    print(f"  OK   social card + video injection at pos {idx}")
else:
    print("  SKIP social card injection: TAB6 boundary not found")

# -------------------------------------------------------------------------
# Change 3: Region in generateLaunch() payload
# -------------------------------------------------------------------------
OLD3 = (
    "  const payload = {\n"
    "    project_id: projId || null,\n"
    "    title: title,\n"
    "    url: url,\n"
    "    description: desc,\n"
    "    target_user: document.getElementById('launch-user').value.trim(),\n"
    "    cta: document.getElementById('launch-cta').value.trim(),\n"
    "  };"
)
NEW3 = (
    "  const payload = {\n"
    "    project_id: projId || null,\n"
    "    title: title,\n"
    "    url: url,\n"
    "    description: desc,\n"
    "    target_user: document.getElementById('launch-user').value.trim(),\n"
    "    cta: document.getElementById('launch-cta').value.trim(),\n"
    "    target_region: (document.getElementById('launch-region') || {}).value || 'global',\n"
    "  };"
)
content = rep("region in payload", OLD3, NEW3, content)

# -------------------------------------------------------------------------
# Change 4: New JS functions (append after savePaymentLink)
# -------------------------------------------------------------------------
OLD6_ANCHOR = (
    "function savePaymentLink() {\n"
    "  const url = document.getElementById('payment-url').value.trim();\n"
    "  if (!url) return;\n"
    "  localStorage.setItem('payment_link', url);\n"
)
NEW_JS = r"""
const REGION_NOTES={global:null,mena:'&#128161; MENA: Instagram+Snapchat lead. WhatsApp forwards = #1 viral. Arabic content outperforms English.',africa:'&#128161; Africa: WhatsApp group forwards are massive. Facebook groups drive trust. Short videos win.',south_asia:'&#128161; South Asia: WhatsApp groups = viral channel #1. High price sensitivity \u2014 offer free/cheap tier.',southeast_asia:'&#128161; SE Asia: Facebook dominant in PH/MY/ID. TikTok exploding in TH/VN. Playful tone wins.',latam:'&#128161; LatAm: Instagram Stories & Reels dominate. Emotional storytelling beats feature lists.',europe:'&#128161; Europe: Privacy-conscious \u2014 mention data safety. LinkedIn for B2B. TikTok growing in UK/DE.',north_america:'&#128161; North America: Reddit & X for community. TikTok for consumer. LinkedIn for B2B.'};
function onRegionChange(){var r=(document.getElementById('launch-region')||{}).value||'global';var el=document.getElementById('region-insight');var n=REGION_NOTES[r];if(el){if(n){el.innerHTML=n;el.style.display='block';}else el.style.display='none';}var vr=document.getElementById('vid-region');if(vr)vr.value=r;}
const CARD_GRADIENTS={purple:['#1a0533','#3d1470','#5b1ea8','#7c3aed'],dark:['#0a0a0a','#1a1a2e','#16213e','#0f3460'],sunset:['#1a0520','#6b1a1a','#c0392b','#e67e22'],ocean:['#0a1628','#1a3a5c','#0e7490','#22d3ee'],black:['#000','#111','#111','#000']};
function drawDodoOnCanvas(ctx,x,y,sz){var s=sz/100;ctx.save();ctx.translate(x,y);ctx.scale(s,s);ctx.beginPath();ctx.ellipse(50,62,28,26,0,0,Math.PI*2);ctx.fillStyle='#6B4DFF';ctx.fill();ctx.beginPath();ctx.ellipse(50,67,16,18,0,0,Math.PI*2);ctx.fillStyle='#e8e8ff';ctx.fill();ctx.beginPath();ctx.arc(50,36,18,0,Math.PI*2);ctx.fillStyle='#6B4DFF';ctx.fill();ctx.beginPath();ctx.arc(43,32,7,0,Math.PI*2);ctx.fillStyle='white';ctx.fill();ctx.beginPath();ctx.arc(57,32,7,0,Math.PI*2);ctx.fillStyle='white';ctx.fill();ctx.beginPath();ctx.arc(44,33,3.5,0,Math.PI*2);ctx.fillStyle='#1a1a2e';ctx.fill();ctx.beginPath();ctx.arc(58,33,3.5,0,Math.PI*2);ctx.fillStyle='#1a1a2e';ctx.fill();ctx.beginPath();ctx.moveTo(47,40);ctx.lineTo(53,40);ctx.lineTo(50,46);ctx.closePath();ctx.fillStyle='#f59e0b';ctx.fill();ctx.restore();}
var _cHue=0,_cAF=null;
function updateCardPreview(){var cv=document.getElementById('social-card-canvas');if(!cv)return;var ctx=cv.getContext('2d');var st=(document.getElementById('card-style')||{value:'purple'}).value||'purple';var sk=(document.getElementById('card-size')||{value:'square'}).value||'square';var pn=(document.getElementById('card-name')||{value:''}).value||'Your Product';var tg=(document.getElementById('card-tagline')||{value:''}).value||'Your tagline here';var ut=(document.getElementById('card-url')||{value:''}).value||'yourproduct.com';var ac=(document.getElementById('card-accent')||{value:'#5b6ef7'}).value||'#5b6ef7';var wh={square:[300,300],landscape:[300,158],story:[169,300]}[sk]||[300,300];var w=wh[0],h=wh[1];cv.width=w;cv.height=h;if(_cAF){cancelAnimationFrame(_cAF);_cAF=null;}function df(){_cHue=(_cHue+0.6)%360;ctx.save();ctx.filter='hue-rotate('+_cHue+'deg)';var g=CARD_GRADIENTS[st]||CARD_GRADIENTS.purple;var grd=ctx.createLinearGradient(0,0,w,h);grd.addColorStop(0,g[0]);grd.addColorStop(0.35,g[1]);grd.addColorStop(0.7,g[2]);grd.addColorStop(1,g[3]);ctx.fillStyle=grd;ctx.fillRect(0,0,w,h);ctx.filter='none';ctx.restore();drawDodoOnCanvas(ctx,w-42,h-52,40);ctx.textAlign='center';ctx.shadowColor='rgba(0,0,0,0.5)';ctx.fillStyle='#fff';ctx.font='bold '+Math.round(w*0.09)+'px system-ui,sans-serif';ctx.shadowBlur=8;ctx.fillText(pn,w/2,h*0.38);ctx.font=Math.round(w*0.052)+'px system-ui,sans-serif';ctx.fillStyle='rgba(255,255,255,0.85)';ctx.shadowBlur=4;var wd=tg.split(' '),ln='',lns=[],mW=w*0.82;wd.forEach(function(d){var t=ln+(ln?' ':'')+d;if(ctx.measureText(t).width>mW&&ln){lns.push(ln);ln=d;}else ln=t;});if(ln)lns.push(ln);var lh=Math.round(w*0.065),sy=h*0.52;lns.forEach(function(l,i){ctx.fillText(l,w/2,sy+i*lh);});ctx.font=Math.round(w*0.042)+'px system-ui,sans-serif';ctx.fillStyle=ac;ctx.shadowBlur=0;ctx.fillText(ut,w/2,h*0.85);var gl=Math.abs(Math.sin(_cHue*Math.PI/180))*5+2;ctx.strokeStyle=ac;ctx.lineWidth=gl;ctx.strokeRect(1,1,w-2,h-2);_cAF=requestAnimationFrame(df);}df();}
function downloadSocialCard(){var sk=(document.getElementById('card-size')||{value:'square'}).value||'square';var fd={square:[1080,1080],landscape:[1200,630],story:[1080,1920]}[sk]||[1080,1080];var fw=fd[0],fh=fd[1];var off=document.createElement('canvas');off.width=fw;off.height=fh;var ctx=off.getContext('2d');var st=(document.getElementById('card-style')||{value:'purple'}).value||'purple';var pn=(document.getElementById('card-name')||{value:''}).value||'Your Product';var tg=(document.getElementById('card-tagline')||{value:''}).value||'tagline';var ut=(document.getElementById('card-url')||{value:''}).value||'yourproduct.com';var ac=(document.getElementById('card-accent')||{value:'#5b6ef7'}).value||'#5b6ef7';var g=CARD_GRADIENTS[st]||CARD_GRADIENTS.purple;var grd=ctx.createLinearGradient(0,0,fw,fh);grd.addColorStop(0,g[0]);grd.addColorStop(0.35,g[1]);grd.addColorStop(0.7,g[2]);grd.addColorStop(1,g[3]);ctx.fillStyle=grd;ctx.fillRect(0,0,fw,fh);drawDodoOnCanvas(ctx,fw-110,fh-140,100);ctx.textAlign='center';ctx.shadowColor='rgba(0,0,0,0.5)';ctx.fillStyle='#fff';ctx.font='bold '+Math.round(fw*0.09)+'px system-ui,sans-serif';ctx.shadowBlur=15;ctx.fillText(pn,fw/2,fh*0.38);ctx.font=Math.round(fw*0.052)+'px system-ui,sans-serif';ctx.fillStyle='rgba(255,255,255,0.85)';ctx.shadowBlur=8;var wd=tg.split(' '),ln='',lns=[],mW=fw*0.82;wd.forEach(function(d){var t=ln+(ln?' ':'')+d;if(ctx.measureText(t).width>mW&&ln){lns.push(ln);ln=d;}else ln=t;});if(ln)lns.push(ln);var lh=Math.round(fw*0.065),sy=fh*0.52;lns.forEach(function(l,i){ctx.fillText(l,fw/2,sy+i*lh);});ctx.font=Math.round(fw*0.042)+'px system-ui,sans-serif';ctx.fillStyle=ac;ctx.shadowBlur=0;ctx.fillText(ut,fw/2,fh*0.85);ctx.strokeStyle=ac;ctx.lineWidth=6;ctx.strokeRect(3,3,fw-6,fh-6);off.toBlob(function(b){var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=(pn.replace(/\s+/g,'-').toLowerCase()||'card')+'-'+sk+'.png';a.click();URL.revokeObjectURL(a.href);toast('Social card downloaded!','success');},'image/png');}
function triggerVideoGeneration(){var p=(document.getElementById('vid-product')||{}).value||'';var tg=(document.getElementById('vid-tagline')||{}).value||'';var u=(document.getElementById('vid-url')||{}).value||'';var r=(document.getElementById('vid-region')||{}).value||'global';var ai=(document.getElementById('vid-ai-concept')||{}).checked||false;if(!p.trim()){toast('Enter a product name first','warn');return;}var btn=document.getElementById('vid-btn'),res=document.getElementById('vid-result');btn.disabled=true;btn.innerHTML='<span class="spinner"></span> Triggering...';res.innerHTML='';apiFetch('/api/distribution/generate-video',{method:'POST',body:JSON.stringify({title:p.trim(),description:tg||p.trim(),url:u||'https://example.com',target_region:r,use_ai_concept:ai})}).then(function(d){var h='<div class="alert alert-success">&#10003; Video job started!</div>';if(d.workflow_url)h+='<div style="margin-top:.4rem">&#128279; <a href="'+esc(d.workflow_url)+'" target="_blank">Track on GitHub Actions</a></div>';if(d.note)h+='<div style="color:var(--text3);font-size:.76rem;margin-top:.3rem">&#9432; '+esc(d.note)+'</div>';res.innerHTML=h;toast('Video triggered!','success');}).catch(function(e){res.innerHTML='<div class="alert alert-error">'+esc(e.message)+'</div>';toast('Video failed: '+e.message,'error');}).finally(function(){btn.disabled=false;btn.innerHTML='&#127916; Generate Free Promo Video';});}
"""

if OLD6_ANCHOR in content:
    insert_pos = content.find(OLD6_ANCHOR)
    content = content[:insert_pos] + NEW_JS + content[insert_pos:]
    print("  OK   new JS functions")
else:
    print("  SKIP new JS functions: anchor not found")

# -------------------------------------------------------------------------
# Push
# -------------------------------------------------------------------------
print(f"Final size: {len(content)} chars")
result = github_put(
    PATH,
    content,
    sha,
    "feat: social card generator, promo video trigger, region insights UI\n\nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>",
)
print(f"SUCCESS: {result['commit']['html_url']}")
