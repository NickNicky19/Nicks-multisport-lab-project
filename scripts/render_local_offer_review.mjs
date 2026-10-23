#!/usr/bin/env node
// Render prepared local review JSON. No fetches, scripts, public assets or keys.
import {constants} from 'node:fs';
import * as fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {webcrypto} from 'node:crypto';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {renderLocalOfferReview} from '../web/local-offer-review.mjs';
import {PLAYER_LINE_REVIEW_SCHEMA,renderPlayerLineReview,verifyPlayerLineReviewHash} from '../web/player-line-review.mjs';
import {ENRICHMENT_SOURCE_URLS,renderEnrichedPlayerLineReview,verifyPlayerLineEnrichmentSources} from '../web/player-line-enrichment.mjs';
import {MOVIODDS_REVIEW_SCHEMA,renderMovioddsReview,verifyMovioddsReviewHash} from '../web/moviodds-review.mjs';
import {NATIVE_OFFER_SCHEMA,renderNativeOffer,verifyNativeOfferHash} from '../web/native-offer.mjs';

const MAX_REVIEW_BYTES = 256 * 1024;
const MAX_HTML_BYTES = 2 * 1024 * 1024;
const require = (condition,message) => {if (!condition) throw new Error(message);};
const execFileAsync=promisify(execFile);

async function replayMovioddsOriginals(input,review) {
  require(path.basename(input)==='review.json','MoviOdds replay requires the package original review.json.');
  let result;
  try {
    result=await execFileAsync('python3',['-O','-m','multisport_lab.moviodds_offer','--verify',path.dirname(input)],{
      cwd:fileURLToPath(new URL('../',import.meta.url)),shell:false,timeout:30000,maxBuffer:128*1024,encoding:'utf8',
      env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
  } catch(error) {
    const reason=typeof error.stderr==='string'?error.stderr.trim().split('\n').at(-1).slice(0,800):'offline verifier did not complete';
    throw new Error('MoviOdds original-source replay failed: '+reason);
  }
  const replay=JSON.parse(result.stdout);
  require(replay.schema_version==='nba-moviodds-replay-v1'&&replay.review_id===review.review_id
    &&replay.originals_replayed===7&&replay.public_admission===false&&replay.durable_remote_archive_verified===false,
    'Independent replay does not acknowledge this exact private review.');
}

async function replayNativeOriginals(input,offer){
  const verifier=`import sys,json
from datetime import datetime,timezone
from pathlib import Path
from multisport_lab.integrity import _bounded_bytes,_decode,IntegrityError
from multisport_lab.moviodds_offer import verify_package,load_assets
from multisport_lab.native_offer import replay_native_offer
p=Path(sys.argv[1]);now=datetime.now(timezone.utc)
package=verify_package(p.parent,now=now)
o=_decode(_bounded_bytes(p,32768))
if package['review_id']!=o['original_review_id']:raise IntegrityError('Native offer does not reference the original package intent')
print(json.dumps(replay_native_offer(o,load_assets(p.parent),now=now),sort_keys=True))`;
  let result;
  try{result=await execFileAsync('python3',['-O','-c',verifier,input],{
    cwd:fileURLToPath(new URL('../',import.meta.url)),shell:false,timeout:30000,maxBuffer:128*1024,encoding:'utf8',
    env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
  }catch(error){
    const reason=typeof error.stderr==='string'?error.stderr.trim().split('\n').at(-1).slice(0,800):'offline verifier did not complete';
    throw new Error('Native offer original-source replay failed: '+reason);
  }
  const replay=JSON.parse(result.stdout);
  require(replay.schema_version==='nba-native-offer-replay-v1'&&replay.offer_id===offer.offer_id
    &&replay.original_review_id===offer.original_review_id&&replay.originals_replayed===7
    &&replay.public_admission===false&&replay.ticket_eligible===false,'Independent original replay does not acknowledge this native offer.');
}

async function boundedRegularFile(filename,limit) {
  const before = await fs.lstat(filename);
  require(before.isFile() && !before.isSymbolicLink(),'Input must be a regular file, not a symlink.');
  const handle = await fs.open(filename,constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
  try {
    const opened = await handle.stat();
    require(opened.isFile() && opened.ino === before.ino && opened.dev === before.dev
      && opened.size <= limit,'Input identity changed or byte limit exceeded.');
    const buffer = Buffer.alloc(limit+1);
    let offset = 0;
    while (offset < buffer.length) {
      const {bytesRead} = await handle.read(buffer,offset,buffer.length-offset,offset);
      if (bytesRead === 0) break;
      offset += bytesRead;
    }
    require(offset <= limit,'Input exceeds its byte limit.');
    return buffer.subarray(0,offset);
  } finally {await handle.close();}
}

async function privateOutputParent(cwd,filename) {
  const allowed = path.join(cwd,'.local-data');
  require(filename.startsWith(allowed+path.sep),'Output must remain under cwd/.local-data.');
  let directory = cwd;
  for (const component of path.relative(cwd,path.dirname(filename)).split(path.sep)) {
    directory = path.join(directory,component);
    try {await fs.mkdir(directory,{mode:0o700});}
    catch (error) {if (error.code !== 'EEXIST') throw error;}
    const info = await fs.lstat(directory);
    require(info.isDirectory() && !info.isSymbolicLink(),'Output ancestors must be directories, not symlinks.');
    require(await fs.realpath(directory) === directory,'Output parent escapes local storage.');
  }
  return directory;
}

async function createIdenticalOnly(filename,content) {
  const temporaryDirectory = await fs.mkdtemp(path.join(path.dirname(filename),'.local-offer-render-'));
  const temporary = path.join(temporaryDirectory,'review.html');
  try {
    const handle = await fs.open(temporary,constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL,0o600);
    try {await handle.writeFile(content); await handle.sync();}
    finally {await handle.close();}
    try {await fs.link(temporary,filename); return true;}
    catch (error) {
      if (error.code !== 'EEXIST') throw error;
      const existing = await boundedRegularFile(filename,MAX_HTML_BYTES);
      require(existing.equals(content),'Conflicting output exists; choose a new local filename.');
      return false;
    }
  } finally {await fs.rm(temporaryDirectory,{recursive:true,force:true});}
}

export async function renderPreparedLocalReview(inputFilename,outputFilename,{cwd:requestedCwd=process.cwd(),enrichmentFilename=null}={}) {
  const cwd = await fs.realpath(requestedCwd);
  const input = path.resolve(cwd,inputFilename), output = path.resolve(cwd,outputFilename);
  const raw = await boundedRegularFile(input,MAX_REVIEW_BYTES);
  let review;
  try {review = JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));}
  catch {throw new Error('Review input is not valid UTF-8 JSON.');}
  let rendered;
  if (review?.schema_version === NATIVE_OFFER_SCHEMA) {
    require(enrichmentFilename===null,'Native Boolean offers retain their own original source bindings.');
    await verifyNativeOfferHash(review,webcrypto);
    await replayNativeOriginals(input,review);
    rendered=renderNativeOffer(review);
  } else if (review?.schema_version === MOVIODDS_REVIEW_SCHEMA) {
    require(enrichmentFilename===null,'MoviOdds has its own retained evidence; no Sleeper enrichment applies.');
    await verifyMovioddsReviewHash(review,webcrypto);
    await replayMovioddsOriginals(input,review);
    rendered=renderMovioddsReview(review);
  } else if (review?.schema_version === PLAYER_LINE_REVIEW_SCHEMA) {
    await verifyPlayerLineReviewHash(review,webcrypto);
    if (enrichmentFilename !== null) {
      const filename=path.resolve(cwd,enrichmentFilename),directory=path.dirname(filename);
      const enrichment=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(await boundedRegularFile(filename,MAX_REVIEW_BYTES)));
      const assets={};
      for(const key of Object.keys(ENRICHMENT_SOURCE_URLS))assets[key]={
        raw:await boundedRegularFile(path.join(directory,key+'.body'),8*1024*1024),
        metadataRaw:await boundedRegularFile(path.join(directory,key+'.metadata.json'),MAX_REVIEW_BYTES)};
      const board=await boundedRegularFile(path.join(path.dirname(input),'source.body'),8*1024*1024);
      await verifyPlayerLineEnrichmentSources(enrichment,review,assets,board,webcrypto);
      rendered=renderEnrichedPlayerLineReview(review,enrichment);
    } else rendered = renderPlayerLineReview(review);
  } else {
    require(enrichmentFilename===null,'Enrichment requires an original private player-line review.');
    rendered = renderLocalOfferReview(review);
  }
  const cssFile = fileURLToPath(new URL('../web/local-offer-review.css',import.meta.url));
  const css = new TextDecoder('utf-8',{fatal:true}).decode(await boundedRegularFile(cssFile,MAX_REVIEW_BYTES))
    .replace(/<\/style/gi,'<\\/style');
  const html = Buffer.from(`<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'"><title>NBA local source review — unpublished</title><style>${css}</style></head><body>${rendered}</body></html>\n`,'utf8');
  require(html.length <= MAX_HTML_BYTES,'Rendered HTML exceeds its byte limit.');
  await privateOutputParent(cwd,output);
  const created = await createIdenticalOnly(output,html);
  return {output,created,bytes:html.length,scope:'LOCAL_REVIEW_ONLY',public_admission:false,ticket_eligibility:false};
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length === 1 && ['--help','-h'].includes(args[0])) {
    process.stdout.write('Usage: node scripts/render_local_offer_review.mjs REVIEW.json .local-data/PREVIEW.html [--enrichment COMPANION/enrichment.json]\nRenders validated local research observations only; optional enrichment replays retained originals. No network or public publication.\n');
    return;
  }
  require(args.length===2||(args.length===4&&args[2]==='--enrichment'),'Expected REVIEW.json, output HTML path and optional --enrichment file. Use --help for usage.');
  process.stdout.write(JSON.stringify(await renderPreparedLocalReview(args[0],args[1],{enrichmentFilename:args.length===4?args[3]:null}))+'\n');
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  main().catch(error => {process.stderr.write('Local preview render failed: '+error.message+'\n');process.exitCode=1;});
