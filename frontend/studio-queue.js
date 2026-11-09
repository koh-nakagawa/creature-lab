import {CreatureViewer} from './viewer.js';
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let busy=false,last='',latest=[];
async function api(path,data){const r=await fetch(path,{method:data?'POST':'GET',headers:{'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});const v=await r.json();if(!r.ok)throw new Error(v.error);return v;}
const time=s=>Math.floor(s/60)+'分'+String(Math.round(s%60)).padStart(2,'0')+'秒';
function render(items){const shown=items.filter(v=>$('show-sent').checked||v.status!=='sent_by_operator');$('count').textContent='未送信 '+items.filter(v=>v.status!=='sent_by_operator').length+'件';$('queue').replaceChildren();
 for(const v of shown){const card=document.createElement('article');card.className='request';const status={queued:'受付済み',opened:'Studioへ渡した',sent_by_operator:'スタッフが送信済みと記録'}[v.status]||v.status;
  card.innerHTML=`<div class="request-top"><div><small>受付 ${esc(v.id.slice(0,6))} · ${esc(new Date(v.created*1000).toLocaleString('ja-JP'))}</small><h2>${esc(v.name)}</h2></div><span class="badge">${esc(status)}</span></div><div class="facts"><span>A1 mini / 0.6 mm / PLA / 標準100%</span><span>準備込み 約${time(v.total_seconds)}</span><span>${v.grams.toFixed(1)} g</span></div><div class="actions"><button class="primary open">Bambu Studioで開く</button><button class="sent" ${v.status==='queued'?'disabled':''}>送信済みとして記録</button><a href="${v.download_url}">印刷ファイルを保存</a></div>`;
  card.querySelector('.open').onclick=()=>act(v.id,'open');card.querySelector('.sent').onclick=()=>act(v.id,'sent');$('queue').appendChild(card);
 }if(!shown.length)$('queue').innerHTML='<p class="empty">印刷待ちはありません。<br>iPadで完成したら「Macへ印刷をお願いする」から送ってください。</p>';
}
async function refresh(){if(busy)return;try{const v=await api('/api/studio/queue');latest=v.items;const key=JSON.stringify([v.items,$('show-sent').checked]);if(last!==key){render(v.items);last=key;}}catch(e){$('message').textContent=e.message;}}
async function act(id,action){busy=true;for(const b of $('queue').querySelectorAll('button'))b.disabled=true;$('refresh').disabled=true;try{const v=await api('/api/studio/queue/'+id+'/'+action,{});$('message').textContent=action==='open'?v.message:'Studioで送信したことを記録しました。実際の印刷状態はStudioまたは本体で確認してください。';}catch(e){$('message').textContent=e.message;}finally{busy=false;last='';$('refresh').disabled=false;await refresh();}}
$('refresh').onclick=()=>{last='';refresh();};$('show-sent').onchange=()=>{last='';render(latest);};setInterval(refresh,3000);refresh();

let catalog=null,monitorBusy=false,monitorViewer=null,modelURL='',modelVersion=0,selectedSession='',autoFollow=true,lastActivity='',renderedSession='';
const monitorLabels={selecting:'パーツを選択中',chosen:'6つの選択が完了・iPadで準備を待っています',preparing:'モデル・印刷ファイルを準備中',ready:'モデル完成・印刷依頼待ち',queued:'モデル完成・Macで受付済み',opened:'Bambu Studioへ渡した',sent_by_operator:'スタッフが送信済みと記録',error:'準備に確認が必要です'};
const partLabel=(key,value)=>catalog?.groups.find(g=>g.key===key)?.options.find(o=>o.id===value)?.label||value;
async function monitor(){if(monitorBusy)return;monitorBusy=true;try{if(!catalog)catalog=await api('/api/catalog');const v=await api('/api/studio/monitor'),sessions=v.sessions,now=v.server_time;
 const remote=sessions.filter(s=>s.client_ip&&!['127.0.0.1','::1'].includes(s.client_ip));const latest=(remote.length?remote:sessions)[0];
 if(autoFollow&&latest)selectedSession=latest.id;if(!sessions.some(s=>s.id===selectedSession))selectedSession=latest?.id||'';
 const select=$('session-select'),options=sessions.map(s=>`<option value="${s.id}">${esc(new Date(s.started_at*1000).toLocaleTimeString('ja-JP'))} · ${esc(s.id.slice(0,6))} · ${esc(s.client_ip||'以前の体験')}</option>`).join('');if(select.innerHTML!==options)select.innerHTML=options;select.value=selectedSession;
 const s=sessions.find(s=>s.id===selectedSession);$('monitor-empty').hidden=!!s;$('monitor-content').hidden=!s;if(!s)return;if(renderedSession!==s.id){renderedSession=s.id;modelURL='';modelVersion++;monitorViewer?.clear();$('monitor-model-label').textContent='形の読み込みを待っています';}
 $('monitor-session').textContent='体験 '+s.id.slice(0,6)+' · '+(s.client_ip||'以前の体験');
 const key=s.step_key,g=catalog.groups.find(g=>g.key===key);$('monitor-stage').textContent=s.phase==='selecting'?`STEP ${s.step_index+1}/6 ${g.label}を選択中 · のこり${Math.max(0,Math.ceil(s.deadline-now))}秒`:monitorLabels[s.stage]||s.stage;
 const age=Math.max(0,Math.floor(now-s.last_seen_at));$('monitor-live').textContent=age<=8?'通信中':'最終通信 '+(age<60?age+'秒前':Math.floor(age/60)+'分前');$('monitor-live').classList.toggle('offline',age>8);
 $('monitor-steps').innerHTML=s.step_keys.map((k,i)=>`<li class="${s.phase==='complete'||i<s.step_index?'done':i===s.step_index?'current':''}">${s.phase==='complete'||i<s.step_index?'✓':i+1} ${esc(catalog.groups.find(g=>g.key===k).label)}</li>`).join('');
 $('monitor-parts').innerHTML=s.step_keys.map((k,i)=>`<span><small>${esc(catalog.groups.find(g=>g.key===k).label)}</small>${s.phase==='complete'||i<=s.step_index?esc(partLabel(k,s.config[k])):'まだ選んでいません'}</span>`).join('');
 $('monitor-ready').textContent=s.error?s.error:s.model_ready?'印刷用のモデルが完成しています。'+(s.request_id?'受付 '+s.request_id.slice(0,6):'iPadからの印刷依頼を待っています。'):'選択に合わせてモデルが更新されます。';
 const events=[...s.activity,...s.selections.filter(v=>v.reason==='timeout').map(v=>({at:v.finished_at,action:'timeout',key:v.key,value:v.value}))].sort((a,b)=>b.at-a.at).slice(0,12);const activity=JSON.stringify([s.id,events]);if(lastActivity!==activity){lastActivity=activity;$('monitor-activity').innerHTML=events.map(e=>`<li><time>${esc(new Date(e.at*1000).toLocaleTimeString('ja-JP'))}</time>${esc(e.action==='start'?'スタート':e.action==='choose'?'選択：'+partLabel(e.key,e.value):e.action==='timeout'?'時間切れで確定：'+partLabel(e.key,e.value):e.step_index===6?'6つの選択が完了':'次の段階へ進んだ')}</li>`).join('')||'<li>これからの操作がここに表示されます。</li>';}
 if(s.preview_url&&s.preview_url!==modelURL){modelURL=s.preview_url;const version=++modelVersion;if(!monitorViewer)monitorViewer=new CreatureViewer($('monitor-viewer'));$('monitor-model-label').textContent='モデルを読み込んでいます…';monitorViewer.load(s.preview_url,true).then(()=>{if(version===modelVersion)$('monitor-model-label').textContent=s.model_ready?'完成したモデル':'作成中のモデル';}).catch(()=>{if(version===modelVersion){modelURL='';$('monitor-model-label').textContent='モデルを読み直しています…';}});}
 if(s.preview_updating)$('monitor-model-label').textContent='新しいパーツへ更新中…';
 }catch(e){$('monitor-empty').textContent=e.message;$('message').textContent=e.message;$('monitor-live').textContent='Macサービスとの通信を確認しています';$('monitor-live').classList.add('offline');}finally{monitorBusy=false;}}
$('session-select').onchange=()=>{autoFollow=false;selectedSession=$('session-select').value;modelURL='';monitor();};$('follow-latest').onclick=()=>{autoFollow=true;monitor();};$('monitor-reset').onclick=()=>monitorViewer?.frame();setInterval(monitor,1000);monitor();
