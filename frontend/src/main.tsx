import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Activity, ArrowUpRight, Bell, Check, ChevronRight, Cpu, Download, Eye, Gauge, Lightbulb, LogOut, Radio, Shield, Thermometer, Video, Volume2, Wifi, Wind } from './icons';
import type { Alert, Command, Measurement, Status } from './types';
import './style.css';

const labels:Record<string,string> = {normal:'Normal',warning:'Dégradé',critical:'Alerte critique',offline:'Hors ligne',initializing:'Initialisation',unavailable:'Indisponible',pending:'En attente',executed:'Exécutée',rejected:'Refusée',timeout:'Sans confirmation'};
const clock = (date:string) => new Date(date).toLocaleTimeString('fr-FR');

function App(){
  const [csrf,setCsrf] = useState('');
  const [sessionChecked,setSessionChecked] = useState(false);
  const [password,setPassword] = useState('');
  const [status,setStatus] = useState<Status|null>(null);
  const [measurements,setMeasurements] = useState<Measurement[]>([]);
  const [alerts,setAlerts] = useState<Alert[]>([]);
  const [commands,setCommands] = useState<Command[]>([]);
  const [connected,setConnected] = useState(false);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const [notice,setNotice] = useState('');
  const [tab,setTab] = useState('overview');
  const [device,setDevice] = useState('sentinel-x-01');
  const [alertPage,setAlertPage] = useState(0);
  const [historyPage,setHistoryPage] = useState(0);
  const [history,setHistory] = useState<Measurement[]>([]);
  const [videoError,setVideoError] = useState(false);
  const heartbeat = useRef(0);
  const activeAlertPage = useRef(0);
  activeAlertPage.current = tab==='alerts'?alertPage:0;
  const api = useCallback(async (path:string, body?:unknown) => {
    const res = await fetch('/api/v1/'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)});
    if(res.status===401 && path!=='login'){setCsrf('');setConnected(false);}
    const data = await res.json();
    if(!res.ok) throw new Error(typeof data.detail==='string'?data.detail:'Requête invalide');
    return data;
  },[csrf]);
  useEffect(()=>{fetch('/api/v1/session').then(async r=>{if(r.ok)setCsrf((await r.json()).csrf_token);}).finally(()=>setSessionChecked(true));},[]);
  const reload = useCallback(async()=>{
    const [s,m,a,c] = await Promise.all([api('status'),api('measurements?seconds=60&limit=500'),api(`alerts?limit=50&offset=${activeAlertPage.current*50}`),api('commands')]);
    setStatus(s);setMeasurements(m.items.reverse());setAlerts(a.items);setCommands(c.items);
  },[api]);
  useEffect(()=>{
    if(!csrf)return;
    let socket:WebSocket|undefined;let timer:number;let stopped=false;
    const open = ()=>{
      socket = new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/v1/ws`);
      socket.onopen=()=>{heartbeat.current=Date.now();reload().catch(e=>setError(e.message));};
      socket.onmessage=e=>{
        const message=JSON.parse(e.data);if(message.type!=='snapshot')return;
        const s:Status=message.data;setStatus(s);setConnected(true);heartbeat.current=Date.now();
        setCommands(s.recent_commands);
        setMeasurements(old=>{
          const next=[...old];
          for(const d of Object.values(s.devices)){
            const row=d.latest;
            if(!next.some(m=>m.device_id===row.device_id&&m.boot_id===row.boot_id&&m.sequence===row.sequence))next.push(row);
          }
          return next.filter(m=>Date.parse(s.server_time)-Date.parse(m.received_at)<=60000).slice(-500);
        });
      };
      socket.onclose=()=>{setConnected(false);if(!stopped)timer=window.setTimeout(open,2000);};
    };
    open();
    const watchdog=window.setInterval(()=>{if(Date.now()-heartbeat.current>5000){setConnected(false);socket?.close();}},1000);
    const refresh=window.setInterval(()=>{Promise.all([api(`alerts?limit=50&offset=${activeAlertPage.current*50}`),api('commands')]).then(([a,c])=>{setAlerts(a.items);setCommands(c.items);}).catch(()=>{});},3000);
    return ()=>{stopped=true;clearTimeout(timer);clearInterval(watchdog);clearInterval(refresh);socket?.close();setConnected(false);};
  },[csrf,reload,api]);
  useEffect(()=>{setVideoError(false);},[status?.vision.online,status?.vision.camera,status?.vision.model,status?.vision.stream_id]);
  useEffect(()=>{if(csrf&&tab==='history')api(`measurements?seconds=604800&limit=50&offset=${historyPage*50}&device_id=${device}`).then(d=>setHistory(d.items)).catch(e=>setError(e.message));},[csrf,tab,historyPage,device,api]);
  useEffect(()=>{if(csrf&&tab==='alerts')api(`alerts?limit=50&offset=${alertPage*50}`).then(d=>setAlerts(d.items)).catch(e=>setError(e.message));},[csrf,tab,alertPage,api]);
  async function action(path:string,body:unknown){setBusy(true);setError('');setNotice('');try{const result=await api(path,body);if(path==='model/retrain')setNotice(`Modèle réentraîné sur ${result.samples} mesures physiques (${clock(result.trained_at)}).`);await reload();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function login(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');try{const d=await api('login',{username:'operateur',password});setCsrf(d.csrf_token);setPassword('');}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function logout(){setBusy(true);try{await api('logout',{});setCsrf('');setStatus(null);setError('');}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  const current=status?.devices[device];const latest=current?.latest;
  const usable=connected&&status?.database&&current?.online;
  const live=Boolean(connected&&current?.online);
  const decision=live?latest?.anomaly:undefined;
  const rows=measurements.filter(m=>m.device_id===device&&!m.replayed).sort((a,b)=>Date.parse(a.received_at)-Date.parse(b.received_at));
  const chartRows:Record<string,unknown>[]=[];
  rows.forEach((row,i)=>{
    const t=Date.parse(row.received_at);
    if(i&&t-Date.parse(rows[i-1].received_at)>2500)chartRows.push({time:t-1000,temperature:null,humidity:null,gas:null});
    chartRows.push({...row,time:t,temperature:row.temperature,humidity:row.humidity});
  });
  function download(){const blob=new Blob([JSON.stringify(history.length?history:rows,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='sentinel-mesures.json';a.click();URL.revokeObjectURL(a.href);}
  const alertList=tab==='alerts'?alerts:status?.active_alerts??[];

  if(!sessionChecked)return <div className="loading">Connexion à SENTINEL-X…</div>;
  if(!csrf)return <main className="login"><div className="login-art"><Shield size={70}/><span className="eyebrow">SURVEILLANCE INDUSTRIELLE LOCALE</span><h1>Une vue claire.<br/>Une longueur d’avance.</h1><p>Environnement, présence et état du système.<br/>Votre poste de supervision SENTINEL-X.</p><div className="login-line">EDGE COMPUTING <span> / </span> LOCAL AI <span> / </span> SECURE BY DESIGN</div></div><form onSubmit={login}><div className="brand"><Shield/> SENTINEL<span>-X</span></div><h2>Ouvrir la supervision</h2><p>Connectez-vous avec le compte opérateur local.</p><label>Identifiant<input value="operateur" readOnly autoComplete="username"/></label><label>Mot de passe<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required autoFocus/></label>{error&&<div role="alert" className="error">{error}</div>}<button className="primary" disabled={busy}>{busy?'Connexion…':'Se connecter'}<ArrowUpRight size={18}/></button><small>Les identifiants sont générés par le script de préparation.</small></form></main>;
  return <div className="shell"><aside><div className="brand"><Shield size={26}/>SENTINEL<span>-X</span></div><div className="workspace"><span className="dot"/> AVANT-POSTE 01<small>Centre de commande local</small></div><span className="nav-label">SUPERVISION</span><nav>{[['overview','Vue d’ensemble',Gauge],['alerts','Journal des alertes',Bell],['history','Historique',Activity]].map(([id,label,Icon])=><button key={id as string} className={tab===id?'selected':''} onClick={()=>setTab(id as string)}>{React.createElement(Icon as typeof Gauge,{size:18})}{label as string}{id==='alerts'&&<b>{status?.active_alerts.length??0}</b>}</button>)}</nav><div className="aside-footer"><div><Cpu size={16}/> Architecture locale</div><small>Traitement et stockage sur ce PC<br/>Aucun service cloud requis</small><div className="operator"><span>OP</span><div>Opérateur<small>Session locale sécurisée</small></div><button title="Se déconnecter" onClick={logout}><LogOut size={16}/></button></div></div></aside>
  <main className="dashboard"><header><div><span className="eyebrow">MISSION SENTINEL-X / POSTE DE SUPERVISION</span><h1>{tab==='overview'?'Vue d’ensemble':tab==='alerts'?'Journal des alertes':'Historique des mesures'}</h1><p>Surveillez votre zone. Comprenez les signaux. Gardez le contrôle.</p></div><div className="header-status"><span className={`pill ${connected?'normal':'offline'}`}><span className="dot"/>{connected?'Temps réel connecté':'Connexion interrompue'}</span><small>{status?clock(status.server_time):'En attente du serveur'}</small></div></header>
  {!connected&&<div className="error" role="alert">Backend injoignable — aucun heartbeat récent. Les données affichées sont périmées et les commandes sont désactivées.</div>}
  {connected&&!status?.database&&<div className="error" role="alert">E006 — Base indisponible. Le stockage et les commandes ne peuvent pas être confirmés.</div>}
  {connected&&current&&!current.online&&<div className="error" role="alert">E001 — {device} déconnecté : dernière mesure reçue il y a {current.age_seconds} s.</div>}
  {error&&<div className="error" role="alert">{error}<button onClick={()=>setError('')}>Fermer</button></div>}
  {notice&&<div className="empty" role="status"><Check size={20}/>{notice}</div>}
  <div className="overview-strip"><div><span className={`dot ${status?.overall}`}/><strong>{labels[connected?status?.overall??'initializing':'offline']}</strong><span className="strip-label">État général</span></div><div className="device-select"><Radio size={16}/><select aria-label="Appareil affiché" value={device} onChange={e=>{setDevice(e.target.value);setHistoryPage(0);}}>{Array.from(new Set(['sentinel-x-01',...Object.keys(status?.devices??{})])).map(id=><option key={id}>{id}</option>)}</select></div><span className="muted">{latest?`Dernière réception · ${clock(latest.received_at)}`:'En attente de télémétrie'}</span></div>
  {tab==='overview'&&<>
    <section className="metric-grid">{[['temperature','Température','°C',Thermometer,'dht22'],['humidity','Humidité','% HR',Wind,'dht22'],['gas','Gaz · valeur brute','ADC',Gauge,'mq2']].map(([key,label,unit,Icon,sensor])=>{const value=latest?.[key as 'temperature'];const readingAge=(latest?.sensor_age_ms[sensor as string]??0)+(current?.age_seconds??0)*1000;const invalid=latest?.sensor_status[sensor as string]!=='ok'||readingAge>(sensor==='dht22'?6000:2000);return <article className="metric" key={key as string}><div className="metric-top"><span>{label as string}</span>{React.createElement(Icon as typeof Gauge,{size:20})}</div><div className="metric-value">{live&&!invalid&&value!=null?value.toLocaleString('fr-FR',{maximumFractionDigits:1}):'—'}<small>{unit as string}</small></div><div className="metric-bottom"><span className={`dot ${live&&!invalid?'normal':'warning'}`}/>{!live?'Donnée périmée':invalid?'Capteur invalide':`Mesure âgée de ${Math.round(readingAge/1000)} s`}</div></article>;})}<article className="metric"><div className="metric-top"><span>Mouvement PIR</span><Eye size={20}/></div><div className="metric-value word">{!live||latest?.presence==null?'Indisponible':latest.presence?'Détecté':'Aucun'}</div><div className="metric-bottom"><span className={`dot ${latest?.presence?'warning':'normal'}`}/>Indice de mouvement</div></article></section>
    <section className="main-grid"><article className="panel chart-panel"><div className="panel-head"><div><span className="eyebrow">TÉLÉMÉTRIE</span><h2>Les 60 dernières secondes</h2></div><span className="outline-tag">1 message / seconde</span></div><div className="charts">{[['temperature','Température','#68dfb5','°C'],['humidity','Humidité','#80b9f4','%'],['gas','Gaz','#eac37b','ADC']].map(([key,label,color,unit])=><div className="chart" key={key}><div><span style={{color}}>{label}</span><small>{unit}</small></div><ResponsiveContainer width="100%" height={100}><AreaChart data={chartRows.filter(row=>key==='gas'||row.temperature===null&&row.humidity===null||((row.sensor_age_ms as Record<string,number> | undefined)?.dht22??0)===0)}><defs><linearGradient id={key} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity={.2}/><stop offset="100%" stopColor={color} stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#253236" strokeDasharray="3 5" vertical={false}/><XAxis dataKey="time" type="number" domain={['dataMin','dataMax']} tickFormatter={v=>clock(new Date(v).toISOString())} tick={{fontSize:10,fill:'#87969a'}} minTickGap={50} axisLine={false} tickLine={false}/><YAxis width={35} domain={['auto','auto']} tick={{fontSize:10,fill:'#87969a'}} axisLine={false} tickLine={false}/><Tooltip contentStyle={{background:'#142024',border:'1px solid #34464a',borderRadius:8,color:'#f1f5f3'}} labelFormatter={v=>clock(new Date(Number(v)).toISOString())}/><Area type="linear" dataKey={key} stroke={color} fill={`url(#${key})`} strokeWidth={2} dot={false} connectNulls={false}/></AreaChart></ResponsiveContainer></div>)}</div><small className="panel-note">Les coupures restent visibles. Le DHT22 produit une nouvelle acquisition toutes les 2 secondes.</small></article>
    <article className="panel vision-panel"><div className="panel-head"><div><span className="eyebrow">VISION LOCALE</span><h2>Zone de surveillance</h2></div><span className={`pill ${status?.vision.online&&status.vision.camera?'normal':'offline'}`}>{status?.vision.online&&status.vision.camera?'Direct':'Indisponible'}</span></div><div className="video-frame">{connected&&status?.vision.online&&status.vision.camera&&!videoError?<img key={status?.vision.stream_id} src="/api/v1/video" alt="Flux de surveillance annoté" onError={()=>setVideoError(true)}/>:<div className="video-empty"><Video size={36}/><strong>Aucun flux disponible</strong><span>Vérifiez le conteneur vision et sa source vidéo.</span></div>}<span className="camera-label">CAM 01 <span> / </span> WEBCAM · YOLO26-n</span></div><div className="vision-info"><div><span className="dot"/>Détection de personnes uniquement</div><small>Médiane {status?.vision.median_ms?.toFixed(1)??'—'} ms · p95 {status?.vision.p95_ms?.toFixed(1)??'—'} ms</small></div></article></section>
    <section className="secondary-grid"><article className="panel"><div className="panel-head"><div><span className="eyebrow">ANALYSE TEMPORELLE</span><h2>Détection d’anomalies</h2></div><Activity size={20}/></div><div className="anomaly-main"><span className={`pill ${decision?.state??'initializing'}`}>{labels[decision?.state??'initializing']}</span><div><strong>{decision?.score?.toFixed(3)??'—'}</strong><span>Score d’anomalie</span></div></div><div className="score-track"><div style={{width:decision?.score?`${Math.min(100,decision.score*100)}%`:'0%'}}/><i style={{left:`${(decision?.threshold??.65)*100}%`}}/></div><div className="score-caption"><span>Plus élevé = plus inhabituel</span><span>Seuil {decision?.threshold?.toFixed(3)??'—'}</span></div><p className="panel-note">Isolation Forest · référence physique de 30 s · 3 observations pour ouvrir une alerte, 10 pour la résoudre. Score sans valeur de probabilité. Lancez la calibration en conditions normales.</p><button disabled={!usable||busy} onClick={()=>action('model/retrain',{})}>{busy?'Opération en cours…':'Réentraîner sur les 30 dernières secondes'}</button></article><article className="panel"><div className="panel-head"><div><span className="eyebrow">CONTRÔLE À DISTANCE</span><h2>Actionneurs</h2></div><Cpu size={20}/></div><div className="controls">{[['buzzer','Buzzer',Volume2],['led','LED de test',Lightbulb]].map(([type,label,Icon])=><div className="control" key={type as string}>{React.createElement(Icon as typeof Gauge,{size:21})}<div><strong>{label as string}</strong><small>État confirmé dans le journal</small></div><button disabled={!usable||busy} onClick={()=>action('commands',{device_id:device,type,value:true,duration_ms:3000})}>Tester · 3 s</button><button aria-label={`Arrêter ${label}`} disabled={!usable||busy} onClick={()=>action('commands',{device_id:device,type,value:false,duration_ms:3000})}>Arrêter</button></div>)}</div><p className="panel-note">La LED système conserve la priorité. Une commande sans accusé reste d’exécution inconnue.</p><div className="command-log">{commands.slice(0,3).map(c=><div key={c.command_id}><span>{clock(c.created_at)} · {c.type}</span><span className={`text-${c.status}`}>{labels[c.status]}</span></div>)}</div></article></section>
  </>}
  {tab!=='history'&&<section className="panel alerts-panel"><div className="panel-head"><div><span className="eyebrow">ÉVÉNEMENTS</span><h2>{tab==='alerts'?'Tous les événements':'Alertes actives'} <span className="count">{alertList.length}</span></h2></div>{tab==='overview'&&<button className="link" onClick={()=>setTab('alerts')}>Voir le journal<ChevronRight size={16}/></button>}</div>{!alertList.length?<div className="empty"><Check size={20}/> Aucun événement à afficher.</div>:<div className="table-wrap"><table><thead><tr><th>Événement</th><th>Source</th><th>Début</th><th>État</th><th>Action</th></tr></thead><tbody>{alertList.map(a=><tr key={a.id}><td><span className={`dot ${a.severity}`}/><strong>{a.code?`${a.code} · `:''}{a.message}</strong></td><td><span className="outline-tag">{a.source}</span></td><td>{clock(a.created_at)}</td><td>{a.resolved_at?'Résolu':a.acknowledged_at?'Acquitté · actif':'Actif'}</td><td><button disabled={Boolean(a.acknowledged_at)||!connected||busy} onClick={()=>action(`alerts/${a.id}/ack`,{})}>{a.acknowledged_at?'Pris en compte':'Acquitter'}</button></td></tr>)}</tbody></table></div>}{tab==='alerts'&&<div className="pagination"><button disabled={!alertPage} onClick={()=>setAlertPage(p=>p-1)}>Précédent</button><span>Page {alertPage+1}</span><button disabled={alerts.length<50} onClick={()=>setAlertPage(p=>p+1)}>Suivant</button></div>}</section>}
  {tab==='history'&&<section className="panel"><div className="panel-head"><div><h2>Mesures archivées</h2><p className="panel-note">7 derniers jours · {device} · 50 mesures par page</p></div><button onClick={download}><Download size={16}/>Exporter cette page</button></div><div className="table-wrap"><table><thead><tr><th>Réception</th><th>Température</th><th>Humidité</th><th>Gaz ADC</th><th>Origine</th><th>Reprise</th></tr></thead><tbody>{history.map(m=><tr key={`${m.device_id}-${m.boot_id}-${m.sequence}`}><td>{new Date(m.received_at).toLocaleString('fr-FR')}</td><td>{m.temperature??'—'} °C</td><td>{m.humidity??'—'} %</td><td>{m.gas??'—'}</td><td>{m.source}</td><td>{m.replayed?'Oui':'Non'}</td></tr>)}</tbody></table></div><div className="pagination"><button disabled={!historyPage} onClick={()=>setHistoryPage(p=>p-1)}>Précédent</button><span>Page {historyPage+1}</span><button disabled={history.length<50} onClick={()=>setHistoryPage(p=>p+1)}>Suivant</button></div></section>}
  <footer><div><Wifi size={14}/>{status?.mqtt==='disabled'?'MQTT non configuré':`MQTT ${status?.mqtt}`}<span>•</span>Stockage {status?.database?'disponible':'indisponible'}<span>•</span>Modèle {status?.model?'chargé':'absent'}</div><span>SENTINEL-X · Workshop 2026</span></footer>
  </main></div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
