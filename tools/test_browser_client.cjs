// Transport tests against a fetch stub. No real backend or authentication is tested.
const {test, afterEach} = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const sdk = require(process.env.LEDGER_SDK_MODULE || path.resolve(__dirname,'../.contract-sdk-build/client.generated.js'));
const originalFetch=globalThis.fetch;
afterEach(()=>{globalThis.fetch=originalFetch;sdk.setApiBaseUrl('');});
const json=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}});

test('query values are encoded and cookies requested',async()=>{
  globalThis.fetch=async(url,init)=>{
    assert.equal(url,'/api/transactions?date_from=2026-11-01&page=2&page_size=50');
    assert.equal(init.credentials,'include');assert.equal(init.method,'GET');
    return json({items:[],total:0,page:2,page_size:50});
  };
  const result=await sdk.listTransactions({query:{date_from:'2026-11-01',page:2,page_size:50}});
  assert.equal(result.page,2);
});
test('mutating call requires CSRF before a network request',async()=>{
  globalThis.fetch=async()=>{throw new Error('must not call fetch');};
  await assert.rejects(()=>sdk.logout({}),/CSRF token required/);
});
test('multipart uses FormData and leaves boundary to browser',async()=>{
  globalThis.fetch=async(url,init)=>{
    assert.equal(url,'/api/imports');assert.ok(init.body instanceof FormData);
    assert.equal(init.body.get('source'),'wechat');assert.ok(init.body.get('file') instanceof Blob);
    assert.equal(init.headers['Content-Type'],undefined);assert.equal(init.headers['X-CSRF-Token'],'demo-csrf');
    return json({id:'batch_demo'},202);
  };
  assert.equal((await sdk.createImport({body:{source:'wechat',ingestion_method:'file',file:new Blob(['synthetic'])}},'demo-csrf')).id,'batch_demo');
});
test('204 response does not parse JSON',async()=>{
  globalThis.fetch=async()=>new Response(null,{status:204});
  assert.equal(await sdk.logout({},'demo-csrf'),undefined);
});
test('version conflict preserves structured error and HTTP status',async()=>{
  globalThis.fetch=async()=>json({error:{code:'VERSION_CONFLICT',message:'changed',details:{current_version:2}}},409);
  await assert.rejects(()=>sdk.patchTransaction({path:{id:'t1'},body:{expected_version:1,changes:{category:'dining'}}},'demo-csrf'),error=>error instanceof sdk.ApiError && error.status===409 && error.payload.error.details.current_version===2);
});
test('downloads return Blob instead of parsing PDF as JSON',async()=>{
  globalThis.fetch=async()=>new Response(new Uint8Array([37,80,68,70]),{status:200,headers:{'Content-Type':'application/pdf'}});
  const result=await sdk.exportMonthlyPdf({query:{month:'2026-11'}});
  assert.ok(result instanceof Blob);assert.equal(await result.text(),'%PDF');
});
test('unexpected successful status is a contract failure',async()=>{
  globalThis.fetch=async()=>json({status:'ok'},201);
  await assert.rejects(()=>sdk.health({}),error=>error instanceof sdk.ApiError && error.payload.error.code==='UNEXPECTED_STATUS');
});
test('login sends JSON but no pre-login CSRF header',async()=>{
  globalThis.fetch=async(url,init)=>{
    assert.equal(url,'/api/auth/login');assert.equal(init.headers['Content-Type'],'application/json');
    assert.equal(init.headers['X-CSRF-Token'],undefined);assert.equal(JSON.parse(init.body).username,'demo_a');
    return json({user:{id:'u1',username:'demo_a'},csrf_token:'demo-csrf'});
  };
  assert.equal((await sdk.login({body:{username:'demo_a',password:'synthetic'}})).csrf_token,'demo-csrf');
});
test('path identifiers are encoded and invalid error bodies are handled',async()=>{
  globalThis.fetch=async(url)=>{assert.equal(url,'/api/imports/batch%2F1');return new Response('<html>bad gateway</html>',{status:503});};
  await assert.rejects(()=>sdk.getImport({path:{id:'batch/1'}}),error=>error instanceof sdk.ApiError && error.payload.error.code==='INVALID_ERROR_RESPONSE');
});
