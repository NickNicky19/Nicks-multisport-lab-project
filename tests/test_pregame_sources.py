"""Concrete source identity/clock/cohort and lossless-input regressions."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from multisport_lab.integrity import canonical, digest, load_json, stamp, utc, write_receipt
from multisport_lab.nba_data import COUNT_FIELDS, NBAPlayerGame
from multisport_lab import pregame_sources as src


NOW=datetime(2026,10,20,1,0,tzinfo=timezone.utc)


def event_fixture():
    competitors=[{'id':'8','homeAway':'home','team':{'id':'8'}},
                 {'id':'2','homeAway':'away','team':{'id':'2'}}]
    status={'type':{'name':'STATUS_SCHEDULED','state':'pre','completed':False}}
    competition={'id':'401909088','date':'2026-10-20T19:00Z','competitors':competitors,
                 'status':status,'timeValid':True}
    event={'id':'401909088','uid':'s:40~l:46~e:401909088','date':'2026-10-20T19:00Z','timeValid':True,'season':{'year':2027,'type':2},
           'status':status,'competitions':[competition]}
    summary={'header':deepcopy(event)}
    return {'leagues':[{'id':'46','abbreviation':'NBA'}],'events':[event]},summary


def roster_fixture(team, ids):
    return {'team':{'id':team},'season':{'year':2027,'type':2},
            'athletes':[{'id':pid,'displayName':'Player '+pid,'status':{'type':'active'}} for pid in ids]}


def tiny_history():
    counts={field:0 for field in COUNT_FIELDS}
    counts.update(points=5,fgm=2,fga=4,fg2m=1,fg3m=1,fg3a=2,ftm=0,fta=0,oreb=1,dreb=2,rebounds=3)
    return [NBAPlayerGame(id_namespace='espn',event_id='401811041',player_id='3195',team_id='2',opponent_id='8',
                         season_ending_year=2026,season_type='2',event_start=NOW-timedelta(days=200),
                         participation='APPEARED',minutes=20.0,minutes_precision='rounded_whole_minutes',
                         final_status='FINAL',final_periods=4,**counts)]


def provenance(rows):
    receipt_path=Path(__file__).resolve().parents[1]/'evidence/data/2026-10-19-source-receipts.json'
    sources={r['key']:r for r in load_json(receipt_path)['receipts']}
    bindings=[]
    for key in ['sdv_player_box_2026','sdv_schedule_2026']:
        r=sources[key]
        bindings.append({'source_id':key,'source_url':r['url'],'raw_sha256':r['sha256'],
                         'raw_bytes':r['bytes'],'observed_at':stamp(utc(r['observed_at'])),
                         'source_updated_at':stamp(utc(r['source_updated_at'])),
                         'source_version':'github-asset:'+str(r['github_asset_id'])})
    raw=src._panel_bytes(rows)
    return {'normalized_panel_sha256':hashlib.sha256(raw).hexdigest(),'normalized_panel_bytes':len(raw),
            'normalized_panel_rows':len(rows),'normalization_version':'nba-panel-preparation-v1',
            'source_receipts':bindings,'upstream_exclusions':load_json(receipt_path.parent/'2026-10-19-panel_preparation_summary.json')['upstream_exclusions'],'availability_semantics':'explicit test fixture',
            'source_receipts_sha256':hashlib.sha256(receipt_path.read_bytes()).hexdigest(),'cohort':'synthetic fixture',
            'current_season_history_claim':False,'history_freshness':'synthetic fixture','normalizer_source_sha256':'a'*64}


def pack_fixture():
    board,summary=event_fixture()
    event=src.normalize_event(canonical(board),canonical(summary),'401909088')
    rosters={'8':src.normalize_roster(canonical(roster_fixture('8',['11','12','13'])),'8',season_ending_year=2027),
             '2':src.normalize_roster(canonical(roster_fixture('2',['21','22','23'])),'2',season_ending_year=2027)}
    selection=src.freeze_selection(event,rosters)
    base='https://site.api.espn.com/apis/site/v2/sports/basketball/nba'
    captures=[]
    for key,url in [('scoreboard',base+'/scoreboard?dates=20261020'),('summary',base+'/summary?event=401909088'),
                    ('roster-8',base+'/teams/8/roster'),('roster-2',base+'/teams/2/roster')]:
        captures.append({'source_id':key,'source_url':url,'request_started_at':stamp(NOW-timedelta(seconds=2)),
                         'observed_at':stamp(NOW-timedelta(seconds=1)),'response_completed_at':stamp(NOW-timedelta(seconds=1)),
                         'source_updated_at':None,'source_response_generated_at':None,'raw_sha256':'b'*64,
                         'raw_bytes':100,'http_status':200,'http_date':None,'etag':None,'last_modified':None})
    rows=tiny_history(); p=provenance(rows)
    with patch.object(src,'PANEL_SHA',p['normalized_panel_sha256']):
        return src.make_pack(event,rosters,captures,selection,src.compact_history(rows),p)


class SourceIdentityTests(unittest.TestCase):
    def test_event_reconciles_and_versions_identity_start_and_teams(self):
        board,summary=event_fixture()
        original=src.normalize_event(canonical(board),canonical(summary),'401909088')
        self.assertEqual(original['home_team_id'],'8')
        self.assertEqual(len(original['event_version']),64)
        changed=deepcopy(summary);changed['header']['competitions'][0]['date']='2026-10-20T20:00Z'
        with self.assertRaisesRegex(ValueError,'start conflict'):
            src.normalize_event(canonical(board),canonical(changed),'401909088')
        changed=deepcopy(summary);changed['header']['competitions'][0]['competitors'][0]['team']['id']='3'
        with self.assertRaisesRegex(ValueError,'identity conflict'):
            src.normalize_event(canonical(board),canonical(changed),'401909088')

    def test_nonpre_duplicate_event_and_unknown_time_rejected(self):
        board,summary=event_fixture()
        board['events'].append(deepcopy(board['events'][0]))
        with self.assertRaisesRegex(ValueError,'exactly one'):
            src.normalize_event(canonical(board),canonical(summary),'401909088')
        board,summary=event_fixture();summary['header']['competitions'][0]['status']['type']['state']='in'
        with self.assertRaisesRegex(ValueError,'pregame'):
            src.normalize_event(canonical(board),canonical(summary),'401909088')
        board,summary=event_fixture();board['events'][0]['timeValid']=False;board['events'][0]['competitions'][0]['timeValid']=False
        with self.assertRaisesRegex(ValueError,'time is not explicitly valid'):
            src.normalize_event(canonical(board),canonical(summary),'401909088')
        board,summary=event_fixture();board['leagues'][0]['id']='28'
        with self.assertRaisesRegex(ValueError,'NBA league'):
            src.normalize_event(canonical(board),canonical(summary),'401909088')

    def test_roster_subject_and_active_status_and_team_conflicts(self):
        roster=roster_fixture('8',['12','11'])
        active=src.normalize_roster(canonical(roster),'8',season_ending_year=2027)
        self.assertEqual([p['player_id'] for p in active],['11','12'])
        # Missing boolean active is not fabricated; explicit status is the amended rule.
        self.assertNotIn('active',active[0])
        roster['athletes'][0]['active']=False
        with self.assertRaisesRegex(ValueError,'conflicts'):
            src.normalize_roster(canonical(roster),'8',season_ending_year=2027)
        roster=roster_fixture('8',['12','11']);roster['athletes'][0]['team']={'id':'2'}
        with self.assertRaisesRegex(ValueError,'team conflicts'):
            src.normalize_roster(canonical(roster),'8',season_ending_year=2027)
        roster=roster_fixture('8',['12','11']);del roster['athletes'][0]['status']
        with self.assertRaisesRegex(ValueError,'status is missing'):
            src.normalize_roster(canonical(roster),'8',season_ending_year=2027)

    def test_frozen_cohort_not_reselected_after_transfer_or_inactivation(self):
        board,summary=event_fixture();event=src.normalize_event(canonical(board),canonical(summary),'401909088')
        rosters={team:src.normalize_roster(canonical(roster_fixture(team,ids)),team,season_ending_year=2027)
                 for team,ids in [('8',['12','11','13']),('2',['22','21','23'])]}
        with patch.object(src,'_now',return_value=NOW):selection=src.freeze_selection(event,rosters)
        self.assertEqual([p['player_id'] for p in selection['players']],['11','12','21','22'])
        rosters['8']=rosters['8'][1:]
        with self.assertRaisesRegex(ValueError,'never reselect'):
            src.verify_selection(event,rosters,selection)


class HistoryAndBindingTests(unittest.TestCase):
    def test_compact_lossless_full_fields_and_same_row_order(self):
        rows=tiny_history();recovered=src.unpack_history(src.compact_history(rows))
        self.assertEqual(src._panel_bytes(rows),src._panel_bytes(recovered))
        self.assertEqual(recovered[0].fgm,recovered[0].fg2m+recovered[0].fg3m)

    def test_compact_rejects_contradictory_counts_and_bad_dictionary(self):
        compact=src.compact_history(tiny_history())
        compact['rows'][0][compact['columns'].index('fgm')]=7
        with self.assertRaisesRegex(ValueError,'FGM'):
            src.unpack_history(compact)
        compact=src.compact_history(tiny_history());compact['rows'][0][0]=True
        with self.assertRaisesRegex(ValueError,'index is invalid'):
            src.unpack_history(compact)

    def test_source_clock_and_panel_binding_recover_after_start(self):
        with patch.object(src,'_now',return_value=NOW):pack=pack_fixture()
        with patch.object(src,'PANEL_SHA',pack['history_provenance']['normalized_panel_sha256']),patch.object(src,'_now',return_value=NOW+timedelta(days=2)):
            with tempfile.TemporaryDirectory() as temporary:
                path=Path(temporary)/'pack.json';write_receipt(path,pack)
                recovered=src.load_pack(path)
                self.assertEqual(src.binding_view(recovered)['history_rows'],1)
                self.assertIsNone(recovered['sources'][0]['source_updated_at'])
        changed=deepcopy(pack);changed['sources'][0]['observed_at']=stamp(NOW+timedelta(seconds=1));changed['sourcepack_id']=src.sourcepack_digest(changed)
        with self.assertRaisesRegex(ValueError,'chronology'):
            src.validate_pack(changed)

    def test_recomputed_pack_checksum_cannot_relabel_original_history_clock(self):
        with patch.object(src,'_now',return_value=NOW):pack=pack_fixture()
        changed=deepcopy(pack);changed['history_provenance']['source_receipts'][0]['observed_at']=stamp(NOW-timedelta(days=2));changed['sourcepack_id']=src.sourcepack_digest(changed)
        with patch.object(src,'PANEL_SHA',pack['history_provenance']['normalized_panel_sha256']):
            with self.assertRaisesRegex(ValueError,'binding conflicts'):
                src.validate_pack(changed)
        changed=deepcopy(pack);changed['history']['rows'][0][changed['history']['columns'].index('assists')]=99;changed['sourcepack_id']=src.sourcepack_digest(changed)
        with self.assertRaisesRegex(ValueError,'panel reference'):
            src.validate_pack(changed)

    def test_durable_input_history_recovery_needs_no_raw_file_http_or_model(self):
        from multisport_lab.ledger import Ledger
        with patch.object(src,'_now',return_value=NOW):pack=pack_fixture()
        with tempfile.TemporaryDirectory() as temporary,patch.object(src,'PANEL_SHA',pack['history_provenance']['normalized_panel_sha256']):
            store=Ledger(temporary)
            reference=store.record_research_inputs(pack)
            before=canonical(pack['history'])
            with (patch('urllib.request.urlopen',side_effect=AssertionError('HTTP forbidden')),
                  patch.object(src,'rebuild_history',side_effect=AssertionError('Parquet/raw rebuild forbidden'))):
                history,provenance=src.history_from_input_record(reference.record_id,repository_root=temporary)
            self.assertEqual(canonical(history),before)
            self.assertEqual(len(history['rows']),len(pack['history']['rows']))
            self.assertEqual(provenance,pack['history_provenance'])
            self.assertEqual(src._panel_bytes(src.unpack_history(history)),src._panel_bytes(src.unpack_history(pack)))

    def test_durable_input_history_missing_corrupt_and_invalid_refs_fail(self):
        from multisport_lab.ledger import Ledger
        with patch.object(src,'_now',return_value=NOW):pack=pack_fixture()
        with tempfile.TemporaryDirectory() as temporary,patch.object(src,'PANEL_SHA',pack['history_provenance']['normalized_panel_sha256']):
            with self.assertRaisesRegex(ValueError,'SHA256'):
                src.history_from_input_record('../outside',repository_root=temporary)
            with self.assertRaises(FileNotFoundError):
                src.history_from_input_record('a'*64,repository_root=temporary)
            reference=Ledger(temporary).record_research_inputs(pack)
            path=Path(temporary)/'records'/'research_inputs'/f'{reference.record_id}.json'
            envelope=json.loads(path.read_text());envelope['payload']['data']['source_pack']['history']['rows'].pop()
            path.write_text(json.dumps(envelope))
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                src.history_from_input_record(reference.record_id,repository_root=temporary)


if __name__=='__main__':unittest.main()
