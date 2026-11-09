"""Protocol behavior tests use fakes only; never contact a printer."""
from pathlib import Path
import sys,unittest,itertools
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import printer_transport as p

PROFILE={'ip':'192.168.0.200','serial':'TESTA1MINI123','access_code':'TEST0000'}

class FakeMQTT:
    behavior='start';busy=False
    def __init__(self,profile):self.state={'gcode_state':'IDLE','print_error':0};self.sent=[]
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def snapshot(self):return {'gcode_state':'RUNNING' if self.busy else 'IDLE','print_error':0,'spd_lvl':2,'spd_mag':100}
    def publish(self,value):self.sent.append(value)
    def read_json(self,timeout):
        seq=self.sent[-1]['print']['sequence_id']
        if self.behavior=='reject':return {'print':{'sequence_id':seq,'result':'fail','reason':'developer mode required'}}
        if self.behavior=='start':self.state['gcode_state']='PREPARE'
        return {'print':{'sequence_id':seq,'result':'success'}}

class Tests(unittest.TestCase):
    def test_mqtt_encoding(self):
        self.assertEqual(p.remaining(128),b'\x80\x01');self.assertEqual(p.enc('abc'),b'\0\3abc')
    def test_public_and_loopback_rejected(self):
        for ip in ['8.8.8.8','127.0.0.1','0.0.0.0','224.0.0.1']:
            with self.assertRaises(p.PrinterError):p.validate_profile(PROFILE|{'ip':ip})
    def test_busy_never_uploads(self):
        with patch.object(p,'MQTT',FakeMQTT),patch.object(FakeMQTT,'busy',True),patch.object(p,'upload_verified') as upload:
            with self.assertRaises(p.PrinterError):p.send_print(PROFILE,'unused')
            upload.assert_not_called()
    def test_actual_transition_confirms_start(self):
        with patch.object(p,'MQTT',FakeMQTT),patch.object(p,'upload_verified',return_value=('model/unique.gcode.3mf','sha')):
            value=p.send_print(PROFILE,'unused')
        self.assertTrue(value['started']);self.assertTrue(value['acknowledged']);self.assertEqual(value['printer']['state'],'PREPARE')
    def test_ack_alone_never_claims_started(self):
        ticks=itertools.count()
        with patch.object(p,'MQTT',FakeMQTT),patch.object(FakeMQTT,'behavior','ack_only'),patch.object(p,'upload_verified',return_value=('model/unique.gcode.3mf','sha')),patch.object(p.time,'monotonic',side_effect=lambda:next(ticks)):
            value=p.send_print(PROFILE,'unused')
        self.assertFalse(value['started']);self.assertTrue(value['unverified']);self.assertTrue(value['acknowledged'])
    def test_rejection_reported(self):
        with patch.object(p,'MQTT',FakeMQTT),patch.object(FakeMQTT,'behavior','reject'),patch.object(p,'upload_verified',return_value=('unique.gcode.3mf','sha')):
            with self.assertRaises(p.PrinterError):p.send_print(PROFILE,'unused')
    def test_snapshot_requires_fresh_state_field(self):
        client=p.MQTT(PROFILE);client.state={'gcode_state':'IDLE'};client.publish=MagicMock()
        sequence=iter([{'print':{'sequence_id':'1','result':'success'}},{'print':{'gcode_state':'RUNNING'}}])
        def receive(timeout):
            item=next(sequence);client.state.update(item['print']);return item
        client.read_json=receive
        self.assertEqual(client.snapshot()['gcode_state'],'RUNNING')
    def test_protected_ftp_data_reuses_control_session(self):
        ctx=MagicMock()
        with patch.object(p,'context',return_value=ctx):client=p.ImplicitFTPS(PROFILE)
        client._prot_p=True;client.host=PROFILE['ip'];client.sock=MagicMock();client.sock.session='control-session'
        raw=object()
        with patch.object(p.ftplib.FTP,'ntransfercmd',return_value=(raw,123)):client.ntransfercmd('STOR unique.gcode.3mf')
        ctx.wrap_socket.assert_called_once_with(raw,server_hostname=PROFILE['ip'],session='control-session')
    def test_standard_speed_needs_no_command_when_fresh(self):
        client=FakeMQTT(PROFILE);p.standard_speed(client,{'spd_lvl':2,'spd_mag':100})
        self.assertEqual(client.sent,[])
    def test_sport_speed_is_changed_once_and_telemetry_required(self):
        client=FakeMQTT(PROFILE);client.read_json=lambda timeout:{'print':{'spd_lvl':2,'spd_mag':100}}
        p.standard_speed(client,{'spd_lvl':3,'spd_mag':124})
        self.assertEqual(len(client.sent),1);self.assertEqual(client.sent[0]['print']['command'],'print_speed')
        self.assertEqual(client.sent[0]['print']['param'],'2')
    def test_speed_ack_alone_does_not_allow_print(self):
        client=FakeMQTT(PROFILE);ticks=itertools.count()
        with patch.object(p.time,'monotonic',side_effect=lambda:next(ticks)):
            with self.assertRaises(p.PrinterError):p.standard_speed(client,{'spd_lvl':3})
        self.assertEqual(len(client.sent),1)
    def test_conflicting_speed_magnitude_is_not_accepted(self):
        client=FakeMQTT(PROFILE);client.read_json=lambda timeout:{'print':{'spd_lvl':2,'spd_mag':124}};ticks=itertools.count()
        with patch.object(p.time,'monotonic',side_effect=lambda:next(ticks)):
            with self.assertRaises(p.PrinterError):p.standard_speed(client,{'spd_lvl':2,'spd_mag':124})

if __name__=='__main__':unittest.main(verbosity=2)
