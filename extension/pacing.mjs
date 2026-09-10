export const defaultTiming={minSeconds:3,maxSeconds:5,restEvery:10,restSeconds:60};

export function validateTiming(settings){
 const s={...defaultTiming,...settings};
 for(const [key,label,max] of [['minSeconds','最小间隔',3600],['maxSeconds','最大间隔',3600],['restEvery','每段操作次数',200],['restSeconds','休息时长',3600]]){
  if(!Number.isInteger(s[key])||s[key]<1||s[key]>max)throw Error(`${label}需为 1–${max} 的整数`);
 }
 if(s.minSeconds>s.maxSeconds)throw Error('最小间隔不能大于最大间隔');
 return s;
}

// Persist the deadline and segment count so pausing/reopening cannot skip a rest.
export function createPacer(settings,state,{now=Date.now,random=Math.random,sleep=ms=>new Promise(r=>setTimeout(r,ms)),stopped=()=>false,onTick=()=>{}}={}){
 const s=validateTiming(settings);
 return {
  recordAttempt(){
   state.segmentReads=(state.segmentReads||0)+1;
   const interval=s.minSeconds+Math.floor(random()*(s.maxSeconds-s.minSeconds+1));
   state.phase=state.segmentReads>=s.restEvery?'rest':'interval';
   const seconds=state.phase==='rest'?Math.max(interval,s.restSeconds):interval;
   if(state.phase==='rest')state.segmentReads=0;
   state.dueAt=now()+seconds*1000;
  },
  async wait(){
   let lastSeconds;
   while(!stopped()){
    const remaining=(state.dueAt||0)-now();if(remaining<=0)return;
    const seconds=Math.ceil(remaining/1000);
    if(seconds!==lastSeconds){onTick(state.phase,seconds);lastSeconds=seconds;}
    await sleep(Math.min(250,remaining));
   }
  }
 };
}
