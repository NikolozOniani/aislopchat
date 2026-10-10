const $ = (id) => document.getElementById(id);
const ICONS = {
  search:'<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
  globe:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/>',
  hash:'<path d="M5 9h14M4 15h14M11 3 7 21M17 3l-4 18"/>',
  send:'<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
  edit:'<path d="M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L8 18l-4 1 1-4Z"/>',
  close:'<path d="M18 6 6 18M6 6l12 12"/>',
  menu:'<path d="M4 7h16M4 12h16M4 17h16"/>',
  smile:'<circle cx="12" cy="12" r="9"/><path d="M8 14s1.5 3 4 3 4-3 4-3"/><path d="M9 9h.01M15 9h.01" stroke-width="2.8"/>',
  chat:'<path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5c-1.3 0-2.5-.3-3.5-.8L4 20l1.8-4.8A7.5 7.5 0 1 1 20 11.5Z"/><path d="M9 11h7M9 14h4"/>',
  shield:'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
  arrow:'<path d="M5 12h14m-7-7 7 7-7 7"/>',
  sparkles:'<path d="m12 3 1.9 5.9L20 11l-6.1 2.1L12 19l-1.9-5.9L4 11l6.1-2.1L12 3ZM20 19l1 2M3 20l1 2"/>',
  users:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
};
function icon(name,size=20) { return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`; }
const palette = [
 ['#143e74','#397dd0','#b9dbff'],['#23566b','#2ca4b6','#d5fdff'],
 ['#47356c','#8d6cdb','#f0dfff'],['#234b65','#3189c7','#d3ecff'],
 ['#365275','#4c85c8','#e0efff'],['#51416d','#ac7ee4','#f2dfff'],
 ['#255359','#26969e','#d3fffa'],['#35416d','#667de3','#ebedff']
];
function avatar(name, size='sm', online=null) {
 const el=document.createElement('div'); el.className=`avatar ${size}`;
 let hash=0;for(const c of name.toLowerCase())hash=(hash*31+c.charCodeAt(0))>>>0;
 const [a,b,c]=palette[hash%palette.length]; el.style.background=`linear-gradient(145deg,${a},${b})`;el.style.color=c;
 el.textContent=name.slice(0,2).toUpperCase();
 if(online!==null){const dot=document.createElement('span');dot.className='presence-dot'+(online?' on':'');el.append(dot)}
 return el;
}
function node(tag,cls,text){const e=document.createElement(tag); if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}
function fmtTime(ms){return new Intl.DateTimeFormat(undefined,{hour:'numeric',minute:'2-digit'}).format(new Date(ms))}
function fmtShort(ms){const d=new Date(ms),today=new Date();if(d.toDateString()===today.toDateString())return fmtTime(ms);return new Intl.DateTimeFormat(undefined,{month:'short',day:'numeric'}).format(d)}
function dayLabel(ms){const d=new Date(ms),today=new Date(),yesterday=new Date();yesterday.setDate(today.getDate()-1);if(d.toDateString()===today.toDateString())return 'TODAY';if(d.toDateString()===yesterday.toDateString())return 'YESTERDAY';return new Intl.DateTimeFormat(undefined,{weekday:'long',month:'short',day:'numeric'}).format(d).toUpperCase()}
function sameDay(a,b){return new Date(a).toDateString()===new Date(b).toDateString()}
const state={me:null,active:{kind:'global',id:null,name:'Global Chat'},messages:[],hasOlder:false,users:[],conversations:[],online:new Set(),ws:null,retry:0,seq:0,searchTimer:null,sendBusy:false,typing:new Map(),typingTimer:null,globalUnread:false,sidebarOpen:false};
const errors={401:'Your session has ended. Refresh to choose a new name.'};
async function api(path,opts={}){
 let resp;
 try{resp=await fetch(path,{credentials:'same-origin',...opts,headers:{...(opts.body?{'Content-Type':'application/json'}:{}),...(opts.headers||{})}})}catch{throw Error('Network unavailable. Check your connection.')}
 if(!resp.ok){let message=errors[resp.status]||`Request failed (${resp.status})`;try{const body=await resp.json();if(typeof body.detail==='string')message=body.detail}catch{}throw Error(message)}
 return resp.json();
}
function notify(message,isError=false){const toast=node('div','toast'+(isError?' error':''),message);$('toast-stack').append(toast);setTimeout(()=>toast.remove(),4500)}
function showModal(id,show){$(id).classList.toggle('hidden',!show)}
function setStatus(on){const e=$('connection-status');e.classList.toggle('connected',on);e.querySelector('label').textContent=on?'Live connection':'Reconnecting'}
function setUser(){const area=$('my-avatar');area.replaceChildren(avatar(state.me.username,'md',true));$('my-name').textContent='@'+state.me.username}
function setSidebar(open){state.sidebarOpen=open;$('sidebar').classList.toggle('open',open);$('sidebar-backdrop').classList.toggle('open',open)}
function switchGlobal(){switchRoom({kind:'global',id:null,name:'Global Chat'})}
function switchDM(person){switchRoom({kind:'dm',id:person.id,name:person.username})}
function itemPerson(person,conversation=false){
 const b=node('button','person-item'+(state.active.kind==='dm'&&state.active.id===person.id?' active':''));
 b.type='button';b.append(avatar(person.username,'sm',!!state.online.has(person.id)));
 const meta=node('span','person-meta');meta.append(node('span','person-name',person.username));
 meta.append(node('span','person-preview',conversation?(person.last_sender_id===state.me.id?'You: ':'')+(person.last_body||'Start a conversation'):(state.online.has(person.id)?'Online now':'Say hello')));
 b.append(meta);
 if(conversation){const right=node('span','person-right');right.append(node('span','person-time',fmtShort(person.last_at)));if(person.unread){right.append(node('span','unread-badge',person.unread>99?'99+':String(person.unread)))}b.append(right)}
 b.addEventListener('click',()=>switchDM(person));return b;
}
function renderSidebar(){
 $('global-button').classList.toggle('active',state.active.kind==='global');
 $('global-dot').classList.toggle('visible',state.globalUnread&&state.active.kind!=='global');
 const conv=$('conversations');conv.replaceChildren();$('dm-count').textContent=state.conversations.length;
 if(!state.conversations.length){conv.append(node('div','empty-sidebar','Your private chats will show up here.'))}
 else for(const c of state.conversations)conv.append(itemPerson(c,true));
 const people=$('people-list');people.replaceChildren();
 const filtered=state.users.filter(u=>!state.conversations.some(c=>c.id===u.id));
 const all=filtered.slice(0,$('user-search').value?40:12);
 $('people-empty').classList.toggle('hidden',!!all.length);
 if(!all.length)$('people-empty').textContent=$('user-search').value?'No people match your search.':'New people will appear here.';
 for(const p of all)people.append(itemPerson(p));
}
function renderOnline(){
 const ids=state.online;const total=ids.size;
 $('online-count').textContent=total;$('side-online-count').textContent=total;
 const shown=[];
 if(state.me&&ids.has(state.me.id))shown.push({id:state.me.id,username:state.me.username,self:true});
 for(const u of state.users)if(ids.has(u.id)&&shown.length<15)shown.push(u);
 for(const u of state.conversations)if(ids.has(u.id)&&!shown.some(x=>x.id===u.id)&&shown.length<15)shown.push(u);
 const stack=node('span','online-avatar-stack');for(const u of shown.slice(0,3))stack.append(avatar(u.username,'sm'));
 $('online-avatars').replaceChildren(stack);
 const list=$('online-list');list.replaceChildren();
 if(!shown.length){list.append(node('p','online-none','Nobody online yet. Be the first to say hello.'));return}
 for(const p of shown.slice(0,7)){const b=node('button','online-person');b.append(avatar(p.username,'sm',true));const info=node('span');info.append(node('strong','',p.username+(p.self?' (you)':'')),node('small','',p.self?'That’s you':'Available to chat'));b.append(info);if(p.self)b.disabled=true;else b.addEventListener('click',()=>switchDM(p));list.append(b)}
}
function updateHeader(){
 const isGlobal=state.active.kind==='global';$('channel-icon').innerHTML=icon(isGlobal?'hash':'chat',23);
 $('channel-title').textContent=isGlobal?'Global Chat':state.active.name;
 $('channel-subtitle').textContent=isGlobal?'The main room · Everyone is welcome':state.online.has(state.active.id)?'Online now · Direct message':'Direct message · Messages stay here';
 $('message-input').placeholder=isGlobal?'Message #global-chat':'Message @'+state.active.name;
 $('info-title').textContent=isGlobal?'One room. Endless conversations.':'A space for two.';
 $('info-description').textContent=isGlobal?"Meet new people, share ideas, and see where the conversation goes. The world's a little smaller here.":`This is your direct conversation with ${state.active.name}. Only the two of you can see these messages from your sessions.`;
 renderSidebar();
}
function renderMessages(){
 const root=$('messages');root.replaceChildren();
 if(state.hasOlder){const older=node('button','load-older','↑  Load earlier messages');older.addEventListener('click',loadOlder);root.append(older)}
 if(!state.messages.length){const empty=node('div','empty-state');empty.innerHTML=`<div class="empty-visual">${icon(state.active.kind==='global'?'globe':'chat',48)}</div><div class="empty-chip">${state.active.kind==='global'?'THE GLOBAL ROOM':'DIRECT MESSAGE'}</div>`;empty.append(node('h2','',state.active.kind==='global'?'Start a conversation.':'Say the first hello.'));empty.append(node('p','',state.active.kind==='global'?'Every great conversation starts somewhere. Your message could be the one that gets things going.':`Send ${state.active.name} a message to start chatting. Just the two of you, right here.`));root.append(empty);return}
 let prev=null;
 for(const m of state.messages){
  if(!prev||!sameDay(prev.created_at,m.created_at))root.append(node('div','day-divider',dayLabel(m.created_at)));
  const mine=m.sender_id===state.me.id;
  const grouped=!!(prev&&prev.sender_id===m.sender_id&&sameDay(prev.created_at,m.created_at)&&m.created_at-prev.created_at<5*60*1000);
  const row=node('div','message-row'+(mine?' mine':'')+(grouped?' grouped':''));
  if(mine){row.append(node('div','message-avatar-placeholder'))}
  else if(grouped)row.append(node('div','message-avatar-placeholder'));
  else {const wrap=node('div','message-avatar');wrap.append(avatar(m.sender_name,'sm'));row.append(wrap)}
  const content=node('div','message-content');
  if(!grouped){const meta=node('div','message-meta');meta.append(node('strong','',mine?'You':m.sender_name));const t=node('time','',fmtTime(m.created_at));t.dateTime=new Date(m.created_at).toISOString();meta.append(t);content.append(meta)}
  content.append(node('div','message-bubble',m.body));row.append(content);root.append(row);prev=m;
 }
}
function scrollBottom(){const s=$('chat-scroll');requestAnimationFrame(()=>s.scrollTop=s.scrollHeight)}
async function switchRoom(room){
 state.active=room;state.messages=[];state.hasOlder=false;state.typing.clear();updateTyping();updateHeader();renderMessages();setSidebar(false);
 if(room.kind==='global')state.globalUnread=false;
 const seq=++state.seq;
 try{
  const url=room.kind==='global'?'/api/messages/global':`/api/messages/dm/${encodeURIComponent(room.id)}`;
  const messages=await api(url);
  if(seq!==state.seq)return;
  state.messages=messages;state.hasOlder=messages.length===60;renderMessages();scrollBottom();
  if(room.kind==='dm'){await api(`/api/messages/dm/${encodeURIComponent(room.id)}/read`,{method:'POST'});await refreshConversations()}
 }catch(e){if(seq===state.seq)notify(e.message,true)}
}
async function loadOlder(){
 if(!state.hasOlder||!state.messages.length)return;
 const before=state.messages[0].id;const seq=state.seq;const a=state.active;
 const path=a.kind==='global'?'/api/messages/global':`/api/messages/dm/${encodeURIComponent(a.id)}`;
 const s=$('chat-scroll');const beforeHeight=s.scrollHeight;
 try{const older=await api(`${path}?before=${before}`);if(seq!==state.seq)return;state.messages=[...older,...state.messages];state.hasOlder=older.length===60;renderMessages();requestAnimationFrame(()=>s.scrollTop=s.scrollHeight-beforeHeight+s.scrollTop)}catch(e){notify(e.message,true)}
}
async function refreshConversations(){if(!state.me)return;try{state.conversations=await api('/api/conversations');renderSidebar();renderOnline()}catch{}}
async function refreshUsers(){if(!state.me)return;try{state.users=await api('/api/users?query='+encodeURIComponent($('user-search').value.trim()));renderSidebar();renderOnline()}catch{}}
function updateTyping(){const key=state.active.kind==='global'?'global':`dm:${state.active.id}`;const names=[...(state.typing.get(key)||new Map()).values()].filter(x=>x.expires>Date.now()).map(x=>x.name);const e=$('typing-indicator');e.replaceChildren();if(!names.length)return;e.append(node('span','',names.length===1?`${names[0]} is typing`:`${names.slice(0,2).join(' and ')} are typing`));const dots=node('span','typing-dots');for(let i=0;i<3;i++)dots.append(node('i'));e.append(dots)}
function recordTyping(packet){const key=packet.kind==='global'?'global':`dm:${packet.peer_id}`;if(!state.typing.has(key))state.typing.set(key,new Map());state.typing.get(key).set(packet.user_id,{name:packet.username,expires:Date.now()+2100});updateTyping()}
function currentRoomMatches(m){return m.kind===state.active.kind&&(m.kind==='global'||m.sender_id===state.active.id||m.recipient_id===state.active.id)}
async function receiveMessage(m){
 if(currentRoomMatches(m)){
  if(!state.messages.some(x=>x.id===m.id)){
   const s=$('chat-scroll');const nearBottom=s.scrollHeight-s.scrollTop-s.clientHeight<160;
   state.messages.push(m);state.messages.sort((a,b)=>a.id-b.id);renderMessages();if(nearBottom||m.sender_id===state.me.id)scrollBottom();
  }
  if(m.kind==='dm'&&m.sender_id!==state.me.id){api(`/api/messages/dm/${encodeURIComponent(state.active.id)}/read`,{method:'POST'}).then(refreshConversations).catch(()=>{})}
 }else if(m.kind==='global'&&m.sender_id!==state.me.id){state.globalUnread=true;renderSidebar()}
 else if(m.kind==='dm'&&m.sender_id!==state.me.id)notify(`New message from ${m.sender_name}`);
 if(m.kind==='dm')refreshConversations();
}
function connectWS(){
 if(!state.me)return;
 if(state.ws&&[WebSocket.OPEN,WebSocket.CONNECTING].includes(state.ws.readyState))return;
 const protocol=location.protocol==='https:'?'wss:':'ws:';const ws=new WebSocket(`${protocol}//${location.host}/ws`);state.ws=ws;
 ws.addEventListener('open',()=>{state.retry=0;setStatus(true)});
 ws.addEventListener('message',event=>{
  let p;try{p=JSON.parse(event.data)}catch{return}
  if(p.type==='hello'){state.online=new Set(p.online_ids);renderSidebar();renderOnline();updateHeader()}
  else if(p.type==='presence'){p.online?state.online.add(p.user_id):state.online.delete(p.user_id);if(p.online&&p.username&&p.user_id!==state.me.id&&!state.users.some(u=>u.id===p.user_id))state.users.push({id:p.user_id,username:p.username,online:true});renderSidebar();renderOnline();updateHeader()}
  else if(p.type==='message:new'){receiveMessage(p.message)}
  else if(p.type==='typing'&&p.user_id!==state.me.id)recordTyping(p);
  else if(p.type==='user:renamed'){
   if(p.user_id===state.me.id){state.me.username=p.username;setUser()}
   for(const p2 of state.users)if(p2.id===p.user_id)p2.username=p.username;
   for(const c of state.conversations)if(c.id===p.user_id)c.username=p.username;
   for(const m of state.messages)if(m.sender_id===p.user_id)m.sender_name=p.username;
   if(state.active.id===p.user_id)state.active.name=p.username;
   renderMessages();updateHeader();renderOnline();
  }
 });
 ws.addEventListener('close',()=>{if(state.ws!==ws)return;setStatus(false);state.online.clear();renderOnline();renderSidebar();const delay=Math.min(15000,1000*2**Math.min(state.retry++,4));setTimeout(()=>{if(state.ws===ws)connectWS()},delay)});
 ws.addEventListener('error',()=>{ws.close()});
}
let lastTyped=0;
function sendTyping(){const t=Date.now();if(t-lastTyped<1150||!state.ws||state.ws.readyState!==WebSocket.OPEN)return;lastTyped=t;state.ws.send(JSON.stringify({type:'typing',kind:state.active.kind,peer_id:state.active.id}))}
async function sendMessage(event){
 event.preventDefault();const input=$('message-input');const text=input.value.trim();if(!text||state.sendBusy||!state.me)return;
 const room={...state.active};state.sendBusy=true;$('send-button').disabled=true;
 try{const m=await api('/api/messages',{method:'POST',body:JSON.stringify({kind:room.kind,recipient_id:room.id,body:text})});
  if(input.value.trim()===text)input.value='';resizeInput();
  if(currentRoomMatches(m)&&!state.messages.some(x=>x.id===m.id)){state.messages.push(m);renderMessages();scrollBottom()}
  if(room.kind==='dm')refreshConversations();
 }catch(e){notify(e.message,true)}finally{state.sendBusy=false;$('send-button').disabled=false;input.focus()}
}
function resizeInput(){const input=$('message-input');input.style.height='auto';input.style.height=Math.min(input.scrollHeight,140)+'px';$('character-count').textContent=input.value.length>1250?`${input.value.length}/1500`:''}
async function enterApp(user){state.me=user;setUser();showModal('welcome-modal',false);connectWS();await Promise.all([refreshUsers(),refreshConversations()]);switchGlobal()}
function wire(){
 $('search-icon').innerHTML=icon('search',16);$('global-icon').innerHTML=icon('globe',19);$('edit-name').innerHTML=icon('edit',15);$('emoji-trigger').innerHTML=icon('smile',21);$('send-button').innerHTML=icon('send',19);$('rules-icon').innerHTML=icon('shield',18);$('lock-icon').innerHTML=icon('lock',13);$('open-sidebar').innerHTML=icon('menu',22);$('close-sidebar').innerHTML=icon('close',20);$('rename-close').innerHTML=icon('close',18);
 $('global-button').addEventListener('click',switchGlobal);
 $('open-sidebar').addEventListener('click',()=>setSidebar(true));$('close-sidebar').addEventListener('click',()=>setSidebar(false));$('sidebar-backdrop').addEventListener('click',()=>setSidebar(false));
 $('show-members').addEventListener('click',()=>{setSidebar(true);$('user-search').focus()});
 $('user-search').addEventListener('input',()=>{clearTimeout(state.searchTimer);state.searchTimer=setTimeout(refreshUsers,210)});
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){showModal('rename-modal',false);$('emoji-picker').classList.add('hidden');setSidebar(false)}if(e.key==='/'&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)&&$('welcome-modal').classList.contains('hidden')){e.preventDefault();setSidebar(true);$('user-search').focus()}});
 $('message-form').addEventListener('submit',sendMessage);
 $('message-input').addEventListener('input',()=>{resizeInput();sendTyping()});
 $('message-input').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('message-form').requestSubmit()}});
 const emojis=['😀','😂','🔥','💙','❤️','👏','👋','✨','🎉','🤔','💯','🙌','😎','🥳','🚀','🌊','👍','☕'];
 for(const em of emojis){const b=node('button','',em);b.type='button';b.addEventListener('click',()=>{const i=$('message-input');i.value+=em;resizeInput();i.focus();$('emoji-picker').classList.add('hidden')});$('emoji-picker').append(b)}
 $('emoji-trigger').addEventListener('click',()=>$('emoji-picker').classList.toggle('hidden'));
 document.addEventListener('click',e=>{if(!e.target.closest('.emoji-picker')&&!e.target.closest('#emoji-trigger'))$('emoji-picker').classList.add('hidden')});
 $('join-form').addEventListener('submit',async e=>{e.preventDefault();const submit=$('join-submit');submit.disabled=true;$('join-error').textContent='';try{const user=await api('/api/join',{method:'POST',body:JSON.stringify({username:$('join-username').value})});await enterApp(user)}catch(err){$('join-error').textContent=err.message}finally{submit.disabled=false}});
 $('edit-name').addEventListener('click',()=>{$('rename-input').value=state.me.username;$('rename-error').textContent='';showModal('rename-modal',true);$('rename-input').focus()});
 $('rename-close').addEventListener('click',()=>showModal('rename-modal',false));
 $('rename-form').addEventListener('submit',async e=>{e.preventDefault();$('rename-error').textContent='';try{const user=await api('/api/me',{method:'PATCH',body:JSON.stringify({username:$('rename-input').value})});state.me=user;setUser();showModal('rename-modal',false);notify('Username updated.')}catch(err){$('rename-error').textContent=err.message}});
 setInterval(updateTyping,800);
}
async function start(){wire();try{const user=await api('/api/me');await enterApp(user)}catch(e){if(e.message.includes('Choose a username')){showModal('welcome-modal',true);$('join-username').focus()}else{showModal('welcome-modal',true);$('join-error').textContent='Could not reach the server. Refresh to retry.'}}}
start();
