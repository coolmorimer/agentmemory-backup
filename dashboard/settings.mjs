import { readFileSync, writeFileSync, renameSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
const token = randomBytes(32).toString('hex');
const envPath = join(homedir(), '.agentmemory', '.env');
const readEnv = p => { try { return readFileSync(p, 'utf8'); } catch { return ''; } };
export function configured(p = envPath) { return /^OPENROUTER_API_KEY=\S+/m.test(readEnv(p)); }
export function saveConfig(key, p = envPath) {
  const values = { OPENROUTER_API_KEY: key, OPENROUTER_MODEL: 'openrouter/free', GRAPH_EXTRACTION_ENABLED: 'true', AGENTMEMORY_AUTO_COMPRESS: 'false', CONSOLIDATION_ENABLED: 'false', AGENTMEMORY_ALLOW_AGENT_SDK: 'false' };
  const lines = readEnv(p).split(/\r?\n/).filter(line => !Object.hasOwn(values, line.split('=')[0].trim()));
  const tmp = p + '.new';
  writeFileSync(tmp, lines.join('\n').trimEnd() + '\n' + Object.entries(values).map(([k,v]) => k+'='+v).join('\n')+'\n', {mode:0o600});
  renameSync(tmp,p);
}
export function injectSettings(html, nonce) {
  const fragment = `<details id="or-settings" style="margin:12px;padding:16px;border:1px solid #45484e;background:#17191c;color:#eee;font:14px system-ui"><summary style="cursor:pointer;font-weight:600">Настройки OpenRouter · только бесплатно</summary><div style="max-width:720px;padding-top:14px"><p>Подключите модель для сводок и графа связей. Записи будут обрабатываться через OpenRouter.</p><p>Модель: <strong>openrouter/free</strong>. Платные модели не используются. Возможны ограничения бесплатных запросов.</p><label for="or-key">Ключ OpenRouter</label><input id="or-key" type="password" autocomplete="new-password" placeholder="sk-or-v1-…" style="display:block;box-sizing:border-box;width:100%;padding:10px;margin:8px 0;background:#101114;color:#fff;border:1px solid #666"><button id="or-save" type="button" style="padding:10px 16px;cursor:pointer">Проверить и сохранить</button> <a href="https://openrouter.ai/settings/keys" target="_blank" rel="noopener noreferrer">Получить ключ</a><p id="or-status" role="status" aria-live="polite">Загрузка настроек…</p><p style="color:#aaa">Ключ хранится только на этом компьютере. После сохранения сервис перезапустится. Граф будет наполняться из новых записей.</p></div></details><script nonce="${nonce}">
(() => {
 const field=document.getElementById('or-key'), button=document.getElementById('or-save'), status=document.getElementById('or-status');
 fetch('/local-settings/openrouter').then(r=>r.json()).then(d=>{status.textContent=d.configured?'Ключ уже сохранён. Можно заменить его новым.':'Ключ пока не добавлен.';if(!d.configured)document.getElementById('or-settings').open=true;}).catch(()=>status.textContent='Не удалось прочитать настройки. Обновите страницу.');
 button.addEventListener('click',async()=>{button.disabled=true;status.textContent='Проверяем ключ…';try{const r=await fetch('/local-settings/openrouter',{method:'POST',headers:{'Content-Type':'application/json','X-Settings-Token':'${token}'},body:JSON.stringify({key:field.value})});const d=await r.json();if(!r.ok)throw Error(d.error);field.value='';status.textContent='Ключ сохранён. Перезапускаем сервис…';let tries=0;const timer=setInterval(async()=>{try{const r=await fetch('/agentmemory/config/flags');const d=await r.json();if(d.provider==='openrouter'){clearInterval(timer);location.reload();}}catch{}if(++tries>=30){clearInterval(timer);status.textContent='Ключ сохранён, но сервис ещё не ответил. Обновите страницу.';button.disabled=false;}},2000);}catch(e){status.textContent=e.message||'Не удалось сохранить настройки.';button.disabled=false;}});
})();</script>`;
  return html.replace(/(<body[^>]*>)/i, '$1'+fragment);
}
let saving=false;
export async function settingsRoute(req,res,options={}) {
 if(req.url!=='/local-settings/openrouter')return false;
 const send=(code,body)=>{res.writeHead(code,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(body));};
 if(req.method==='GET'){send(200,{configured:configured(options.path),model:'openrouter/free'});return true;}
 if(req.method!=='POST'){send(405,{error:'Метод не поддерживается.'});return true;}
 if(req.headers.origin!==`http://${req.headers.host}` || req.headers['x-settings-token']!==token){send(403,{error:'Обновите страницу настроек.'});return true;}
 if(saving){send(409,{error:'Сохранение уже выполняется.'});return true;}
 saving=true;
 try{
  let body='';for await(const chunk of req){body+=chunk;if(body.length>4096)throw Error('Слишком длинный ключ.');}
  let data;try{data=JSON.parse(body);}catch{throw Error('Неверный формат запроса.');}
  const key=typeof data.key==='string'?data.key.trim():'';
  if(!/^sk-or-v1-[a-zA-Z0-9_-]{20,200}$/.test(key))throw Error('Введите действительный ключ OpenRouter (sk-or-v1-…).');
  let response;try{response=await (options.fetch||fetch)('https://openrouter.ai/api/v1/key',{headers:{Authorization:'Bearer '+key},signal:AbortSignal.timeout(15000)});}catch{throw Error('OpenRouter не отвечает. Попробуйте ещё раз.');}
  if(!response.ok)throw Error(response.status===401?'OpenRouter отклонил ключ. Проверьте его.':'Не удалось проверить ключ в OpenRouter. Попробуйте позже.');
  saveConfig(key,options.path);send(200,{saved:true,model:'openrouter/free'});
  if(options.restart)options.restart();else {
   const child=spawn('powershell.exe',['-NoProfile','-ExecutionPolicy','Bypass','-File',join(homedir(),'.agentmemory','dashboard','restart.ps1')],{detached:true,stdio:'ignore',windowsHide:true});child.unref();
  }
 }catch(e){send(400,{error:e.message?.startsWith('OpenRouter')||/^(Введите|Неверный|Не удалось|Слишком)/.test(e.message)?e.message:'Не удалось сохранить настройки на диске.'});}finally{saving=false;}
 return true;
}
