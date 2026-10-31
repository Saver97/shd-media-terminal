'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<svg class="icon" aria-hidden="true"><use href="#icon-${name}"></use></svg>`;
const size = n => !Number.isFinite(n) ? '—' : n >= 1073741824 ? (n/1073741824).toFixed(2)+' GB' : n >= 1048576 ? (n/1048576).toFixed(1)+' MB' : (n/1024).toFixed(0)+' KB';
const state = {view:'discover', items:[], selected:null, query:'', page:1, hasMore:false, tasks:[], history:[], subscriptions:[], settings:{}, fileRequest:null, taskFilter:'all', request:0, fileToken:0, busy:false};
let backend, nextId=0, toastTimer, polling=false;
const pending = new Map();
function api(method, data={}) { return new Promise((resolve,reject)=>{if(!backend)return reject(Error('桌面连接尚未就绪'));const id=String(++nextId);const timer=setTimeout(()=>{pending.delete(id);reject(Error('操作仍未完成，请稍后检查任务状态'));},120000);pending.set(id,{resolve,reject,timer});backend.request(id,method,JSON.stringify(data));}); }
function toast(message,error=false) { $('toast').textContent=message; $('toast').classList.toggle('failure',error);$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,error?10000:5000); }
async function attempt(fn) { try{return await fn();}catch(e){toast(e.message,true);} }
function empty(title, body) {return `<div class="empty"><div class="empty-mark">◇</div><h3>${esc(title)}</h3><p>${esc(body)}</p></div>`;}
function setView(view) {state.view=view;document.body.classList.toggle('calendar-mode',view==='calendar');const names={calendar:['新番日历','WEEKLY BROADCAST'],discover:['发现资源','RESOURCE DISCOVERY'],subscriptions:['我的追番','FOLLOWED SERIES'],history:['交接记录','HANDOFF HISTORY']};document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));Object.keys(names).forEach(k=>$('view-'+k).hidden=k!==view);$('heading').textContent=names[view][0];$('section-code').textContent=names[view][1];if(view==='calendar'&&backend&&!calendarState.data&&!calendarState.loading)loadCalendar();renderHistory();renderSubscriptions();if(backend&&(view==='subscriptions'||view==='history'))attempt(async()=>{const lib=await api('library');state.history=lib.history;state.subscriptions=lib.subscriptions;renderHistory();renderSubscriptions();});}
function selected(item, query='') {state.selected=item;state.selectedQuery=query;$('detail-ep').textContent=item.episode||'—';let title=query||item.title;const match=item.title.match(/\[(?:国漫|國漫)\]\[([^\]]+)\]/);if(match)title=match[1];$('detail-title').textContent=title.length>32?title.slice(0,32)+'…':title;$('detail-group').textContent=item.group||'未标注发布组';for(const [id,key] of [['publisher','group'],['quality','quality'],['subtitle','subtitle'],['size','size'],['seeds','seeds']])$('detail-'+id).textContent=item[key]||'—';$('detail-raw').textContent=item.title;['detail-download','detail-subscribe'].forEach(id=>$(id).disabled=false);renderResults();}
function resourceCard(r, multi=false) {return `<article class="resource ${state.selected?.hash===r.hash?'selected':''}"><div class="row">${multi?`<input type="checkbox" class="resource-check" data-check="${r.hash}" aria-label="选择 ${esc(r.title)}" ${subscriptionSelection.has(r.hash)?'checked':''}>`:''}<button class="pick" data-select="${r.hash}">${esc(r.title)}</button><span class="badge">${esc(r.quality)}</span></div><div class="metadata">${esc(r.group||'未标注发布组')} · ${esc(r.subtitle)} · ${esc(r.size)} · 做种 ${esc(r.seeds)}</div><div class="row"><span class="date">${esc(r.date)} / 动漫花园</span><div class="actions"><button data-download="${r.hash}">${icon('download')}迅雷下载</button></div></div></article>`;}
function bindResources(container, items, query='') {container.querySelectorAll('[data-select]').forEach(b=>b.onclick=()=>selected(items.find(r=>r.hash===b.dataset.select),query));for(const action of ['download'])container.querySelectorAll('[data-'+action+']').forEach(b=>b.onclick=()=>attempt(async()=>{const r=items.find(r=>r.hash===b.dataset[action]);selected(r,query);await handoff(r);}));}
function renderResults() {if(!state.query)return;const rows=state.items.filter(r=>(!$('filter-quality').value||r.quality===$('filter-quality').value)&&(!$('filter-subtitle').value||r.subtitle===$('filter-subtitle').value));$('result-count').textContent=`本页 ${rows.length} 个资源 / ${state.query}`;$('results').innerHTML=rows.map(r=>resourceCard(r)).join('')||empty('没有找到匹配资源','可尝试简繁体名称、英文名，或清除筛选条件。');bindResources($('results'),rows,state.query);$('pagination').hidden=false;$('page-number').textContent='第 '+state.page+' 页';$('previous-page').disabled=state.page===1;$('next-page').disabled=!state.hasMore;}
async function search(page=1) {const query=$('search-query').value.trim();if(!query)return;const serial=++state.request;$('search-button').disabled=true;$('search-button').textContent='搜索中…';try{const result=await api('search',{query,page});if(serial!==state.request)return;state.items=result.items;state.query=query;state.page=page;state.hasMore=result.has_more;renderResults();if(result.items.length)selected(result.items[0],query);}finally{if(serial===state.request){$('search-button').disabled=false;$('search-button').textContent='搜索';}}}
function showDialog(id){$(id).showModal();}
async function handoff(resource){if(state.busy)return;state.busy=true;try{const result=await api('launch_thunder',{resource});state.history=result.history;renderHistory();toast('已向迅雷发送磁链，请在迅雷中选择文件和保存位置。');}finally{state.busy=false;}}
function renderHistory(){$('history-list').innerHTML=state.history.map((h,i)=>`<article class="resource"><div class="pick history-title">${esc(h.title)}</div><div class="row"><span class="metadata">${esc(h.time)} · 已发送启动请求</span><button data-history="${i}">再次交给迅雷</button></div></article>`).join('')||empty('还没有交接记录','点击资源的“迅雷下载”后，会记录在这里。');$('history-list').querySelectorAll('[data-history]').forEach(b=>b.onclick=()=>attempt(()=>handoff(state.history[Number(b.dataset.history)].resource)));}

function openSubscription(item=null){$('sub-query').value=item?(state.selectedQuery||item.title):(state.query||$('search-query').value.trim());$('sub-group').value=item?.group||'';$('sub-quality').value=item?.quality==='未标注'?'':item?.quality||'';$('sub-subtitle').value=item?.subtitle==='未标注'?'':item?.subtitle||'';$('subscribe-error').textContent='';showDialog('subscribe-dialog');}
const foldedSubscriptions = (()=>{try{const ids=JSON.parse(localStorage.getItem('shd.subscriptionFolds')||'[]');return new Set(Array.isArray(ids)?ids.filter(x=>typeof x==='string'):[]);}catch{return new Set();}})();
function saveSubscriptionFolds(){try{localStorage.setItem('shd.subscriptionFolds',JSON.stringify([...foldedSubscriptions]));}catch{/* Session folding still works when storage is unavailable. */}}
function foldAllSubscriptions(fold){for(const sub of state.subscriptions){fold?foldedSubscriptions.add(sub.id):foldedSubscriptions.delete(sub.id);}saveSubscriptionFolds();renderSubscriptions();}
const subscriptionCoverImages=new Map(), subscriptionCoverTried=new Set();
let subscriptionCoverLoading=false;
async function loadSubscriptionCovers(){
 if(subscriptionCoverLoading||!backend)return;
 const ids=state.subscriptions.map(s=>s.id).filter(id=>!subscriptionCoverImages.has(id)&&!subscriptionCoverTried.has(id));
 if(!ids.length)return;ids.forEach(id=>subscriptionCoverTried.add(id));subscriptionCoverLoading=true;
 try{const images=await api('subscription_covers',{ids});for(const [id,uri] of Object.entries(images))subscriptionCoverImages.set(id,uri);renderSubscriptions();}
 catch(e){/* A missing cover must never block the subscription controls. */}
 finally{subscriptionCoverLoading=false;loadSubscriptionCovers();}
}
const subscriptionSelection=new Set();
let subscriptionBatchBusy=false;
function subscriptionResources(){return [...new Map(state.subscriptions.flatMap(s=>s.items.slice(0,8)).map(r=>[r.hash,r])).values()];}
function updateSubscriptionBatch(){
 const button=$('download-subscriptions');
 button.textContent=subscriptionBatchBusy?'发送中…':`迅雷下载所选 (${subscriptionSelection.size})`;
 button.disabled=subscriptionBatchBusy||!subscriptionSelection.size;
 $('select-subscriptions').disabled=subscriptionBatchBusy||!subscriptionResources().length;
 $('clear-subscriptions').disabled=subscriptionBatchBusy||!subscriptionSelection.size;
 $('subscriptions-list').querySelectorAll('[data-check]').forEach(c=>{c.checked=subscriptionSelection.has(c.dataset.check);c.disabled=subscriptionBatchBusy;});
}
async function downloadSubscriptions(){
 if(state.busy||subscriptionBatchBusy)return;
 const resources=subscriptionResources().filter(r=>subscriptionSelection.has(r.hash));
 if(!resources.length)return;
 state.busy=true;subscriptionBatchBusy=true;updateSubscriptionBatch();let sent=0,failed=0;
 try{for(const resource of resources){try{const result=await api('launch_thunder',{resource});state.history=result.history;subscriptionSelection.delete(resource.hash);sent++;}catch(e){failed++;}}renderHistory();
 toast(`已向迅雷发送 ${sent} 条${failed?`，${failed} 条失败，已保留勾选，可重试`:''}。请在迅雷中确认下载。`,failed>0);
 }finally{state.busy=false;subscriptionBatchBusy=false;updateSubscriptionBatch();}
}
function renderSubscriptions(){
 const available=new Set(subscriptionResources().map(r=>r.hash));for(const hash of subscriptionSelection)if(!available.has(hash))subscriptionSelection.delete(hash);

 $('subscriptions-list').innerHTML=state.subscriptions.map(s=>{const folded=foldedSubscriptions.has(s.id);return `<section class="subscription"><div class="subscription-summary"><div class="subscription-cover">${subscriptionCoverImages.has(s.id)?`<img src="${esc(subscriptionCoverImages.get(s.id))}" alt="${esc(s.query)}封面">`:'<span aria-hidden="true">◇</span>'}</div><div class="subscription-copy"><div class="row"><h3 class="subscription-heading"><button class="subscription-toggle" data-fold="${s.id}" aria-expanded="${!folded}" aria-controls="subitems-${s.id}"><span class="fold-chevron" aria-hidden="true">${folded?'›':'⌄'}</span><span>${esc(s.query)}</span><small>${folded?'展开':'收起'} · ${s.items.length} 条</small></button></h3><button data-unsub="${s.id}">取消追番</button></div><div class="metadata">${esc([s.group||'所有发布组',s.quality||'所有清晰度',s.subtitle||'所有字幕'].join(' · '))}<br>上次检查：${esc(s.checked||'尚未检查')} ${esc(s.error||'')}</div></div></div><div id="subitems-${s.id}" data-subitems="${s.id}" ${folded?'hidden':''}>${s.items.slice(0,8).map(r=>resourceCard(r,true)).join('')||'<p class="muted">检查更新后显示符合规则的资源。</p>'}</div></section>`;}).join('')||empty('你的追番列表还是空的','在搜索结果中订阅作品和发布版本。');
 for(const s of state.subscriptions)bindResources(document.querySelector(`[data-subitems="${s.id}"]`),s.items,s.query);
 $('subscriptions-list').querySelectorAll('[data-fold]').forEach(b=>b.onclick=()=>{const id=b.dataset.fold;foldedSubscriptions.has(id)?foldedSubscriptions.delete(id):foldedSubscriptions.add(id);saveSubscriptionFolds();renderSubscriptions();document.querySelector(`[data-fold="${id}"]`)?.focus({preventScroll:true});});
 $('subscriptions-list').querySelectorAll('[data-unsub]').forEach(b=>b.onclick=()=>attempt(async()=>{state.subscriptions=await api('unsubscribe',{id:b.dataset.unsub});foldedSubscriptions.delete(b.dataset.unsub);saveSubscriptionFolds();renderSubscriptions();}));
 $('subscriptions-list').querySelectorAll('[data-check]').forEach(c=>c.onchange=()=>{c.checked?subscriptionSelection.add(c.dataset.check):subscriptionSelection.delete(c.dataset.check);updateSubscriptionBatch();});updateSubscriptionBatch();
 $('collapse-subscriptions').disabled=!state.subscriptions.length;$('expand-subscriptions').disabled=!state.subscriptions.length;loadSubscriptionCovers();
}

async function checkSubscriptions(){$('check-subscriptions').disabled=true;$('check-subscriptions').textContent='检查中…';try{state.subscriptions=await api('check_subscriptions');subscriptionCoverTried.clear();renderSubscriptions();}finally{$('check-subscriptions').disabled=false;$('check-subscriptions').textContent='检查更新';}}
function settingsValue(){return {proxy_mode:$('proxy-mode').value,proxy_url:$('proxy-url').value.trim(),thunder_path:$('thunder-path').value.trim()};}
function proxyFields(){$('proxy-fields').hidden=$('proxy-mode').value!=='manual';}
function openSettings(){const s=state.settings;$('proxy-mode').value=s.proxy_mode||'system';$('proxy-url').value=s.proxy_url||'';$('thunder-path').value=s.thunder_path||'';$('settings-error').textContent='';$('proxy-test-status').textContent='';proxyFields();showDialog('settings-dialog');}
function updateProxyStatus(){$('proxy-status').textContent='资源站：'+({manual:'手动代理',system:'系统代理',direct:'直连'}[state.settings.proxy_mode]||'—');}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view));document.querySelectorAll('.close-dialog').forEach(b=>b.onclick=()=>b.closest('dialog').close());document.querySelectorAll('dialog').forEach(d=>d.addEventListener('click',e=>{if(e.target===d){const r=d.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)d.close();}}));$('search-form').onsubmit=e=>{e.preventDefault();attempt(()=>search())};$('filter-quality').onchange=renderResults;$('filter-subtitle').onchange=renderResults;$('previous-page').onclick=()=>attempt(()=>search(state.page-1));$('next-page').onclick=()=>attempt(()=>search(state.page+1));$('settings-button').onclick=openSettings;$('proxy-mode').onchange=proxyFields;$('detail-download').onclick=()=>attempt(()=>handoff(state.selected));$('new-subscription').onclick=()=>openSubscription();$('detail-subscribe').onclick=()=>openSubscription(state.selected);$('check-subscriptions').onclick=()=>attempt(checkSubscriptions);
$('settings-form').onsubmit=async e=>{e.preventDefault();$('save-settings').disabled=true;$('settings-error').textContent='';try{state.settings=await api('settings',settingsValue());updateProxyStatus();$('settings-dialog').close();toast('设置已保存，下载由迅雷管理。');}catch(e){$('settings-error').textContent=e.message;}finally{$('save-settings').disabled=false;}};
$('test-proxy').onclick=async()=>{$('test-proxy').disabled=true;$('proxy-test-status').textContent='连接中…';try{const r=await api('test_proxy',settingsValue());$('proxy-test-status').textContent=`连接成功 · ${r.milliseconds} ms`;}catch(e){$('proxy-test-status').textContent='连接失败';$('settings-error').textContent=e.message;}finally{$('test-proxy').disabled=false;}};
document.querySelectorAll('[data-browse]').forEach(b=>b.onclick=()=>attempt(async()=>{const p=await api('browse',{kind:b.dataset.browse});if(p)$('thunder-path').value=p;}));
$('subscribe-form').onsubmit=async e=>{e.preventDefault();try{state.subscriptions=await api('subscribe',{query:$('sub-query').value,group:$('sub-group').value.trim(),quality:$('sub-quality').value,subtitle:$('sub-subtitle').value});$('subscribe-dialog').close();setView('subscriptions');await checkSubscriptions();}catch(e){$('subscribe-error').textContent=e.message;}};
new QWebChannel(qt.webChannelTransport,channel=>{backend=channel.objects.backend;backend.result.connect((id,message)=>{const p=pending.get(id);if(!p)return;pending.delete(id);clearTimeout(p.timer);const result=JSON.parse(message);result.ok?p.resolve(result.data):p.reject(Error(result.error));});attempt(async()=>{const init=await api('bootstrap');state.settings=init.settings;state.history=init.history;state.subscriptions=init.subscriptions;updateProxyStatus();setView('calendar');});});

const calendarState={day:new Date().getDay()||7,data:null,loading:false,token:0};
const weekNames=['周一','周二','周三','周四','周五','周六','周日'];
function calendarRows(){return calendarState.data?.days.find(d=>d.weekday===calendarState.day)?.items||[];}
function drawCalendar(){
 const today=new Date().getDay()||7;

 $('calendar-days').innerHTML=weekNames.map((name,i)=>`<button data-day="${i+1}" aria-pressed="${calendarState.day===i+1}" class="${calendarState.day===i+1?'active':''}">${name}${today===i+1?' · 今天':''}</button>`).join('');
 $('calendar-days').querySelectorAll('[data-day]').forEach(b=>b.onclick=()=>{calendarState.day=Number(b.dataset.day);drawCalendar();loadCovers();});
 $('calendar-list').innerHTML=calendarRows().map(r=>`<article class="calendar-card"><div class="cover-placeholder"><span>SHD<br>ON AIR</span><img id="cover-${r.id}" hidden alt="${esc(r.title)}封面"></div><div class="calendar-info"><h3 title="${esc(r.title)}">${esc(r.title)}</h3>${r.name_label?`<span class="translation-badge" title="${esc(r.name_note||'暂未取得可靠中文译名')}">${esc(r.name_label)}</span>`:''}<p class="original">${esc(r.original===r.title?'':r.original)}</p><p class="metadata">首播 ${esc(r.air_date||'未标注')}</p><div class="actions"><button class="hot" data-calendar-search="${r.id}">${icon('search')}查看资源</button><button data-calendar-follow="${r.id}">${icon('plus')}追番</button></div></div></article>`).join('')||empty('当天暂无放送条目','可以切换其他星期，或直接搜索作品。');
 $('calendar-list').querySelectorAll('[data-calendar-search]').forEach(b=>b.onclick=()=>{const row=calendarRows().find(r=>r.id===Number(b.dataset.calendarSearch));$('search-query').value=row.search_title||row.title;$('filter-quality').value='';$('filter-subtitle').value='';setView('discover');attempt(()=>search());});
 $('calendar-list').querySelectorAll('[data-calendar-follow]').forEach(b=>b.onclick=()=>{const row=calendarRows().find(r=>r.id===Number(b.dataset.calendarFollow));openSubscription();$('sub-query').value=row.search_title||row.title;});
}
async function loadCalendar(force=false){
 if(calendarState.loading)return;calendarState.loading=true;$('refresh-calendar').disabled=true;$('calendar-status').textContent='正在获取放送表…';
 try{calendarState.data=await api('calendar',{force});const d=calendarState.data;$('calendar-status').textContent=`${d.notice||'放送表'} · 更新于 ${d.updated}${d.cached?' · 本地缓存':''}`;drawCalendar();loadCovers();}
 catch(e){$('calendar-status').textContent=e.message;if(!calendarState.data)$('calendar-list').innerHTML=empty('日历暂时不可用','可点击刷新重试，或者继续使用发现资源。');}
 finally{calendarState.loading=false;$('refresh-calendar').disabled=false;}
}
async function loadCovers(){const token=++calendarState.token;const day=calendarState.day;try{const [covers,titles]=await Promise.all([api('calendar_covers',{weekday:day}),api('calendar_titles',{weekday:day}).catch(()=>({}))]);if(token!==calendarState.token)return;const data=calendarState.data?.days.find(d=>d.weekday===day);if(data)data.items=data.items.map(r=>titles[String(r.id)]||r);drawCalendar();for(const [id,uri] of Object.entries(covers)){const img=$('cover-'+id);if(img){img.onload=()=>{img.hidden=false;img.previousElementSibling.hidden=true;};img.src=uri;}}}catch(e){/* Artwork is optional. */}}
$('refresh-calendar').onclick=()=>loadCalendar(true);
drawCalendar();

$('collapse-subscriptions').onclick=()=>foldAllSubscriptions(true);
$('expand-subscriptions').onclick=()=>foldAllSubscriptions(false);

$('select-subscriptions').onclick=()=>{subscriptionResources().forEach(r=>subscriptionSelection.add(r.hash));updateSubscriptionBatch();};
$('clear-subscriptions').onclick=()=>{subscriptionSelection.clear();updateSubscriptionBatch();};
$('download-subscriptions').onclick=()=>attempt(downloadSubscriptions);
