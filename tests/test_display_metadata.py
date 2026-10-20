"""Display-only identity/provenance regressions; no forecast generation or capture."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from multisport_lab import display_metadata as display
from multisport_lab.integrity import IntegrityError,canonical,digest,load_json
from multisport_lab.publication import build_site,read_manifest,research_nba

ROOT=Path(__file__).resolve().parents[1]


def reseal(value,key):
    value[key]=digest({k:v for k,v in value.items() if k!=key})
    return value


class DisplayMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.now=datetime.now(timezone.utc)
        cls.catalog=load_json(ROOT/display.CATALOG_PATH)
        cls.sports=[research_nba(ROOT,now=cls.now)]

    def test_all_six_display_identities_and_three_historical_matchups_match_retained_records(self):
        display.validate_catalog(self.catalog,now=self.now)
        display.validate_targets(self.catalog,self.sports)
        names={r['player_id']:r['display_name'] for r in self.catalog['players']}
        self.assertEqual(names,{'2991070':'Jerami Grant','2991350':'Alex Caruso','2489663':'Kelly Olynyk',
            '2583632':"Royce O'Neale",'1966':'LeBron James','2960236':'Maxi Kleber'})
        forecasts=self.sports[0]['forecasts']
        self.assertEqual({r['player_id'] for r in forecasts},set(names))
        self.assertEqual(len(self.catalog['events']),3)
        self.assertEqual(len(self.catalog['appearances']),6)
        # The name lookup never replaces the producer's original identity text.
        self.assertEqual(next(r for r in forecasts if r['player_id']=='2583632')['player_label'],'ESPN player 2583632')

    def test_checksum_consistent_wrong_name_namespace_membership_and_source_clock_reject(self):
        for mutate in (
            lambda c:c['players'][0].update(display_name='Wrong player'),
            lambda c:c['players'][0].update(id_namespace='nba'),
            lambda c:c['appearances'][0].update(team_id='25',opponent_id='22'),
            lambda c:c['events'][0].update(event_starts_at='2025-11-24T00:00:00.000001Z'),
            lambda c:c['sources'][0].update(observed_at='2099-01-01T00:00:00.000000Z'),
            lambda c:c['sources'][0].update(http_status=True),
            lambda c:c['players'][0].update(source_ids=['missing']),
        ):
            cat=deepcopy(self.catalog);mutate(cat);reseal(cat,'catalog_id')
            with self.assertRaises(IntegrityError):display.validate_catalog(cat,now=self.now)
        wrong=deepcopy(self.sports);wrong[0]['forecasts'][0]['team_id']='other'
        with self.assertRaises(IntegrityError):display.validate_targets(self.catalog,wrong)

    def test_source_bytes_are_crosschecked_not_just_self_rehashed_catalog_facts(self):
        source=deepcopy(self.catalog['sources'][0]);facts=source['facts']
        body={'header':{'id':source['event_id'],'uid':'s:40~l:46~e:'+source['event_id'],
            'competitions':[{'id':source['event_id'],'date':facts['event_starts_at'],'status':{'type':{'completed':True,'state':'post'}},
                'competitors':[{'homeAway':t['home_away'],'team':{'id':t['team_id'],'displayName':t['display_name'],'abbreviation':t['abbreviation']}} for t in facts['teams']]}]},
            'boxscore':{'players':[{'team':{'id':t['team_id']},'statistics':[{'athletes':[{'athlete':{'id':p['player_id'],'displayName':p['display_name']}} for p in facts['players'] if p['team_id']==t['team_id']]}]} for t in facts['teams']]}}
        player_team_order=list(dict.fromkeys(p['team_id'] for p in facts['players']))
        body['boxscore']['players'].sort(key=lambda r:player_team_order.index(r['team']['id']))
        raw=canonical(body);source.update(raw_bytes=len(raw),raw_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual(display.verify_archived_source(raw,source)['verified_players'],2)
        source['facts']['players'][0]['display_name']='A self-rehashed false label'
        with self.assertRaisesRegex(IntegrityError,'excerpt'):display.verify_archived_source(raw,source)

    def test_separate_clocks_and_counts_do_not_promote_name_verification_or_reconstructions(self):
        asset=display.make_asset(ROOT,self.sports,now=self.now)
        status=asset['status'];capture=status['latest_retained_input_capture']
        self.assertEqual(status['counts'],{'forecasts':6,'reconstructed_forecasts':6,'captured_forecasts':0,'upcoming_forecasts':0,'forecast_grades':6,'offers':0,'qualified_tickets':0})
        self.assertEqual(capture['observed_at'],'2026-10-20T01:51:55.889290Z')
        self.assertLess(capture['observed_at'],self.catalog['verified_at'])
        self.assertLess(capture['observed_at'],capture['imported_at'])
        self.assertIsNone(status['last_genuine_issued_at'])
        for mutation in (lambda a:a['status']['counts'].update(upcoming_forecasts=6),lambda a:a['status'].update(last_genuine_issued_at=self.sports[0]['forecasts'][0]['issued_at']),lambda a:a['status']['latest_retained_input_capture'].update(meaning='TIMELY_ISSUANCE')):
            bad=deepcopy(asset);mutation(bad);reseal(bad,'metadata_id')
            with self.assertRaises(IntegrityError):display.validate_asset(bad,self.sports,now=self.now)

    def test_manifest_four_metadata_is_separate_and_failed_update_retains_older_clocks(self):
        with tempfile.TemporaryDirectory() as name:
            base=Path(name);output=base/'site'
            first=build_site(ROOT,output,build_commit='a'*40,now=self.now)
            self.assertEqual(first['schema_version'],4)
            self.assertIsNone(first['display_error'])
            old=first['display'];before=(output/'data'/old['path']).read_bytes()
            from unittest.mock import patch
            with patch('multisport_lab.display_metadata.make_asset',side_effect=IntegrityError('private body must not leak')):
                later=build_site(ROOT,output,build_commit='b'*40,now=self.now+timedelta(seconds=1))
            self.assertTrue(later['display']['retained'])
            self.assertEqual(later['display']['generated_at'],old['generated_at'])
            self.assertEqual((output/'data'/old['path']).read_bytes(),before)
            self.assertNotIn('private body',canonical(later).decode())
            self.assertEqual(read_manifest(output/'data',now=self.now+timedelta(seconds=1)),later)
            self.assertEqual(len(load_json(output/'data'/later['sports'][0]['path'])['forecasts']),6)

    def test_corrupt_optional_previous_metadata_cannot_block_valid_sport_refresh(self):
        with tempfile.TemporaryDirectory() as name:
            output=Path(name)/'site'
            first=build_site(ROOT,output,build_commit='a'*40,now=self.now)
            for broken in ({**first['display'],'path':'../outside.json'}, {**first['display'],'status':'QUALIFIED'}):
                bad=deepcopy(first);bad['display']=broken;reseal(bad,'snapshot_id')
                (output/'data/manifest.json').write_bytes(canonical(bad))
                with self.assertRaises(IntegrityError):read_manifest(output/'data',now=self.now)
                later=build_site(ROOT,output,build_commit='b'*40,now=self.now+timedelta(seconds=1))
                self.assertIsNone(later['display_error'])
                self.assertEqual(len(load_json(output/'data'/later['sports'][0]['path'])['forecasts']),6)
            # Changed bytes also fail strict upload/readback but allow safe refresh.
            (output/'data'/later['display']['path']).write_bytes(b'{}')
            refreshed=build_site(ROOT,output,build_commit='c'*40,now=self.now+timedelta(seconds=2))
            self.assertIsNone(refreshed['display_error'])
            self.assertIsNotNone(refreshed['display'])

    def test_failed_initial_metadata_update_keeps_valid_forecasts_and_names_failure_explicit(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as name,patch('multisport_lab.display_metadata.make_asset',side_effect=IntegrityError('bad mapping')):
            result=build_site(ROOT,Path(name)/'site',build_commit='a'*40,now=self.now)
            self.assertIsNone(result['display']);self.assertTrue(result['display_error'])
            self.assertEqual(len(load_json(Path(name)/'site/data'/result['sports'][0]['path'])['forecasts']),6)

    def test_synthetic_future_research_publishes_without_prices_and_ages_into_history(self):
        # Wire/export controls only. No source capture or ledger admission occurs.
        from test_publication import PublicationTests
        from unittest.mock import patch
        future=PublicationTests.prospective_fixture(self,self.sports[0])
        forecasts=deepcopy(self.sports[0]['forecasts'])+[future]
        with tempfile.TemporaryDirectory() as name:
            output=Path(name)/'site'
            for elapsed,expected_upcoming in ((timedelta(0),1),(timedelta(hours=2),0)):
                now=datetime.now(timezone.utc)+elapsed
                with patch('multisport_lab.ledger.Ledger.iter_active_forecasts',return_value=iter(forecasts)):
                    manifest=build_site(ROOT,output,build_commit='a'*40,now=now)
                sport=load_json(output/'data'/manifest['sports'][0]['path'])
                asset=display.read_asset(output/'data',manifest['display'],[sport],now=now)
                self.assertEqual(sport['forecasts'][-1],future)
                self.assertEqual(asset['status']['counts']['upcoming_forecasts'],expected_upcoming)
                self.assertEqual(asset['status']['last_genuine_issued_at'],future['issued_at'])
                self.assertEqual((sport['offers'],sport['candidates'],sport['tickets']),([],[],[]))
                self.assertEqual(len(sport['performance']),6)  # Still pending for the invented future target.

    def test_original_nineteen_record_bytes_are_unchanged(self):
        proof=load_json(ROOT/'evidence/display/2026-10-20-historical-metadata-verification.json')
        self.assertEqual(len(proof['record_inventory']),19)
        for row in proof['record_inventory']:
            self.assertEqual(hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest(),row['sha256'])

    @unittest.skipUnless(shutil.which('node'),'Node required for browser contract readback')
    def test_python_asset_recovers_all_six_targets_through_javascript_loader(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)/'site';build_site(ROOT,root,build_commit='a'*40,now=self.now)
            code="""import{readFile}from'node:fs/promises';import{webcrypto}from'node:crypto';import{loadSnapshot}from'./web/snapshot.mjs';import{displayTarget}from'./web/display.mjs';
const root=process.argv[1];const snapshot=await loadSnapshot(async p=>new Response(await readFile(root+'/'+p.slice(2))),webcrypto);
if(snapshot.errors.length||snapshot.displayError||!snapshot.display)throw new Error(JSON.stringify(snapshot.errors)+' '+snapshot.displayError);
const rows=snapshot.sports.flatMap(s=>s.forecasts);if(rows.length!==6||new Set(rows.map(r=>displayTarget(r,snapshot.display).playerName)).size!==6)throw new Error('Display coverage lost');
const royce=rows.find(r=>r.player_id==='2583632');if(displayTarget(royce,snapshot.display).playerName!==\"Royce O'Neale\"||royce.player_label!=='ESPN player 2583632')throw new Error('Original label changed');console.log('six immutable forecasts + source-backed labels + separate clocks verified');"""
            result=subprocess.run(['node','--input-type=module','-e',code,str(root)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_invalid_catalog_still_rejects_under_optimized_python(self):
        code="from multisport_lab.display_metadata import validate_catalog;from multisport_lab.integrity import IntegrityError\ntry:validate_catalog({},now='2026-10-20T23:00:00.000000Z')\nexcept IntegrityError:print('rejected')\nelse:raise RuntimeError('invalid catalog admitted')"
        result=subprocess.run([sys.executable,'-O','-c',code],cwd=ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'rejected')
