#!/usr/bin/env node
// Render prepared local review JSON. No fetches, scripts, public assets or keys.
import {constants} from 'node:fs';
import * as fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {renderLocalOfferReview} from '../web/local-offer-review.mjs';

const MAX_REVIEW_BYTES = 256 * 1024;
const MAX_HTML_BYTES = 2 * 1024 * 1024;
const require = (condition,message) => {if (!condition) throw new Error(message);};

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

async function main() {
  const args = process.argv.slice(2);
  if (args.length === 1 && ['--help','-h'].includes(args[0])) {
    process.stdout.write('Usage: node scripts/render_local_offer_review.mjs REVIEW.json .local-data/PREVIEW.html\nRenders validated local research observations only; no network or public publication.\n');
    return;
  }
  require(args.length === 2,'Expected REVIEW.json and output HTML path. Use --help for usage.');
  const cwd = await fs.realpath(process.cwd());
  const input = path.resolve(cwd,args[0]), output = path.resolve(cwd,args[1]);
  const raw = await boundedRegularFile(input,MAX_REVIEW_BYTES);
  let review;
  try {review = JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));}
  catch {throw new Error('Review input is not valid UTF-8 JSON.');}
  const rendered = renderLocalOfferReview(review);
  const cssFile = fileURLToPath(new URL('../web/local-offer-review.css',import.meta.url));
  const css = new TextDecoder('utf-8',{fatal:true}).decode(await boundedRegularFile(cssFile,MAX_REVIEW_BYTES))
    .replace(/<\/style/gi,'<\\/style');
  const html = Buffer.from(`<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'"><title>NBA local source review — unpublished</title><style>${css}</style></head><body>${rendered}</body></html>\n`,'utf8');
  require(html.length <= MAX_HTML_BYTES,'Rendered HTML exceeds its byte limit.');
  await privateOutputParent(cwd,output);
  const created = await createIdenticalOnly(output,html);
  process.stdout.write(JSON.stringify({output,created,bytes:html.length,scope:'LOCAL_REVIEW_ONLY',public_admission:false,ticket_eligibility:false})+'\n');
}

main().catch(error => {process.stderr.write('Local preview render failed: '+error.message+'\n');process.exitCode=1;});
