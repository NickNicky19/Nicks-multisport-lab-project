"""Synthetic source/selection/history risks; no source access or genuine issuance."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

from multisport_lab import pros004_inputs as inp
from multisport_lab import pregame_sources as old
from multisport_lab.integrity import IntegrityError, canonical, digest, stamp
from multisport_lab.ledger import LedgerRef
from test_pregame_sources import tiny_history, provenance

NOW = datetime(2026,10,21,22,45,tzinfo=timezone.utc)
OBSERVED = NOW-timedelta(minutes=1)
START = datetime(2026,10,22,0,30,tzinfo=timezone.utc)


def event_fixture(event_id='401900001', start=START):
    status = {'type':{'name':'STATUS_SCHEDULED','state':'pre','completed':False}}
    competition = {'id':event_id,'date':stamp(start),'timeValid':True,'status':status,
        'competitors':[{'id':'8','homeAway':'home','team':{'id':'8'}},
                       {'id':'2','homeAway':'away','team':{'id':'2'}}]}
    event = {'id':event_id,'uid':f's:40~l:46~e:{event_id}','date':stamp(start),
             'timeValid':True,'season':{'year':2027,'type':2},'status':status,
             'competitions':[competition]}
    return event


def board(events, *, pagination=True):
    value = {'leagues':[{'id':'46','abbreviation':'NBA'}],'events':deepcopy(events)}
    if pagination:
        value['pagination']={'page':1,'pageCount':1,'totalCount':len(events),'pageSize':1000}
    return value


def observation(name,url,body,observed=OBSERVED):
    raw=canonical(body)
    return {'raw':raw,'source':{'source_id':name,'source_url':url,
        'request_started_at':stamp(observed-timedelta(seconds=1)),'observed_at':stamp(observed),
        'response_completed_at':stamp(observed),'source_updated_at':None,
        'source_response_generated_at':None,'raw_sha256':hashlib.sha256(raw).hexdigest(),
        'raw_bytes':len(raw),'http_status':200,'http_date':None,'etag':None,'last_modified':None}}


def schedule_observations():
    first=event_fixture()
    later=event_fixture('401900002',START+timedelta(hours=8))
    outside=event_fixture('401900003',START+timedelta(days=1))
    return [observation('schedule-20261021',f'{inp.BASE}/scoreboard?dates=20261021&limit=1000',board([first])),
            observation('schedule-20261022',f'{inp.BASE}/scoreboard?dates=20261022&limit=1000',board([later,outside])),
            observation('schedule-20261023',f'{inp.BASE}/scoreboard?dates=20261023&limit=1000',board([]))]


def event_observations(event=None):
    event=event or event_fixture()
    result={'scoreboard':observation('scoreboard',f'{inp.BASE}/scoreboard?dates=20261021',board([event])),
            'summary':observation('summary',f"{inp.BASE}/summary?event={event['id']}",{'header':deepcopy(event)})}
    for team,ids in (('8',['40','20','10']),('2',['60','50','30'])):
        value={'team':{'id':team},'season':{'year':2027,'type':2},
               'athletes':[{'id':pid,'displayName':'Player '+pid,'status':{'type':'active'}} for pid in ids]}
        result['roster-'+team]=observation('roster-'+team,f'{inp.BASE}/teams/{team}/roster',value)
    return result


def input_fixture():
    with patch.object(inp,'_now',return_value=NOW):
        schedule=inp.make_schedule('2026-10-22',schedule_observations(),mode='SYNTHETIC_DIAGNOSTIC')
        observations=event_observations()
        selection=inp.make_selection(schedule,observations)
        return inp.make_event_body(LedgerRef('research_inputs','a'*64,'b'*64),schedule,selection,observations,mode='SYNTHETIC_DIAGNOSTIC')


def reseal(body,key):
    body[key]=digest({k:v for k,v in body.items() if k!=key})
    return body


class Pros004InputsTests(unittest.TestCase):
    def setUp(self):
        self.clock=patch.object(inp,'_now',return_value=NOW)
        self.clock.start();self.addCleanup(self.clock.stop)

    def test_complete_utc_inventory_includes_previous_route_and_keeps_first_game(self):
        schedule=inp.make_schedule('2026-10-22',schedule_observations(),mode='SYNTHETIC_DIAGNOSTIC')
        self.assertEqual([e['event_id'] for e in schedule['events']],['401900001','401900002'])
        first=inp.first_event(schedule)
        self.assertEqual(first['event_id'],'401900001')
        cutoff=inp.utc(first['event_starts_at'])-timedelta(minutes=90)
        self.assertEqual(cutoff.date(),date(2026,10,21))
        self.assertLess(cutoff.date(),date.fromisoformat(schedule['study_date']))
        self.assertEqual(len(schedule['source_proofs']),3)

    def test_unknown_or_conflicting_pagination_never_becomes_complete_boolean(self):
        values=schedule_observations()
        for bad in (board([event_fixture()],pagination=False),board([event_fixture()])|{'pagination':{'page':1,'pageCount':2,'totalCount':2,'pageSize':1000}},board([event_fixture()])|{'complete':True,'pagination':None}):
            changed=deepcopy(values);changed[0]=observation('schedule-20261021',changed[0]['source']['source_url'],bad)
            with self.assertRaisesRegex(IntegrityError,'COMPLETENESS|pagination'):
                inp.make_schedule('2026-10-22',changed)
        schedule=inp.make_schedule('2026-10-22',values)
        schedule['source_proofs'][0]['pagination']['page']=True
        reseal(schedule,'schedule_id')
        with self.assertRaisesRegex(IntegrityError,'completeness'):
            inp.validate_schedule(schedule)

    def test_raw_byte_binding_and_adjacent_exact_dates_are_required(self):
        values=schedule_observations();values[0]['raw']+=b' '
        with self.assertRaisesRegex(IntegrityError,'bind supplied response bytes'):
            inp.make_schedule('2026-10-22',values)
        values=schedule_observations();values[-1]['source']['source_url']=f'{inp.BASE}/scoreboard?dates=20261024&limit=1000'
        with self.assertRaisesRegex(IntegrityError,'adjacent dates'):
            inp.make_schedule('2026-10-22',values)
        with self.assertRaisesRegex(IntegrityError,'reservation'):
            inp.make_schedule('2026-11-11',schedule_observations())
        values=schedule_observations();wrong=event_fixture();wrong['season']['year']=2028;values[0]=observation('schedule-20261021',values[0]['source']['source_url'],board([wrong]))
        with self.assertRaisesRegex(IntegrityError,'ending-year2027'):
            inp.make_schedule('2026-10-22',values)

    def test_selection_lowest_two_per_team_is_frozen_before_cutoff(self):
        body=input_fixture()
        self.assertEqual([p['player_id'] for p in body['candidates']],['10','20','30','50'])
        self.assertEqual(body['selection']['event_version'],body['event']['event_version'])
        self.assertNotIn('history',body)
        self.assertNotIn('history_provenance',body)
        self.assertEqual(body['history_ref']['record_id'],'a'*64)
        with patch.object(inp,'_now',return_value=NOW+timedelta(minutes=6)):
            with self.assertRaisesRegex(IntegrityError,'selection closes'):
                inp.make_selection(body['schedule'],event_observations())
        changed=deepcopy(body);changed['selection']['players'][0]['player_id']='40';reseal(changed['selection'],'selection_id');changed['candidates']=changed['selection']['players'];reseal(changed,'sourcepack_id')
        with self.assertRaisesRegex(IntegrityError,'lowest-numeric'):
            inp.validate_event(changed)

    def test_changed_event_version_or_selected_player_blocks_without_replacement(self):
        body=input_fixture();event=event_fixture(start=START+timedelta(minutes=10))
        with self.assertRaisesRegex(IntegrityError,'version changed'):
            inp.make_event_body(body['history_ref'],body['schedule'],body['selection'],event_observations(event),mode='SYNTHETIC_DIAGNOSTIC')
        observations=event_observations()
        bad={'team':{'id':'8'},'season':{'year':2027,'type':2},'athletes':[
            {'id':'20','displayName':'Player 20','status':{'type':'active'}},
            {'id':'40','displayName':'Player 40','status':{'type':'active'}}]}
        observations['roster-8']=observation('roster-8',f'{inp.BASE}/teams/8/roster',bad)
        with self.assertRaisesRegex(IntegrityError,'selected-player identity changed'):
            inp.make_event_body(body['history_ref'],body['schedule'],body['selection'],observations,mode='SYNTHETIC_DIAGNOSTIC')

    def test_stale_future_and_late_import_clock_gates_survive_readback(self):
        body=input_fixture()
        stale=deepcopy(body);src=stale['sources']['summary'];src.update(request_started_at=stamp(NOW-timedelta(minutes=6)),observed_at=stamp(NOW-timedelta(minutes=6)),response_completed_at=stamp(NOW-timedelta(minutes=6)));reseal(stale,'sourcepack_id')
        with self.assertRaisesRegex(IntegrityError,'stale/future'):
            inp.validate_event(stale)
        future=deepcopy(body);future['sources']['summary']['source_updated_at']=stamp(NOW+timedelta(seconds=1));reseal(future,'sourcepack_id')
        with self.assertRaisesRegex(IntegrityError,'follows observation'):
            inp.validate_event(future)
        with patch.object(inp,'_now',return_value=NOW+timedelta(days=3)):
            self.assertEqual(inp.validate_event(body)['sourcepack_id'],body['sourcepack_id'])
        late=deepcopy(body);late['imported_at']=stamp(NOW+timedelta(minutes=6));reseal(late,'sourcepack_id')
        with self.assertRaisesRegex(IntegrityError,'selection close'):
            inp.validate_event(late,now=NOW+timedelta(hours=1))

    def test_empty_day_is_valid_empty_not_replacement_and_invalid_first_is_retained(self):
        values=[observation(f'schedule-{day}',f'{inp.BASE}/scoreboard?dates={day}&limit=1000',board([])) for day in ('20261021','20261022','20261023')]
        empty=inp.make_schedule('2026-10-22',values)
        self.assertIsNone(inp.first_event(empty))
        with self.assertRaisesRegex(IntegrityError,'VALID_EMPTY_UTC_DATE'):
            inp.make_selection(empty,event_observations())
        values=schedule_observations();first=event_fixture();first['competitions'][0]['status']['type']={'name':'STATUS_POSTPONED','state':'pre','completed':False};values[0]=observation('schedule-20261021',values[0]['source']['source_url'],board([first]))
        schedule=inp.make_schedule('2026-10-22',values)
        with self.assertRaisesRegex(IntegrityError,'earliest frozen event'):
            inp.first_event(schedule)

    def test_history_no_truncation_and_original_provenance_limitations_are_immutable(self):
        rows=tiny_history();history=old.compact_history(rows);original=inp._original_provenance()
        with self.assertRaisesRegex(IntegrityError,'complete fixed history'):
            inp.make_history_body(history,original)
        p=provenance(rows)
        raw=old._panel_bytes(rows)
        with ExitStack() as stack:
            for name,value in (('PANEL_SHA256',hashlib.sha256(raw).hexdigest()),('PANEL_ROWS',len(rows)),('PANEL_BYTES',len(raw))):
                stack.enter_context(patch.object(inp,name,value))
            stack.enter_context(patch.object(inp,'_original_provenance',return_value=p))
            body=inp.make_history_body(history,p,mode='SYNTHETIC_DIAGNOSTIC')
            recovered=inp.history_rows(body)
            self.assertEqual(len(recovered),1)
            self.assertEqual(recovered[0].outcome_available_at,rows[0].event_start+timedelta(hours=24))
            self.assertEqual(body['history_provenance'],p)
            changed=deepcopy(body);changed['history_provenance']['availability_semantics']='proved historical availability';reseal(changed,'history_id')
            with self.assertRaisesRegex(IntegrityError,'limitations must remain unchanged'):
                inp.validate_history(changed)

    def test_dnp_missing_and_genuine_zero_remain_distinct(self):
        rows=tiny_history();history=old.compact_history(rows);original=inp._original_provenance()
        changed=deepcopy(history);changed['constants']['participation']='DNP'
        with self.assertRaisesRegex(IntegrityError,'history'):
            inp.make_history_body(changed,original)
        changed=deepcopy(history)
        index=changed['columns'].index('minutes');changed['rows'][0][index]=None
        with self.assertRaisesRegex(IntegrityError,'DNP/missing distinct'):
            inp.make_history_body(changed,original)
        # Recorded zero stays a real APPEARED outcome; it is not filled for DNP.
        from dataclasses import replace
        zero=replace(rows[0],minutes=0.0)
        p=provenance([zero]);raw=old._panel_bytes([zero])
        with ExitStack() as stack:
            for name,value in (('PANEL_SHA256',hashlib.sha256(raw).hexdigest()),('PANEL_ROWS',1),('PANEL_BYTES',len(raw))):
                stack.enter_context(patch.object(inp,name,value))
            stack.enter_context(patch.object(inp,'_original_provenance',return_value=p))
            body=inp.make_history_body(old.compact_history([zero]),p,mode='SYNTHETIC_DIAGNOSTIC')
            self.assertEqual(inp.history_rows(body)[0].minutes,0)

    def test_normalizer_source_and_lane_are_bound_and_event_pack_is_bounded(self):
        body=input_fixture();changed=deepcopy(body);changed['normalizer']['code_sha256']='0'*64;reseal(changed,'sourcepack_id')
        with self.assertRaisesRegex(IntegrityError,'source bytes differ'):
            inp.validate_event(changed)
        changed=deepcopy(body);changed['mode']='REAL_TIME_CAPTURED';reseal(changed,'sourcepack_id')
        with self.assertRaisesRegex(IntegrityError,'evidence lanes differ'):
            inp.validate_event(changed)
        with patch.object(inp,'MAX_EVENT_BODY_BYTES',10):
            with self.assertRaisesRegex(IntegrityError,'32KiB'):
                inp.validate_event(body)

    def test_cached_history_is_exact_content_bounded_and_never_caches_dynamic_gates(self):
        from dataclasses import FrozenInstanceError
        rows=tiny_history();history=old.compact_history(rows);p=provenance(rows);raw=old._panel_bytes(rows)
        inp._fixed_history_rows.cache_clear();inp._historical_appearances.cache_clear()
        self.addCleanup(inp._fixed_history_rows.cache_clear)
        self.addCleanup(inp._historical_appearances.cache_clear)
        with ExitStack() as stack:
            for name,value in (('PANEL_SHA256',hashlib.sha256(raw).hexdigest()),('PANEL_ROWS',len(rows)),('PANEL_BYTES',len(raw))):
                stack.enter_context(patch.object(inp,name,value))
            original=stack.enter_context(patch.object(inp,'_original_provenance',return_value=p))
            decode=stack.enter_context(patch.object(old,'unpack_history',wraps=old.unpack_history))
            body=inp.make_history_body(history,p,mode='SYNTHETIC_DIAGNOSTIC')
            inp.validate_history(deepcopy(body))
            converted=inp.history_rows(body)
            with self.assertRaises(FrozenInstanceError):
                converted[0].minutes=999
            converted.clear()
            self.assertEqual(len(inp.history_rows(body)),len(rows))
            self.assertEqual(decode.call_count,1)
            self.assertGreaterEqual(original.call_count,4)
            self.assertEqual(inp._fixed_history_rows.cache_info().maxsize,1)
            self.assertEqual(inp._historical_appearances.cache_info().maxsize,1)
            future=deepcopy(body);future['imported_at']=stamp(NOW+timedelta(seconds=1));reseal(future,'history_id')
            with self.assertRaisesRegex(IntegrityError,'in the future'):
                inp.validate_history(future)
            changed=deepcopy(body);changed['history_provenance']['availability_semantics']='proved';reseal(changed,'history_id')
            with self.assertRaisesRegex(IntegrityError,'limitations must remain unchanged'):
                inp.validate_history(changed)
            self.assertEqual(decode.call_count,1)
            changed=deepcopy(body)
            changed['history']['rows'][0][changed['history']['columns'].index('minutes')]+=1
            reseal(changed,'history_id')
            with self.assertRaisesRegex(IntegrityError,'complete fixed history'):
                inp.validate_history(changed)
            self.assertEqual(decode.call_count,2)
            with patch.object(inp,'PANEL_SHA256','0'*64):
                with self.assertRaisesRegex(IntegrityError,'complete fixed history'):
                    inp.validate_history(body)
            self.assertEqual(decode.call_count,3)

    def test_event_and_shared_history_lanes_cannot_be_relabelled(self):
        for event_mode in inp.MODES:
            for history_mode in inp.MODES:
                if event_mode==history_mode:
                    self.assertEqual(inp.validate_input_lanes({'mode':event_mode},{'mode':history_mode}),event_mode)
                else:
                    with self.assertRaisesRegex(IntegrityError,'evidence lanes differ'):
                        inp.validate_input_lanes({'mode':event_mode},{'mode':history_mode})


if __name__=='__main__':
    unittest.main()
