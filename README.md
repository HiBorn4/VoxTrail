# 🎙️ VoxTrail — Voice-Powered Corporate Travel AI

> **Talk your way through business travel.** Book flights, manage reimbursements, and review trip history — all with natural voice commands, powered by Google Gemini Live + a multi-agent AI backend.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Google ADK](https://img.shields.io/badge/Google%20ADK-Gemini%20Live-4285F4?style=flat-square&logo=google&logoColor=white)](https://ai.google.dev)
[![Redis](https://img.shields.io/badge/Redis-Session%20Store-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

---

## 📸 Demo![nexusiq_architecture](https://github.com/user-attachments/assets/252cb7db-5202-458c-ba64-20f9ebdd66cd)<svg width="100%" viewBox="0 0 680 820" xmlns="http://www.w3.org/2000/svg">
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </marker>
<mask id="imagine-text-gaps-nexvvr" maskUnits="userSpaceOnUse"><rect x="0" y="0" width="680" height="820" fill="white"/><rect x="284.3506164550781" y="27.027769088745117" width="111.98551940917969" height="21.9444637298584" fill="black" rx="2"/><rect x="270.5307312011719" y="44.444435119628906" width="139.64910888671875" height="19.111123085021973" fill="black" rx="2"/><rect x="347.9999694824219" y="73.72220611572266" width="70.95592880249023" height="19.11112689971924" fill="black" rx="2"/><rect x="280.0784912109375" y="111.02776336669922" width="120.52576446533203" height="21.9444637298584" fill="black" rx="2"/><rect x="232.42822265625" y="130.44444274902344" width="214.90525817871094" height="19.11112689971924" fill="black" rx="2"/><rect x="255.74423217773438" y="205.02777099609375" width="169.3701171875" height="21.9444637298584" fill="black" rx="2"/><rect x="227.30018615722656" y="224.44442749023438" width="225.2854766845703" height="19.11112689971924" fill="black" rx="2"/><rect x="347.9999694824219" y="260.7221984863281" width="136.47386169433594" height="19.11112689971924" fill="black" rx="2"/><rect x="45.0555534362793" y="295.7221984863281" width="207.1841278076172" height="19.11112689971924" fill="black" rx="2"/><rect x="278.4804382324219" y="325.0277404785156" width="83.6561050415039" height="21.9444637298584" fill="black" rx="2"/><rect x="227.3697052001953" y="342.4444274902344" width="185.150390625" height="19.11112689971924" fill="black" rx="2"/><rect x="73.55376434326172" y="405.02777099609375" width="113.51014709472656" height="21.9444637298584" fill="black" rx="2"/><rect x="47.6036491394043" y="422.4444274902344" width="164.60678100585938" height="19.11112689971924" fill="black" rx="2"/><rect x="58.21390151977539" y="436.4444274902344" width="143.62493896484375" height="19.11112689971924" fill="black" rx="2"/><rect x="261.7239074707031" y="405.02777099609375" width="116.23826599121094" height="21.9444637298584" fill="black" rx="2"/><rect x="257.62884521484375" y="422.4444274902344" width="124.19569396972656" height="19.11112689971924" fill="black" rx="2"/><rect x="257.8723449707031" y="436.4444274902344" width="123.75411224365234" height="19.11112689971924" fill="black" rx="2"/><rect x="453.1900329589844" y="405.02777099609375" width="94.24653625488281" height="21.9444637298584" fill="black" rx="2"/><rect x="453.35235595703125" y="422.4444274902344" width="93.75171661376953" height="19.11112689971924" fill="black" rx="2"/><rect x="438.01251220703125" y="436.4444274902344" width="124.6824722290039" height="19.11112689971924" fill="black" rx="2"/><rect x="278.5511474609375" y="519.0277099609375" width="123.26162719726562" height="21.9444637298584" fill="black" rx="2"/><rect x="133.41641235351562" y="536.4443969726562" width="413.1670837402344" height="19.11112689971924" fill="black" rx="2"/><rect x="347.0555419921875" y="563.72216796875" width="104.6373062133789" height="19.11112689971924" fill="black" rx="2"/><rect x="268.1622314453125" y="601.0277709960938" width="144.52459716796875" height="21.9444637298584" fill="black" rx="2"/><rect x="172.02798461914062" y="618.4444580078125" width="336.7817687988281" height="19.11112689971924" fill="black" rx="2"/><rect x="235.42388916015625" y="632.4443969726562" width="209.75933837890625" height="19.11112689971924" fill="black" rx="2"/><rect x="113.79942321777344" y="713.0277099609375" width="132.4011688232422" height="21.9444637298584" fill="black" rx="2"/><rect x="86.71302032470703" y="730.4443969726562" width="187.40512084960938" height="19.11112689971924" fill="black" rx="2"/><rect x="428.02203369140625" y="713.0277099609375" width="143.95587158203125" height="21.9444637298584" fill="black" rx="2"/><rect x="437.1566162109375" y="730.4443969726562" width="125.50050354003906" height="19.11112689971924" fill="black" rx="2"/><rect x="244.9495086669922" y="789.0277709960938" width="189.83787536621094" height="21.9444637298584" fill="black" rx="2"/><rect x="581.72216796875" y="207.02777099609375" width="67.21921920776367" height="21.9444637298584" fill="black" rx="2"/><rect x="576.2252197265625" y="221.0277557373047" width="78.87952423095703" height="21.9444637298584" fill="black" rx="2"/><rect x="557.6978759765625" y="236.44442749023438" width="114.27991485595703" height="19.11112689971924" fill="black" rx="2"/><rect x="30.60803985595703" y="111.02776336669922" width="70.03797149658203" height="21.9444637298584" fill="black" rx="2"/><rect x="14.434412002563477" y="128.44442749023438" width="100.79905700683594" height="19.11112689971924" fill="black" rx="2"/><rect x="26.468711853027344" y="142.44444274902344" width="76.826904296875" height="19.11112689971924" fill="black" rx="2"/><rect x="563.098876953125" y="111.02776336669922" width="104.12348937988281" height="21.9444637298584" fill="black" rx="2"/><rect x="577.4205322265625" y="128.44442749023438" width="75.60359191894531" height="19.11112689971924" fill="black" rx="2"/></mask></defs>

<!-- ── USER LAYER ── -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="240" y="20" width="200" height="44" rx="8" stroke-width="0.5" style="fill:rgb(60, 52, 137);stroke:rgb(175, 169, 236);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="340" y="38" text-anchor="middle" dominant-baseline="central" style="fill:rgb(206, 203, 246);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">User / Frontend</text>
  <text x="340" y="54" text-anchor="middle" dominant-baseline="central" style="fill:rgb(175, 169, 236);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">Natural language query</text>
</g>

<!-- User → FastAPI -->
<line x1="340" y1="64" x2="340" y2="104" marker-end="url(#arrow)" stroke="var(--color-border-primary)" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
<text x="352" y="88" fill="var(--color-text-secondary)" style="fill:rgb(194, 192, 182);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:start;dominant-baseline:auto">POST /chat</text>

<!-- ── FASTAPI LAYER ── -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="190" y="104" width="300" height="56" rx="8" stroke-width="0.5" style="fill:rgb(12, 68, 124);stroke:rgb(133, 183, 235);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="340" y="122" text-anchor="middle" dominant-baseline="central" style="fill:rgb(181, 212, 244);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">FastAPI Backend</text>
  <text x="340" y="140" text-anchor="middle" dominant-baseline="central" style="fill:rgb(133, 183, 235);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">Auth check · Session mgmt · Caching</text>
</g>

<!-- FastAPI → Router -->
<line x1="340" y1="160" x2="340" y2="198" marker-end="url(#arrow)" stroke="var(--color-border-primary)" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>

<!-- ── QUERY ROUTER ── -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="200" y="198" width="280" height="56" rx="8" stroke-width="0.5" style="fill:rgb(99, 56, 6);stroke:rgb(239, 159, 39);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="340" y="216" text-anchor="middle" dominant-baseline="central" style="fill:rgb(250, 199, 117);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">Intelligent Query Router</text>
  <text x="340" y="234" text-anchor="middle" dominant-baseline="central" style="fill:rgb(239, 159, 39);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">Gemini 2.5 · Table selection · Agent tier</text>
</g>

<!-- Router → ADK Runner -->
<line x1="340" y1="254" x2="340" y2="290" marker-end="url(#arrow)" stroke="var(--color-border-primary)" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
<text x="352" y="275" fill="var(--color-text-secondary)" style="fill:rgb(194, 192, 182);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:start;dominant-baseline:auto">Router output injected</text>

<!-- ── GOOGLE ADK CONTAINER ── -->
<rect x="30" y="290" width="620" height="200" rx="12" fill="none" stroke="var(--color-border-secondary)" stroke-width="0.5" stroke-dasharray="6 4" style="fill:none;stroke:rgba(222, 220, 209, 0.3);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-dasharray:6px, 4px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
<text x="50" y="310" fill="var(--color-text-secondary)" style="fill:rgb(194, 192, 182);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:start;dominant-baseline:auto">Google ADK — Multi-Agent System</text>

<!-- Root Agent -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="220" y="318" width="200" height="44" rx="8" stroke-width="0.5" style="fill:rgb(8, 80, 65);stroke:rgb(93, 202, 165);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="320" y="336" text-anchor="middle" dominant-baseline="central" style="fill:rgb(159, 225, 203);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">Root Agent</text>
  <text x="320" y="352" text-anchor="middle" dominant-baseline="central" style="fill:rgb(93, 202, 165);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">ADK LlmAgent + BuiltInPlanner</text>
</g>

<!-- Root → sub agents -->
<line x1="260" y1="362" x2="130" y2="398" marker-end="url(#arrow)" stroke="var(--color-border-primary)" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
<line x1="320" y1="362" x2="320" y2="398" marker-end="url(#arrow)" stroke="var(--color-border-primary)" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
<line x1="380" y1="362" x2="510" y2="398" marker-end="url(#arrow)" stroke="var(--color-border-primary)" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>

<!-- Sub Agent: BigQuery -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="50" y="398" width="160" height="56" rx="8" stroke-width="0.5" style="fill:rgb(8, 80, 65);stroke:rgb(93, 202, 165);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="130" y="416" text-anchor="middle" dominant-baseline="central" style="fill:rgb(159, 225, 203);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">BigQuery Agent</text>
  <text x="130" y="432" text-anchor="middle" dominant-baseline="central" style="fill:rgb(93, 202, 165);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">CHASE NL2SQL framework</text>
  <text x="130" y="446" text-anchor="middle" dominant-baseline="central" style="fill:rgb(93, 202, 165);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">SQL execution · schema</text>
</g>

<!-- Sub Agent: Analytics -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="238" y="398" width="164" height="56" rx="8" stroke-width="0.5" style="fill:rgb(8, 80, 65);stroke:rgb(93, 202, 165);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="320" y="416" text-anchor="middle" dominant-baseline="central" style="fill:rgb(159, 225, 203);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">Analytics Agent</text>
  <text x="320" y="432" text-anchor="middle" dominant-baseline="central" style="fill:rgb(93, 202, 165);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">Gemini 2.5 Pro/Flash</text>
  <text x="320" y="446" text-anchor="middle" dominant-baseline="central" style="fill:rgb(93, 202, 165);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">Summarize · insights</text>
</g>

<!-- Sub Agent: BQML -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="420" y="398" width="160" height="56" rx="8" stroke-width="0.5" style="fill:rgb(8, 80, 65);stroke:rgb(93, 202, 165);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="500" y="416" text-anchor="middle" dominant-baseline="central" style="fill:rgb(159, 225, 203);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">BQML Agent</text>
  <text x="500" y="432" text-anchor="middle" dominant-baseline="central" style="fill:rgb(93, 202, 165);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">ML predictions</text>
  <text x="500" y="446" text-anchor="middle" dominant-baseline="central" style="fill:rgb(93, 202, 165);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">Forecasting · scoring</text>
</g>

<!-- ADK → BigQuery DB -->
<line x1="130" y1="454" x2="130" y2="512" marker-end="url(#arrow)" stroke="var(--color-border-primary)" mask="url(#imagine-text-gaps-nexvvr)" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
<line x1="320" y1="454" x2="320" y2="512" marker-end="url(#arrow)" stroke="var(--color-border-primary)" mask="url(#imagine-text-gaps-nexvvr)" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
<line x1="500" y1="454" x2="500" y2="512" marker-end="url(#arrow)" stroke="var(--color-border-primary)" mask="url(#imagine-text-gaps-nexvvr)" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>

<!-- ── DATA LAYER ── -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="50" y="512" width="580" height="44" rx="8" stroke-width="0.5" style="fill:rgb(68, 68, 65);stroke:rgb(180, 178, 169);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="340" y="530" text-anchor="middle" dominant-baseline="central" style="fill:rgb(211, 209, 199);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">Google BigQuery</text>
  <text x="340" y="546" text-anchor="middle" dominant-baseline="central" style="fill:rgb(180, 178, 169);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">HR_AI dataset · Dynamic schema profiling · Cached schema (60 min TTL)</text>
</g>

<!-- BQ → Orchestrator -->
<line x1="340" y1="556" x2="340" y2="594" marker-end="url(#arrow)" stroke="var(--color-border-primary)" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
<text x="352" y="578" fill="var(--color-text-secondary)" style="fill:rgb(194, 192, 182);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:start;dominant-baseline:auto">SQL result + text</text>

<!-- ── INSIGHT ORCHESTRATOR ── -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="170" y="594" width="340" height="56" rx="8" stroke-width="0.5" style="fill:rgb(113, 43, 19);stroke:rgb(240, 153, 123);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="340" y="612" text-anchor="middle" dominant-baseline="central" style="fill:rgb(245, 196, 179);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">Insight Orchestrator</text>
  <text x="340" y="628" text-anchor="middle" dominant-baseline="central" style="fill:rgb(240, 153, 123);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">Intent engine · Gemini data extractor · Chart recommender</text>
  <text x="340" y="642" text-anchor="middle" dominant-baseline="central" style="fill:rgb(240, 153, 123);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">Fast-path table parser · Quality gate</text>
</g>

<!-- Orchestrator → Plotly -->
<line x1="280" y1="650" x2="190" y2="706" marker-end="url(#arrow)" stroke="var(--color-border-primary)" mask="url(#imagine-text-gaps-nexvvr)" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
<!-- Orchestrator → Matplotlib -->
<line x1="400" y1="650" x2="490" y2="706" marker-end="url(#arrow)" stroke="var(--color-border-primary)" mask="url(#imagine-text-gaps-nexvvr)" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>

<!-- Plotly -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="60" y="706" width="240" height="44" rx="8" stroke-width="0.5" style="fill:rgb(39, 80, 10);stroke:rgb(151, 196, 89);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="180" y="724" text-anchor="middle" dominant-baseline="central" style="fill:rgb(192, 221, 151);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">Plotly (interactive)</text>
  <text x="180" y="740" text-anchor="middle" dominant-baseline="central" style="fill:rgb(151, 196, 89);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">Bar · Donut · Line · Area · Scatter</text>
</g>

<!-- Matplotlib -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="380" y="706" width="240" height="44" rx="8" stroke-width="0.5" style="fill:rgb(68, 68, 65);stroke:rgb(180, 178, 169);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="500" y="724" text-anchor="middle" dominant-baseline="central" style="fill:rgb(211, 209, 199);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">Matplotlib (fallback)</text>
  <text x="500" y="740" text-anchor="middle" dominant-baseline="central" style="fill:rgb(180, 178, 169);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">Static image fallback</text>
</g>

<!-- Both → Response -->
<line x1="180" y1="750" x2="290" y2="784" marker-end="url(#arrow)" stroke="var(--color-border-primary)" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
<line x1="500" y1="750" x2="390" y2="784" marker-end="url(#arrow)" stroke="var(--color-border-primary)" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>

<!-- ── FINAL RESPONSE ── -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="200" y="784" width="280" height="24" rx="6" stroke-width="0.5" style="fill:rgb(12, 68, 124);stroke:rgb(133, 183, 235);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="340" y="800" text-anchor="middle" dominant-baseline="central" style="fill:rgb(181, 212, 244);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">JSON response → frontend</text>
</g>

<!-- Side elements: Dynamic Prompting -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="560" y="198" width="110" height="56" rx="8" stroke-width="0.5" style="fill:rgb(114, 36, 62);stroke:rgb(237, 147, 177);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="615" y="218" text-anchor="middle" dominant-baseline="central" style="fill:rgb(244, 192, 209);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">Dynamic</text>
  <text x="615" y="232" text-anchor="middle" dominant-baseline="central" style="fill:rgb(244, 192, 209);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">Prompting</text>
  <text x="615" y="246" text-anchor="middle" dominant-baseline="central" style="fill:rgb(237, 147, 177);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">Schema + rules JIT</text>
</g>
<line x1="560" y1="226" x2="480" y2="226" marker-end="url(#arrow)" stroke="var(--color-border-secondary)" stroke-dasharray="4 3" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-dasharray:4px, 3px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>

<!-- Side: Firestore -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="10" y="104" width="110" height="56" rx="8" stroke-width="0.5" style="fill:rgb(68, 68, 65);stroke:rgb(180, 178, 169);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="65" y="122" text-anchor="middle" dominant-baseline="central" style="fill:rgb(211, 209, 199);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">Firestore</text>
  <text x="65" y="138" text-anchor="middle" dominant-baseline="central" style="fill:rgb(180, 178, 169);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">Sessions · cache</text>
  <text x="65" y="152" text-anchor="middle" dominant-baseline="central" style="fill:rgb(180, 178, 169);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">chat history</text>
</g>
<line x1="190" y1="132" x2="120" y2="132" marker-end="url(#arrow)" stroke="var(--color-border-secondary)" stroke-dasharray="4 3" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-dasharray:4px, 3px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>

<!-- Side: GCS -->
<g style="fill:rgb(0, 0, 0);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto">
  <rect x="560" y="104" width="110" height="44" rx="8" stroke-width="0.5" style="fill:rgb(68, 68, 65);stroke:rgb(180, 178, 169);color:rgb(255, 255, 255);stroke-width:0.5px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
  <text x="615" y="122" text-anchor="middle" dominant-baseline="central" style="fill:rgb(211, 209, 199);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:14px;font-weight:500;text-anchor:middle;dominant-baseline:central">Cloud Storage</text>
  <text x="615" y="138" text-anchor="middle" dominant-baseline="central" style="fill:rgb(180, 178, 169);stroke:none;color:rgb(255, 255, 255);stroke-width:1px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:12px;font-weight:400;text-anchor:middle;dominant-baseline:central">File uploads</text>
</g>
<line x1="490" y1="132" x2="560" y2="126" marker-end="url(#arrow)" stroke="var(--color-border-secondary)" stroke-dasharray="4 3" style="fill:none;stroke:rgb(156, 154, 146);color:rgb(255, 255, 255);stroke-width:1.5px;stroke-dasharray:4px, 3px;stroke-linecap:butt;stroke-linejoin:miter;opacity:1;font-family:&quot;Anthropic Sans&quot;, -apple-system, BlinkMacSystemFont, &quot;Segoe UI&quot;, sans-serif;font-size:16px;font-weight:400;text-anchor:start;dominant-baseline:auto"/>
</svg>

### 🎬 Full Demo Video
```


https://github.com/user-attachments/assets/463ff93e-247b-4dfd-b2d2-b9293eaefa2d


```

---

## 🧠 What Is VoxTrail?

VoxTrail is a **production-grade, voice-first AI assistant** built for corporate travel management. Instead of clicking through clunky travel portals, employees speak naturally:

> *"Book me a flight from Mumbai to Delhi next Friday, economy, aisle seat"*

The system understands, confirms, and books — entirely via voice. Under the hood, a **multi-agent architecture** powered by Google's Agent Development Kit (ADK) routes requests intelligently across specialized AI agents backed by real enterprise APIs (SAP, Redis, custom reimbursement pipelines).

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🎙️ **Real-time voice interface** | WebSocket-based bidirectional audio using `gemini-live-2.5-flash-preview-native-audio` |
| 🤖 **Multi-agent orchestration** | OrchestratorAgent → TravelBookingAgent / ReimbursementAgent / RedisDataAgent |
| ✈️ **Full flight booking flow** | Search → select → reprice → confirm, with SAP integration |
| 🧾 **Reimbursement AI** | Upload receipts → AI analysis → structured claim submission |
| 📂 **Trip history** | Redis MCP-powered retrieval of past trips and expenses |
| 💬 **Text + voice parity** | SSE-streamed chat fallback for accessibility and testing |
| 🔒 **Enterprise auth** | MSAL-based Azure AD login, AES-encrypted JWT pipeline |
| 🔭 **Observability** | OpenTelemetry tracing → Phoenix dashboard |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT / BROWSER                          │
│   Voice (WebSocket / PCM16) ◄──────────► Text (SSE / REST)     │
└──────────────────────┬──────────────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │   FastAPI App   │  ← MSAL Auth · AES JWT · CORS
              │   (app.py)      │
              └──┬──────────┬───┘
                 │          │
    ┌────────────▼──┐    ┌──▼────────────────┐
    │ Voice WS      │    │   REST/SSE Chat    │
    │ Handler       │    │   Endpoints        │
    │ (Google ADK   │    │   (InMemoryRunner) │
    │  LiveRunner)  │    └──────────┬─────────┘
    └──────┬────────┘               │
           │                        │
     ┌─────▼────────────────────────▼──────┐
     │         OrchestratorAgent            │
     │         (gemini-2.5-flash)           │
     │         Intent routing · Memory      │
     └─────┬────────────┬──────────┬────────┘
           │            │          │
  ┌────────▼──┐  ┌──────▼──┐  ┌───▼───────────┐
  │  Travel   │  │ Reimburse│  │  RedisData    │
  │  Booking  │  │ Agent    │  │  Agent        │
  │  Agent    │  │ (2.5-pro)│  │  (2.5-flash)  │
  │ (2.5-pro) │  └──────────┘  └───────────────┘
  └──────┬────┘        │               │
         │        Reimbursement      Redis MCP
      SAP APIs      APIs            Server (MCP)
   (flights, trips, CSRF)
```

> 📌 See `architecture.svg` in the repo root for the full visual diagram.

---

## 📁 Project Structure

```
VoxTrail/
│
├── app.py                          # FastAPI entry point, auth, all routes
├── runtime.py                      # ADK Runner + Phoenix OTEL setup
├── agent.py                        # Multi-agent definitions (Orchestrator, Travel, Reimbursement, Redis)
├── voice_orchestrator_agent.py     # Gemini Live voice agent + tool delegation
├── voice_websocket_handler.py      # WebSocket lifecycle, ADK LiveRunner integration
├── voice_tool_delegates.py         # Bridge: voice agent → backend specialist agents
├── voice_context_tool.py           # Shared tool: passes voice context to sub-agents
│
├── config2.py                      # App config, agent instructions, DEFAULT_TRAVEL_STATE schema
├── schemas.py                      # Pydantic models: ChatEnvelope, FlightDetails, etc.
├── schema_with_travel_dict.py      # Extended schema variants
│
├── function_tools_router.py        # All SAP-facing function tool definitions
├── cancel_trip.py                  # Trip cancellation API wrapper
├── check_trip_validity.py          # Trip validation logic
├── post_es_final.py                # Non-flight booking finalization
├── post_es_final_flight.py         # Flight booking finalization (SAP)
├── post_es_get.py                  # Non-flight search
├── post_es_get_flight.py           # Flight search API
├── post_es_reprice.py              # Repricing flow
├── reimbursement_api.py            # Receipt analysis API
├── reimbursement_submit.py         # Claim submission
├── sap_csrf.py                     # SAP CSRF token fetch
├── trip_details_api.py             # Individual trip detail retrieval
│
├── session_service.py              # ADK session create/read/diff/merge
├── redis_manager.py                # RedisJSONManager: hierarchical key store
├── session_cleanup.py              # Session + Redis data cleanup
├── permanent_store.py              # Persistent chat history (DB)
├── chat_extract.py                 # Extract message pairs from ADK events
│
├── utils.py                        # JWT decode, user extraction, trip categorizer
├── env_loader.py                   # .env loading helper
│
└── voicebot/                       # Standalone voice client utilities
    ├── realtime_speechbot.py       # Azure OpenAI Realtime client (mic → API → speaker)
    ├── realtime_speechbot_copy.py  # Experimental variant
    ├── realtime_transcribing.py    # Live transcription only mode
    └── wav_to_mp4.py               # Audio format converter
```

---

## ⚡ Quick Start

### Prerequisites

- Python 3.11+
- Redis server (local or remote)
- Google Cloud project with Gemini API access
- SAP Travel API credentials (for full booking flow)
- Azure AD app registration (for enterprise auth)

### 1. Clone & Install

```bash
git clone https://github.com/hiborn4/VoxTrail.git
cd VoxTrail

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Google AI
GOOGLE_API_KEY=your_gemini_api_key
GOOGLE_CLOUD_PROJECT=your_gcp_project_id

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# Auth
JWT_SECRET_KEY=your_jwt_secret_here
AES_SECRET_KEY=your_16_byte_aes_key

# Azure AD (optional, for enterprise auth)
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
AZURE_TENANT_ID=

# SAP (optional, for booking integration)
SAP_BASE_URL=
SAP_API_KEY=
```

### 3. Start Redis

```bash
# Docker (recommended)
docker run -d -p 6379:6379 redis:alpine

# Or local install
redis-server
```

### 4. Run

```bash
uvicorn app:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for the interactive API explorer.

For voice, open the frontend on port 3000 (or 5173 for Vite dev server) and connect via WebSocket to `/ws/voice/{session_id}`.

---

## 🎙️ How the Voice Flow Works

```
User speaks → Browser captures PCM16 audio
    → WebSocket stream → FastAPI /ws/voice/{session_id}
    → Google ADK LiveRunner (voice_orchestrator_agent)
    → Gemini Live understands intent
    → Delegates to specialist agent via tool call
    → Specialist agent calls SAP / Redis APIs
    → Returns structured ChatEnvelope response
    → ADK synthesizes voice response (voice: "Puck")
    → Audio streamed back to browser → Speaker playback
```

Key technical choices:
- **Bidirectional streaming** with `RunConfig(streaming_mode="bidi")`
- **Server VAD** for natural turn detection (silence_duration_ms=1000)
- **Session resumption** via transparent ADK config for reconnect resilience
- **Voice context tool** bridges voice agent → sub-agents without losing transcript context

---

## 🤖 Agent Architecture Deep Dive

### OrchestratorAgent (`gemini-2.5-flash`)
Pure routing agent. Receives user message → detects intent → delegates to correct specialist. Never calls tools directly, never makes up booking data.

### TravelBookingAgent (`gemini-2.5-pro`)
Manages the full booking lifecycle:
1. Collect travel details (origin, destination, dates, class, cost center)
2. Search flights via SAP API
3. Present options, handle user selection
4. Reprice selected flight
5. Confirm and finalize booking

### ReimbursementAgent (`gemini-2.5-pro`)
- Guides user through document upload
- Calls AI analysis API to extract line items from receipts
- Reviews results with user
- Submits structured claim

### RedisDataAgent (`gemini-2.5-flash`)
- Uses Redis MCP Server to read trip and expense history
- Answers questions about past travel without SAP API calls

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **API Framework** | FastAPI + Uvicorn |
| **AI Agents** | Google ADK (Agent Development Kit) |
| **LLMs** | Gemini 2.5 Flash, Gemini 2.5 Pro, Gemini Live Flash |
| **Voice** | Google Gemini Live (native audio), Azure OpenAI Realtime (voicebot/) |
| **Session Store** | Redis (via RedisJSONManager + MCP Server) |
| **Auth** | MSAL / Azure AD + AES-encrypted JWT |
| **Observability** | OpenTelemetry + Phoenix (Arize) |
| **Data Models** | Pydantic v2 |
| **Database** | SQLAlchemy (permanent chat store) |

---

## 📸 Media Guide

### What Screenshots to Capture

1. **Voice interface active state** — Show the waveform animation while speaking. Ideal: side by side with the bot's text response appearing simultaneously.
2. **Booking confirmation screen** — After the AI confirms a flight, capture the full `ChatEnvelope` response rendered in the frontend with flight details, seat class, and cost center.
3. **Reimbursement flow** — Screenshot the document upload step, then the AI's extracted line-item analysis.
4. **Trip history panel** — Show the categorized trip list (upcoming / in-progress / past) with trip IDs.
5. **Architecture diagram** — Use the `architecture.svg` included in this repo.

### Screen Recording Tips

| Clip | Duration | What to Show |
|---|---|---|
| Full voice booking | ~45s | Speak a flight request → confirmation → done |
| Reimbursement upload | ~30s | Upload receipt → AI response → submit |
| System overview | ~20s | Pan through the architecture diagram |

**Recommended tools:**
- [Loom](https://loom.com) — Free, shareable, great for portfolio
- [OBS Studio](https://obsproject.com) — Full control, local recording
- [Kap](https://getkap.co) — macOS GIF/MP4 export

**For GIFs:** Use [Gifski](https://gif.ski) or export from Kap. Ideal size: 800×500px, under 5MB.

---

## 🌐 Deployment Options

Since VoxTrail uses WebSockets + Redis + environment secrets, serverless platforms like Vercel won't work directly. Recommended free-tier options:

| Platform | Notes |
|---|---|
| **Google Cloud Run** | Ideal — native Gemini integration, WebSocket support, scales to zero |
| **Railway** | Easy Redis + FastAPI deploy, generous free tier |
| **Render** | Free tier supports persistent services + Redis add-on |

> 💡 The project already contains Cloud Run origins in CORS config (`asia-south1.run.app`), so Cloud Run is the natural deployment target.

**Minimum deploy checklist:**
- [ ] Set all environment variables in your platform's secret manager
- [ ] Provision a Redis instance (Railway Redis, Upstash, or Cloud Memorystore)
- [ ] Build Docker image: `docker build -t VoxTrail .`
- [ ] Configure WebSocket idle timeout > 60s (Cloud Run: `--timeout 300`)

---

## 🗺️ Roadmap

- [ ] Frontend UI (React voice client with waveform visualization)
- [ ] `.env.example` template
- [ ] `requirements.txt` with pinned versions
- [ ] Docker Compose for local full-stack development
- [ ] Unit tests for agent routing and tool delegates
- [ ] Support for multi-city itineraries
- [ ] Hotel and car rental booking agents

---

## 🤝 Contributing

Pull requests are welcome. For major changes, please open an issue first.

```bash
# Lint
ruff check .

# Format
black .
```

---

## 📄 License

MIT © 2025 — Built with ❤️ and a lot of voice commands.

---

*Built using [Google Agent Development Kit](https://ai.google.dev/adk), [FastAPI](https://fastapi.tiangolo.com), and [Gemini Live](https://ai.google.dev/gemini-api/docs/live).*
