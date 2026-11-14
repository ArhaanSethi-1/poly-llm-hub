# Roadmap – Poly‑LLM Hub (AI‑Model‑Aggregator UI)

## Overview
A cross‑platform app that lets a user **select any locally‑installed LLM client** (ChatGPT, Claude, DeepSeek, Grok, Antigravity, …), send a prompt, and display the response – all from a single UI. The app orchestrates the existing CLIs, adds optional multi‑model comparison/fusion, and stays fully compliant with each provider’s licensing.

---

## Phase‑by‑Phase Timeline
| Phase | Duration | Goal | Deliverables |
|-------|----------|------|--------------|
| **0️⃣ Prep** | 1 wk | Workspace & repo set‑up | GitHub repo, folder layout (frontend, dispatcher, docs) |
| **1️⃣ Discovery & Config** | 1 wk | Detect installed model CLIs | `client-detect.ts` → `models.json`, install guide |
| **2️⃣ Unified Prompt Schema** | 1 wk | Canonical JSON prompt definition | `PromptSchema.ts`, translators for each client |
| **3️⃣ Dispatcher Service** | 2 wks | Background HTTP/IPC server | `POST /query {modelId,prompt}` endpoint, async CLI execution, unit tests |
| **4️⃣ Front‑end UI** | 2 wks | Cross‑platform UI (React‑Native / Electron) | Model selector, prompt box, result pane |
| **5️⃣ Parallel & Fusion Layer** | 2 wks | Compare multiple models & fuse answers | Side‑by‑side view, majority‑vote selector, meta‑LLM summariser |
| **6️⃣ Settings & Security** | 1 wk | Store API keys locally, encrypted | Encrypted config, Settings screen, env‑var injection |
| **7️⃣ Policy & License Guard** | 1 wk | Enforce provider usage policies | `policy.json`, runtime checks, friendly UI errors |
| **8️⃣ QA & User Study** | 2 wks | Verify correctness & usability | Integration tests, small pilot (3‑5 users), latency & satisfaction metrics |
| **9️⃣ Documentation & Research Write‑up** | 2 wks | Produce usable docs & dissertation chapter | README, architecture diagram (Mermaid), research paper outline |
| **🔟 Release** | 1 wk | Publish open‑source release | GitHub tag v1.0.0, installer binaries, community guide |

**Total:** ~14 weeks (≈ 3½ months)

---

## Weekly Action Plan
- **Week 1:** Initialise repo, CI, `client-detect` script, draft README.
- **Week 2:** Design `PromptSchema`, implement translators for OpenAI & Anthropic, add unit tests.
- **Week 3:** Scaffold dispatcher (Express or FastAPI), wrap `runCommand`, test with dummy CLI.
- **Week 4:** Create React‑Native (or Electron) skeleton, ModelSelect component, wire to dispatcher.
- **Week 5:** Add “Compare” mode, parallel dispatch, simple fusion (longest reply / meta‑LLM).
- **Week 6:** Settings screen → encrypted API‑key storage, env‑var injection for CLIs.
- **Week 7:** Draft `policy.json`, add middleware to block disallowed usage.
- **Week 8:** Write Cypress / Playwright end‑to‑end tests, run pilot study, collect metrics.
- **Week 9:** Architecture diagram (Mermaid), write research chapter on unified translation & fusion.
- **Week 10:** Polish README, generate installers, tag release, announce.

---

## Core Code Snippets (Reference)
### 1️⃣ Client‑Detect (Node)
```ts
// src/client-detect.ts
import { execSync } from 'child_process';
const CLIs = ['openai','anthropic','deepseek','grok','agy'];
const found: Record<string,string> = {};
CLIs.forEach(cli=>{ try{ const p = execSync(`where ${cli}`).toString().trim().split(/\r?\n/)[0]; found[cli]=p; } catch {} });
import * as fs from 'fs';
fs.writeFileSync('models.json', JSON.stringify(found, null, 2));
```

### 2️⃣ Dispatcher (Express)
```js
const express = require('express');
const { execFile } = require('child_process');
const app = express(); app.use(express.json());
function buildCmd(id,p){ const map={ openai:['openai',['api','chat.completions','--model','gpt-4o-mini','--prompt',p]], anthropic:['anthropic',['completion','--model','claude-3-5-sonnet','--prompt',p]] }; return map[id]; }
app.post('/query', (req,res)=>{ const {modelId,prompt}=req.body; const [cmd,args]=buildCmd(modelId,prompt); if(!cmd) return res.status(400).json({error:'unknown model'});
 const child = execFile(cmd,args,{windowsHide:true}); let out=''; child.stdout.on('data',d=>out+=d);
 child.on('close',code=>{ if(code===0) res.json({reply:out.trim()}); else res.status(500).json({error:`${cmd} exited ${code}`}); }); });
app.listen(3001,()=>console.log('Dispatcher ready on :3001'));
```

### 3️⃣ React‑Native Prompt UI (TSX)
```tsx
export default function PromptScreen(){
  const [models,setModels]=useState<string[]>([]);
  const [model,setModel]=useState('');
  const [prompt,setPrompt]=useState('');
  const [reply,setReply]=useState('');
  useEffect(()=>fetch('file:///C:/Users/arhaa/.gemini/antigravity/brain/4d9b0a16-844e-4804-866a-be35de741387/models.json')
    .then(r=>r.json()).then(j=>{setModels(Object.keys(j)); setModel(Object.keys(j)[0]);}),[]);
  const send=async()=>{ const r=await fetch('http://localhost:3001/query',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({modelId:model,prompt})}); const {reply}=await r.json(); setReply(reply); };
  return (<View style={{padding:12}}>
    <Picker selectedValue={model} onValueChange={setModel}> {models.map(m=> <Picker.Item key={m} label={m} value={m}/>)} </Picker>
    <TextInput multiline placeholder="Prompt…" value={prompt} onChangeText={setPrompt}
      style={{height:120,borderWidth:1,marginVertical:8}}/>
    <Button title="Send" onPress={send}/>
    <ScrollView style={{marginTop:12}}><Text>{reply}</Text></ScrollView>
  </View>);
}
```

---

## Research Extensions (Optional Chapters)
1. **Unified Prompt Translation** – latency vs. expressive power.
2. **Parallel Multi‑Model Inference** – optimal concurrency on typical laptops.
3. **Result Fusion Strategies** – voting vs. meta‑LLM summarisation on benchmark QA.
4. **Privacy‑by‑Design Orchestration** – guarantee zero‑disk writes of prompts.
5. **Policy Engine** – machine‑readable encoding of diverse provider TOS.

---

## Release Checklist
- [ ] Detect all CLIs on Windows/macOS/Linux.
- [ ] Encrypted storage of API keys.
- [ ] License disclaimer shown on first launch.
- [ ] CI runs unit & e2e tests.
- [ ] Accessibility (screen‑reader labels, high‑contrast).
- [ ] Documentation includes "Add a new model" guide.
- [ ] Publish installers for Windows (`.exe`), macOS (`.dmg`), Linux (`.tar.gz`).

---

*You can now open `roadmap.md` in the artifact directory to view the full plan.*
