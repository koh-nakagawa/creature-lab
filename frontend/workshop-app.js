import {CreatureViewer} from './viewer.js';

const $=id=>document.getElementById(id);
const STORE='creature-lab-workshop-v1';
const questions={body:'どのからだにする？',head:'どのあたまにする？',limbs:'あし・うではどれ？',tail:'どのしっぽにする？',eyes:'めは、いくつにする？',expression:'どんな顔にする？'};
const explanation=[
  {title:'パーツをえらんで<br>いきものをつくろう。',text:'からだ、あたま、あし、しっぽ、め、ひょうじょう。6つのパーツを組み合わせよう。',image:'dragon'},
  {title:'ひとつのパーツを<br>えらぶ時間は、1分。',text:'何回えらび直してもOK！ 決まったら「これにする」。時間が来たら、自動で次へ進むよ。',image:'octopus'},
  {title:'大きさやバランスは<br>おまかせで、ぴったり。',text:'目と口も自動で整うよ。完成したら名前をつけて、スタッフに印刷をお願いしよう。',image:'turtle'}
];
let catalog,boot,session=null,viewer=null,currentModel=null,currentSlice=null,prepared=null;
let introIndex=0,introTimer=null,serverOffset=0,polling=false,requestBusy=false,preparing=false,prepareStarted=false;
let previewVersion=0,previewBusy=false,previewAgain=false,previewTimer,lastPreviewConfig='',lastRenderedConfig='',lastRenderedStep=-1,announcedStep=-1;

const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const creatureLabel=value=>value.endsWith('もどき')?`<span class="creature-base">${esc(value.slice(0,-3))}</span><span class="creature-suffix">もどき</span>`:esc(value);
const clock=value=>{const s=Math.round(value);return `${Math.floor(s/60)}分${String(s%60).padStart(2,'0')}秒`;};
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const notice=message=>{$('notice').textContent=message;$('notice').hidden=!message;};
async function api(path,options={}){const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});const result=await response.json();if(!response.ok){const error=new Error(result.error||'Macとの接続を確認してください。');error.status=response.status;throw error;}return result;}
const post=(path,data={})=>api(path,{method:'POST',body:JSON.stringify(data)});
async function waitJob(job){for(let n=0;n<600;n++){if(job.status==='done')return job.result;if(job.status==='error')throw new Error(job.error||'準備できませんでした。');await pause(300);job=await api('/api/jobs/'+job.id);}throw new Error('時間がかかっています。スタッフを呼んでください。');}
function group(key){return catalog.groups.find(g=>g.key===key);}
function label(key,value){return group(key)?.options.find(o=>o.id===value)?.label||value;}
function workshopURL(action=''){return '/api/workshop/'+session.id+(action?'/'+action:'');}
function getViewer(){if(!viewer)viewer=new CreatureViewer($('viewer'));return viewer;}

function renderExplanation(){const item=explanation[introIndex];$('intro-number').textContent=(introIndex+1)+' / 3';$('intro-title').innerHTML=item.title;$('intro-text').textContent=item.text;$('intro-image').src='/thumbnails/preset_'+item.image+'.png';$('intro-image').alt=label('body',item.image)+'の見本';[...$('intro-dots').children].forEach((dot,i)=>dot.classList.toggle('active',i===introIndex));}
function showWelcome(){clearInterval(introTimer);introIndex=0;viewer?.clear();$('announcer').textContent='';$('welcome').hidden=false;$('workshop-screen').hidden=true;renderExplanation();introTimer=setInterval(()=>{if(!document.hidden){introIndex=(introIndex+1)%explanation.length;renderExplanation();}},6000);}
function drawTrack(){const keys=catalog.workshop.step_keys;$('step-track').innerHTML=keys.map((key,i)=>`<li class="${session.phase==='complete'||i<session.step_index?'done':i===session.step_index?'current':''}" ${i===session.step_index?'aria-current="step"':''}><span class="step-circle">${session.phase==='complete'||i<session.step_index?'✓':i+1}</span><span>${esc(group(key).label)}</span></li>`).join('');}
function drawSelected(){const config=prepared&&session.phase==='complete'?prepared.model.config:session.config;$('selected-parts').innerHTML=catalog.workshop.step_keys.map((key,i)=>`<span class="selected-chip ${session.phase!=='complete'&&i>session.step_index?'pending':''}">${esc(group(key).label)}：${session.phase==='complete'||i<=session.step_index?esc(label(key,config[key])):'おまかせ'}</span>`).join('');}
function drawOptions(){const key=session.step_key,g=group(key);$('part-options').replaceChildren();
  for(const option of g.options){const button=document.createElement('button');button.className='workshop-option'+(session.config[key]===option.id?' selected':'');button.setAttribute('aria-label',option.label);button.setAttribute('aria-pressed',String(session.config[key]===option.id));button.innerHTML=`<img src="/thumbnails/${key}_${option.id}.png" alt="" draggable="false"><span class="choice-label">${key==='body'?creatureLabel(option.label):esc(option.label)}</span>`;button.onclick=()=>choose(key,option.id);$('part-options').appendChild(button);}
  $('step-number').textContent='STEP '+(session.step_index+1)+' / '+catalog.workshop.step_keys.length;$('step-question').textContent=questions[key];
  $('next-step').innerHTML=(session.step_index===catalog.workshop.step_keys.length-1?'これで完成！':'これにする')+' <span>→</span>';
}
function applyState(value){
  if(session&&session.id===value.id&&value.server_time<session.server_time)return;
  const stepChanged=!session||session.id!==value.id||session.step_index!==value.step_index||session.phase!==value.phase;
  session=value;serverOffset=value.server_time*1000-Date.now();
  clearInterval(introTimer);$('welcome').hidden=true;$('workshop-screen').hidden=false;getViewer();
  const selecting=session.phase==='selecting';$('selection-panel').hidden=!selecting;$('finish-panel').hidden=selecting;
  $('workshop-screen').classList.toggle('is-complete',!selecting);$('auto-badge').textContent=selecting?'バランスはおまかせ':'6ステップ かんせい！';
  if(stepChanged)$('announcer').textContent=selecting?`${session.step_index+1}ばんめ。${questions[session.step_key]} えらぶ時間は1分です。`:'6つのパーツが決まりました。印刷の準備をしています。';
  $('journey-title').textContent=selecting?'きみのいきもの、つくろう。':'きみのいきもの、できあがり。';
  drawTrack();drawSelected();
  if(selecting){const serial=JSON.stringify(session.config);if(lastRenderedStep!==session.step_index||lastRenderedConfig!==serial){lastRenderedStep=session.step_index;lastRenderedConfig=serial;drawOptions();}if(lastPreviewConfig!==serial){lastPreviewConfig=serial;schedulePreview();}updateClock();}
  else{previewVersion++;clearTimeout(previewTimer);$('model-loading').hidden=true;if(!prepareStarted)prepareResult();}
}
function updateClock(){if(!session||session.phase!=='selecting')return;
  const seconds=Math.max(0,Math.ceil((session.deadline*1000-Date.now()-serverOffset)/1000));
  $('step-timer').textContent=Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');
  $('time-fill').style.width=Math.min(100,seconds/session.step_seconds*100)+'%';$('timer-box').classList.toggle('urgent',seconds<=10);
  for(const button of $('part-options').children)button.disabled=requestBusy||seconds<=0;
  $('next-step').disabled=requestBusy||seconds<=0;
  if(seconds<=10&&announcedStep!==session.step_index){announcedStep=session.step_index;$('announcer').textContent='のこり10秒です。いま選んでいる形で次へ進みます。';}
  if(seconds===0)synchronize();
}
async function synchronize(){if(polling||!session)return;polling=true;const id=session.id;try{const value=await api(workshopURL());if(session?.id===id){if(session.phase==='selecting')applyState(value);else session=value;}}catch(error){notice('Macとの接続を確認しています。時間はそのまま進みます。');}finally{polling=false;}}
async function start(){const button=$('start-button');button.disabled=true;notice('');try{session=null;currentModel=null;currentSlice=null;prepared=null;prepareStarted=false;preparing=false;lastRenderedStep=-1;lastRenderedConfig='';lastPreviewConfig='';announcedStep=-1;$('creature-name').value='';$('finish-ready').hidden=true;$('retry-prepare').hidden=true;$('preparing').hidden=false;
    $('stage-label').textContent='カタチをつくっています';$('model-size').textContent='大きさはおまかせ';$('model-loading').hidden=false;
    const value=await post('/api/workshop/start');localStorage.setItem(STORE,value.id);applyState(value);
  }catch(error){notice(error.message);}finally{button.disabled=false;}}
async function choose(key,value){if(requestBusy||!session||session.phase!=='selecting')return;requestBusy=true;updateClock();try{applyState(await post(workshopURL('choose'),{step_index:session.step_index,key,value}));}catch(error){notice(error.message);}finally{requestBusy=false;updateClock();}}
async function next(){if(requestBusy||!session||session.phase!=='selecting')return;requestBusy=true;updateClock();try{applyState(await post(workshopURL('next'),{step_index:session.step_index}));}catch(error){notice(error.message);}finally{requestBusy=false;updateClock();}}

function schedulePreview(){previewVersion++;clearTimeout(previewTimer);previewTimer=setTimeout(loadPreview,180);}
async function loadPreview(){if(!session||session.phase!=='selecting')return;if(previewBusy){previewAgain=true;return;}
  const version=previewVersion,id=session.id;previewBusy=true;previewAgain=false;$('model-loading').hidden=false;
  try{const model=await waitJob(await post(workshopURL('preview')));if(session?.id===id&&session.phase==='selecting'&&version===previewVersion){await getViewer().load(model.stl_url,!currentModel);if(version===previewVersion){currentModel=model;$('stage-label').textContent='きみのオリジナル生物';$('model-size').textContent='大きさはおまかせ';}}}
  catch(error){if(version===previewVersion)notice('形を確認できませんでした。別のパーツを選ぶか、スタッフを呼んでください。');}
  finally{previewBusy=false;if((previewAgain||version!==previewVersion)&&session?.phase==='selecting'){previewAgain=false;loadPreview();}else $('model-loading').hidden=true;}
}
async function prepareResult(){if(preparing||!session)return;preparing=true;prepareStarted=true;$('finish-ready').hidden=true;$('retry-prepare').hidden=true;$('preparing').hidden=false;$('finish-title').textContent='カタチが決まったね！';$('finish-message').textContent='大きさを整えて、印刷の準備をしています。';
  try{const id=session.id;const value=await waitJob(await post(workshopURL('prepare')));if(session?.id!==id)return;prepared=value;currentModel=value.model;currentSlice=value.slice;
    await getViewer().load(currentModel.stl_url,true);$('stage-label').textContent='完成！ きみのオリジナル生物';$('model-size').textContent='約'+Math.max(...currentModel.geometry.dimensions_mm).toFixed(0)+' mm';
    $('finish-title').textContent='できあがり！';$('finish-message').textContent='名前をつけて、スタッフに見せよう。';$('preparing').hidden=true;$('finish-ready').hidden=false;
    $('slice-summary').innerHTML=`<strong>印刷は 約${clock(currentSlice.total_seconds)}</strong><small>造形 ${clock(currentSlice.model_seconds)} · PLA ${currentSlice.grams.toFixed(1)} g<br>選んだ時間も含めると 約${clock(value.estimated_elapsed_seconds)}。<br>冷却・取り外しは別です。見積もり時間です。</small>`;
    drawSelected();if(value.warning)notice(value.warning);else notice('');
  }catch(error){$('preparing').hidden=true;$('finish-title').textContent='スタッフを呼んでね';$('finish-message').textContent=error.message;$('retry-prepare').hidden=false;}
  finally{preparing=false;}
}
function nextPerson(){previewVersion++;clearTimeout(previewTimer);session=null;prepared=null;currentModel=null;currentSlice=null;prepareStarted=false;lastPreviewConfig='';lastRenderedConfig='';lastRenderedStep=-1;localStorage.removeItem(STORE);notice('');showWelcome();window.scrollTo({top:0,behavior:'smooth'});}
function download(url){const a=document.createElement('a');a.href=url;a.download='';document.body.appendChild(a);a.click();a.remove();}
function blobDownload(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);}
function name(){return $('creature-name').value.trim()||label('body',currentModel.config.body);}
function saveCard(){if(!currentModel||!viewer)return;const canvas=document.createElement('canvas');canvas.width=1000;canvas.height=1220;const c=canvas.getContext('2d');c.fillStyle='#f6f5ef';c.fillRect(0,0,1000,1220);c.fillStyle='#397d65';c.font='600 24px sans-serif';c.fillText('CREATURE LAB · わたしのいきもの図鑑',65,80);c.fillStyle='#e6ece1';c.fillRect(45,125,910,720);const image=new Image();image.onload=()=>{const aspect=image.width/image.height,w=Math.min(900,690*aspect),h=w/aspect;c.drawImage(image,(1000-w)/2,140+(690-h)/2,w,h);c.fillStyle='#253b35';c.font='600 48px sans-serif';c.fillText(name().slice(0,18),65,925);c.font='22px sans-serif';c.fillText(['body','head','eyes'].map(k=>label(k,currentModel.config[k])).join(' / '),65,980);c.fillText(['limbs','tail','expression'].map(k=>label(k,currentModel.config[k])).join(' / '),65,1020);c.fillStyle='#75847b';c.font='20px sans-serif';c.fillText('発見した日：'+new Date().toLocaleDateString('ja-JP'),65,1110);canvas.toBlob(blob=>blobDownload(blob,'creature-card.png'));};image.src=viewer.image();}

async function openPrint(){if(!currentSlice)return;boot=await api('/api/bootstrap');const s=currentSlice;$('print-details').innerHTML=[['なまえ',name()],['印刷する場所','MacのBambu Studio → A1 mini'],['ノズル / 素材','0.6 mm / PLA'],['速度','標準 100%'],['準備込みの見積もり',clock(s.total_seconds)],['造形のみ',clock(s.model_seconds)]].map(([k,v])=>`<div class="print-fact"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>`).join('');$('print-status').textContent=!boot.staff?'右上の設定から、Macに表示される6桁のコードでこのiPadを接続してください。':!boot.studio_available?'MacにBambu Studioが見つかりません。':'受付するとMacの印刷待ちに表示されます。スタッフがStudioで印刷を開始します。';$('print-submit').disabled=!boot.staff||!boot.studio_available;$('print-submit').textContent=boot.staff?'Macの印刷待ちへ送る →':'Macとの接続が必要です';$('print-dialog').showModal();}
async function printNow(){$('print-submit').disabled=true;$('print-status').textContent='印刷ファイルをMacの印刷待ちへ送っています…';try{const result=await waitJob(await post('/api/print',{slice_id:currentSlice.id,name:name(),confirmed:true}));$('print-status').textContent='受付 '+result.queue_id.slice(0,6)+'：'+result.message;$('print-submit').textContent='Macで受け付けました';}catch(error){$('print-status').textContent=error.message+' スタッフを呼んでください。';}}
async function openSettings(){boot=await api('/api/bootstrap');$('pairing-section').hidden=boot.staff;$('staff-settings').hidden=!boot.staff;if(boot.staff){$('ipad-link').innerHTML='<div>iPad miniのSafariで開く</div>'+boot.ipad_urls.map(u=>`<a href="${esc(u)}">${esc(u)}</a>`).join('<br>')+(boot.pairing_code?`<div>iPad接続コード：<strong>${esc(boot.pairing_code)}</strong></div>`:'');$('studio-queue-link').hidden=!boot.local;$('studio-status').textContent=boot.studio_available?(boot.local?'Bambu Studioを確認できました。下の印刷待ちからファイルを開いて送信します。':'Mac側で印刷待ちを開いて、Studioから送信してください。'):'このMacにBambu Studioが見つかりません。';$('staff-downloads').hidden=!currentSlice;}$('settings-dialog').showModal();}
function saveSettings(event){event.preventDefault();if(!boot?.staff)pair();}
async function pair(){try{await post('/api/session',{code:$('pair-code').value});$('settings-dialog').close();await openSettings();}catch(error){$('pairing-section').querySelector('p').textContent=error.message;}}

async function init(){try{[catalog,boot]=await Promise.all([api('/api/catalog'),api('/api/bootstrap')]);const id=localStorage.getItem(STORE);if(id){try{applyState(await api('/api/workshop/'+id));return;}catch(error){if(error.status!==404)throw error;localStorage.removeItem(STORE);}}showWelcome();}catch(error){notice('Macに接続できません。 '+error.message);}}
$('start-button').onclick=start;$('next-step').onclick=next;$('view-reset').onclick=()=>viewer?.frame();$('retry-prepare').onclick=()=>{prepareStarted=false;prepareResult();};$('next-person').onclick=nextPerson;$('save-card').onclick=saveCard;$('open-print').onclick=()=>openPrint().catch(e=>notice(e.message));$('print-submit').onclick=printNow;
$('settings-open').onclick=()=>openSettings().catch(e=>notice(e.message));$('settings-form').onsubmit=saveSettings;$('pair-button').onclick=pair;
$('download-3mf').onclick=()=>currentSlice&&download(currentSlice.download_url);$('download-3mf-staff').onclick=()=>currentSlice&&download(currentSlice.download_url);$('download-stl').onclick=()=>currentModel&&download(currentModel.stl_url);
for(const button of document.querySelectorAll('.close-dialog'))button.onclick=()=>button.closest('dialog').close();
setInterval(updateClock,150);setInterval(synchronize,1000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)synchronize();});init();
