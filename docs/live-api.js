/* HDC Permit Review: remote API transport.
   Activated only when runtime-config.js specifies a reachable HTTPS backend.
   No API keys, passwords or shared secrets are hard-coded here. */
(() => {
  'use strict';
  const base = String(window.PERMIT_API_BASE || '').trim().replace(/\/+$/, '');
  const enabled = /^https:\/\/[^/]+/i.test(base) ||
                  (base === window.location.origin && /^http:\/\//i.test(base));
  // HTTP is accepted only when the frontend itself is served by that same
  // office-LAN server. Public GitHub Pages remains in preview mode.
  const TOKEN_KEY = 'hdc-permit-live-token-v1';
  let token = enabled ? (sessionStorage.getItem(TOKEN_KEY) || '') : '';
  let user = null;
  const path = p => base + p;
  async function request(endpoint, method = 'GET', value) {
    if (!enabled) throw Error('공용 저장 서버가 아직 연결되지 않았습니다.');
    const headers = {'Accept': 'application/json'};
    if (token) headers.Authorization = 'Bearer ' + token;
    if (value !== undefined) headers['Content-Type'] = 'application/json';
    let response;
    try {
      response = await fetch(path(endpoint), {
        method, headers, mode:'cors', cache:'no-store',
        body: value === undefined ? undefined : JSON.stringify(value)
      });
    } catch {
      throw Error('공용 저장 서버에 접속할 수 없습니다. 서버 주소와 연결 상태를 확인하세요.');
    }
    let data;
    try {data = await response.json()} catch {data = {error:'서버 응답을 읽을 수 없습니다.'}}
    if (!response.ok) {
      if (response.status === 401 && endpoint !== '/api/login') {
        token = '';user=null;sessionStorage.removeItem(TOKEN_KEY);
      }
      throw Error(data.error || '요청이 실패했습니다 (' + response.status + ')');
    }
    return data;
  }
  async function login(email, password) {
    const data = await request('/api/login','POST',{email,password});
    if (!data.token || !data.user) throw Error('로그인 응답이 올바르지 않습니다.');
    token = data.token;user = data.user;sessionStorage.setItem(TOKEN_KEY,token);
    return user;
  }
  async function signup(email,password){
    return request('/api/signup','POST',{email,password});
  }
  async function restore() {
    if (!token) return null;
    try {
      const data=await request('/api/me');
      user=data.user;return user;
    } catch {
      return null;
    }
  }
  async function logout() {
    try {if(token)await request('/api/logout','POST',{})} catch {}
    token='';user=null;sessionStorage.removeItem(TOKEN_KEY);
  }
  async function load() {
    return (await request('/api/tickets')).tickets;
  }
  async function create(fields) {
    return (await request('/api/tickets','POST',fields)).ticket;
  }
  async function fileToBase64(file) {
    if (file.size > 8*1024*1024) throw Error(file.name+' 파일은 8MB를 초과합니다.');
    const bytes = new Uint8Array(await file.arrayBuffer());
    const step = 0x7000;
    let encoded = '';
    for(let i=0;i<bytes.length;i+=step){
      encoded+=String.fromCharCode(...bytes.slice(i,i+step));
    }
    return btoa(encoded);
  }
  async function upload(ticketId,file) {
    const data=await fileToBase64(file);
    return (await request('/api/tickets/'+encodeURIComponent(ticketId)+'/attachments','POST',
                          {name:file.name,data})).ticket;
  }
  async function download(ticket,index) {
    const info=ticket.attachments?.[index];
    if(!info)throw Error('첨부파일 정보가 없습니다.');
    const endpoint='/api/tickets/'+encodeURIComponent(ticket.id)+'/attachments/'+info.id;
    const response=await fetch(path(endpoint), {
      headers:{Authorization:'Bearer '+token},mode:'cors',cache:'no-store'
    });
    if(!response.ok)throw Error('첨부파일을 불러오지 못했습니다.');
    const blob=await response.blob();
    return new File([blob], info.name, {type:blob.type||'application/octet-stream'});
  }
  async function review(ticketId,body){
    return (await request('/api/tickets/'+encodeURIComponent(ticketId)+'/review','POST',body)).ticket;
  }
  async function addUser(email,password,role){
    return request('/api/users','POST',{email,password,role});
  }
  window.PERMIT_LIVE = {enabled,login,signup,restore,logout,load,create,upload,download,review,addUser,
    get user(){return user},
    get connected(){return !!user}
  };
})();
