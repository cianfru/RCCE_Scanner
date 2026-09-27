import test from "node:test";
import assert from "node:assert/strict";
import {executeAndJournal} from "./executionOutcome.js";
test("a journal transport failure preserves confirmed exchange success",async()=>{
 let orders=0; const execution={oid:42,avgPx:100};
 const r=await executeAndJournal(async()=>{orders++;return execution;},async()=>{throw new Error("offline");});
 assert.equal(orders,1); assert.equal(r.execution,execution);assert.equal(r.journalPending,true);
});
test("journal HTTP rejection is pending, not synced",async()=>{
 const r=await executeAndJournal(async()=>({oid:42}),async()=>({ok:false,status:503}));assert.equal(r.journalPending,true);
});
test("exchange rejection never attempts journaling",async()=>{
 let logged=false;await assert.rejects(executeAndJournal(async()=>{throw new Error("rejected");},async()=>{logged=true;}),/rejected/);assert.equal(logged,false);
});
test("both successful stages return a synced outcome",async()=>{
 assert.equal((await executeAndJournal(async()=>({oid:42}),async()=>({ok:true}))).journalPending,false);
});
