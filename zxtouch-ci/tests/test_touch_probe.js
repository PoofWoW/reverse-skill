'use strict';
// Synthetic DOM events test the receiver UI/log logic, never iOS hardware delivery.
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const elements = Object.fromEntries(['stage','status','tail','reset','export'].map(id=>[id,{id,tagName:'CANVAS',listeners:{},options:{},addEventListener(type,fn,options){this.listeners[type]=fn;this.options[type]=options;}}]));
elements.stage.getContext=()=>({scale(){},beginPath(){},arc(){},fill(){},fillText(){}});
elements.stage.getBoundingClientRect=()=>({left:0,top:0,width:390,height:400});
let exported;
const sandbox={document:{querySelector:s=>elements[s.slice(1)],createElement:()=>({click(){}})},
  window:{devicePixelRatio:3,addEventListener(){}},navigator:{userAgent:'synthetic-host-test'},
  screen:{width:390,height:844},devicePixelRatio:3,performance:{now:()=>123},
  URL:{createObjectURL:blob=>{exported=JSON.parse(blob.data[0]);return 'blob:test';},revokeObjectURL(){}},
  Blob:class{constructor(data){this.data=data;}},setTimeout(){},alert(){throw Error('Unexpected alert');},console};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(__dirname+'/../diagnostics/touch-probe.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1],sandbox);
const finger=(id,x)=>({identifier:id,clientX:x,clientY:200,target:elements.stage});
const a=finger(11,70),b=finger(22,230);
const touch=(type,touches,changed)=>elements.stage.listeners[type]({preventDefault(){},touches,targetTouches:touches,changedTouches:changed,timeStamp:1,isTrusted:false});
touch('touchstart',[a],[a]);
elements.stage.listeners.pointerdown({pointerId:99,isPrimary:false,pointerType:'touch',clientX:230,clientY:200});
assert.match(elements.status.textContent,/touches=1/); // pointer marker must not inflate TouchEvent count
assert.strictEqual(elements.stage.options.touchstart.passive,false);
touch('touchstart',[a,b],[b]);assert.match(elements.status.textContent,/touches=2/);
a.clientX=90;touch('touchmove',[a,b],[a]);
touch('touchend',[b],[a]);assert.match(elements.status.textContent,/touches=1/);
touch('touchcancel',[],[b]);assert.match(elements.status.textContent,/touches=0/);
elements.export.onclick();
assert.strictEqual(exported.peak,2);assert.strictEqual(exported.rows.length,6);
assert.strictEqual(exported.rows[2].touches.length,2);
assert.strictEqual(exported.rows[2].changedTouches.length,1);
assert.strictEqual(exported.rows[4].touches[0].id,22);
assert.strictEqual(exported.rows[5].type,'touchcancel');
assert.strictEqual(exported.rows[5].touches.length,0);
console.log('receiver DOM logic passed (synthetic events only; not device validation)');
