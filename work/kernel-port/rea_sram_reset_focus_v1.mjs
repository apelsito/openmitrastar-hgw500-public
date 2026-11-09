// Isolated project ARC REA; exact firmware carrier never rewritten or executed.
import fs from 'node:fs';import path from 'node:path';import {pathToFileURL} from 'node:url';import{createHash}from'node:crypto';
const root='/workspace/user-home/Desktop/MitraStar';
const lab=path.join(root,'outputs/rea/windows-arc700-static-lab-20261022T154500Z-r3');
const out=path.join(root,'outputs/rea/linux73-sram-oem-reset-rea-v1');
if(fs.existsSync(out))throw Error('Immutable evidence exists');fs.mkdirSync(out);
const m=JSON.parse(fs.readFileSync(path.join(lab,'manifest.json'),'utf8'));
const target=path.join(root,'work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/qdrv/qdrv.ko');
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const digest=hash(target);const env={...process.env,GHIDRA_INSTALL_DIR:path.resolve(root,m.ghidra),JAVA_HOME:m.java,REA_GHIDRA_LANGUAGE_ID:m.language_id,REA_GHIDRA_COMPILER_SPEC_ID:m.compiler_spec_id,REA_ANALYSIS_PROVIDER:'ghidra',REA_LOG_LEVEL:'silent'};
const load=async relative=>import(pathToFileURL(path.resolve(root,m.runtime,'dist',relative)).href);
const{parseConfig}=await load('config/parseConfig.js');const{createBinarySession}=await load('composition/binary.js');const{silentLogger}=await load('logger.js');
const c=parseConfig(env);if(!c.ok)throw Error(JSON.stringify(c.error));const session=createBinarySession(c.value,silentLogger,env);
const write=(n,v)=>fs.writeFileSync(path.join(out,n),JSON.stringify(v,null,2)+'\n',{flag:'wx'});
let error;try{const opened=await session.open(target,{providerId:'ghidra'});write('open.json',opened);if(!opened.ok)throw Error(JSON.stringify(opened.error));
 for(const name of ['hal_reset','qdrv_command_clearsram']){console.log('REA_ANALYZE '+name);const r=await session.execute('analyze_function',{procedure:name});write(name+'.json',r);console.log(JSON.stringify({function:name,ok:r.ok}));}
}catch(e){error=e.message;console.log(error);}finally{write('evidence.json',session.exportEvidenceBundle());const closed=await session.close();write('close.json',closed);write('result.json',{status:error?'REA_FOCUS_INCOMPLETE':'PASS_REA_RESET_FOCUS_WITH_LIMITS',target_sha256:digest,target_unchanged:hash(target)===digest,hardware_accessed:false,error,limits:['Project-isolated ARC decoder; original header retained.','Reset and clear functions only; not universal SRAM-writer completeness.']});}
