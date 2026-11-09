"""A1 mini LAN developer-mode transport. Never starts a job implicitly/retries."""
import socket,ssl,struct,json,time,secrets,ipaddress,ftplib,hashlib,re
from pathlib import Path

class PrinterError(RuntimeError):pass
def validate_profile(profile):
    try:address=ipaddress.ip_address(str(profile.get('ip','')))
    except ValueError:raise PrinterError('プリンターのLAN内IPアドレスを入力してください。')
    if not address.is_private or address.is_loopback or address.is_multicast or address.is_unspecified:raise PrinterError('LAN内のプリンターIPを指定してください。')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,40}',str(profile.get('serial',''))):raise PrinterError('本体のシリアル番号を確認してください。')
    if not re.fullmatch(r'[A-Za-z0-9]{8}',str(profile.get('access_code',''))):raise PrinterError('8文字のLANアクセスコードを入力してください。')
    return str(address)
def context():
    c=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);c.check_hostname=False;c.verify_mode=ssl.CERT_NONE
    return c
def pin(sock,profile,kind):
    fp=hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest()
    pins=profile.setdefault('_tls_pins',{})
    if pins.get(kind) and pins[kind]!=fp:raise PrinterError('プリンターの証明書が変わりました。接続設定を入れ直してください。')
    pins[kind]=fp
def enc(value):
    b=value.encode();return struct.pack('!H',len(b))+b
def remaining(n):
    out=bytearray()
    while True:
        b=n%128;n//=128;out.append(b|(128 if n else 0))
        if not n:return bytes(out)

class MQTT:
    def __init__(self,profile):
        self.profile=profile;self.ip=validate_profile(profile);self.sock=None;self.state={};self.last_report=0
    def _read(self,n):
        out=b''
        while len(out)<n:
            p=self.sock.recv(n-len(out))
            if not p:raise PrinterError('プリンターとの接続が閉じられました。')
            out+=p
        return out
    def packet(self):
        head=self._read(1)[0];n=0;factor=1
        for _ in range(4):
            b=self._read(1)[0];n+=(b&127)*factor
            if not b&128:break
            factor*=128
        if n>4_000_000:raise PrinterError('プリンターの応答が大きすぎます。')
        return head,self._read(n)
    def send(self,head,payload):self.sock.sendall(bytes([head])+remaining(len(payload))+payload)
    def __enter__(self):
        raw=socket.create_connection((self.ip,8883),timeout=8)
        self.sock=context().wrap_socket(raw,server_hostname=self.ip);self.sock.settimeout(8);pin(self.sock,self.profile,'mqtt')
        self.send(0x10,enc('MQTT')+bytes([4,0xC2])+struct.pack('!H',30)+enc('creature-'+secrets.token_hex(5))+enc('bblp')+enc(self.profile['access_code']))
        h,p=self.packet()
        if h>>4!=2 or len(p)<2 or p[1]!=0:raise PrinterError('接続が拒否されました。LANアクセスコードとDeveloper Modeを確認してください。')
        self.send(0x82,struct.pack('!H',1)+enc('device/'+self.profile['serial']+'/report')+b'\0')
        # SUBACK and reports may arrive in either order; read_json handles both.
        return self
    def __exit__(self,*args):
        if self.sock:
            try:self.send(0xE0,b'')
            except OSError:pass
            self.sock.close()
    def publish(self,data):self.send(0x30,enc('device/'+self.profile['serial']+'/request')+json.dumps(data,separators=(',',':')).encode())
    def read_json(self,timeout=1):
        self.sock.settimeout(timeout)
        try:h,p=self.packet()
        except socket.timeout:return None
        if h>>4!=3:return None
        length=struct.unpack('!H',p[:2])[0];offset=2+length
        if ((h>>1)&3):
            packet_id=p[offset:offset+2];offset+=2;self.send(0x40,packet_id)
        try:data=json.loads(p[offset:])
        except (UnicodeDecodeError,json.JSONDecodeError):return None
        if isinstance(data.get('print'),dict):
            item=data['print'];self.state.update(item);self.last_report=time.monotonic()
        return data
    def snapshot(self,timeout=9):
        self.publish({'pushing':{'sequence_id':str(secrets.randbelow(999999)),'command':'pushall'}})
        end=time.monotonic()+timeout;start=time.monotonic()
        while time.monotonic()<end:
            data=self.read_json(min(1,max(.1,end-time.monotonic())))
            if 'gcode_state' in (data or {}).get('print',{}):return dict(self.state)
        raise PrinterError('状態を取得できません。IP・シリアル番号・LAN Only・Developer Modeを確認してください。')

class ImplicitFTPS(ftplib.FTP_TLS):
    def __init__(self,profile):super().__init__(context=context(),timeout=12);self.profile=profile
    def connect(self,host='',port=990,timeout=12,source_address=None):
        self.host=host;self.port=port;self.sock=socket.create_connection((host,port),timeout,source_address)
        self.af=self.sock.family;self.sock=self.context.wrap_socket(self.sock,server_hostname=host);pin(self.sock,self.profile,'ftps')
        self.file=self.sock.makefile('r',encoding=self.encoding);self.welcome=self.getresp();return self.welcome
    def ntransfercmd(self,cmd,rest=None):
        conn,size=ftplib.FTP.ntransfercmd(self,cmd,rest)
        if self._prot_p:conn=self.context.wrap_socket(conn,server_hostname=self.host,session=self.sock.session)
        return conn,size

def upload_verified(profile,path):
    ip=validate_profile(profile);path=Path(path);remote='creature_'+secrets.token_hex(10)+'.gcode.3mf'
    with ImplicitFTPS(profile) as ftp:
        ftp.connect(ip);ftp.login('bblp',profile['access_code']);ftp.prot_p();folder=''
        try:ftp.cwd('/model');folder='model/'
        except ftplib.error_perm:pass
        with path.open('rb') as src:ftp.storbinary('STOR '+remote,src,blocksize=65536)
        ftp.voidcmd('TYPE I')
        if ftp.size(remote)!=path.stat().st_size:raise PrinterError('転送後のファイルサイズが一致しません。印刷は開始していません。')
        checksum=hashlib.sha256();ftp.retrbinary('RETR '+remote,checksum.update,blocksize=65536)
        local=hashlib.sha256(path.read_bytes()).hexdigest()
        if checksum.hexdigest()!=local:raise PrinterError('転送ファイルの検証に失敗しました。印刷は開始していません。')
    return folder+remote,local

def summarize(state):
    return dict(state=str(state.get('gcode_state','UNKNOWN')),progress=state.get('mc_percent'),
        remaining_minutes=state.get('mc_remaining_time'),nozzle_temperature=state.get('nozzle_temper'),
        bed_temperature=state.get('bed_temper'),error=state.get('print_error',0),name=state.get('subtask_name',''),
        speed_level=state.get('spd_lvl'),speed_percent=state.get('spd_mag'))
def idle(state):
    if state.get('gcode_state') not in ('IDLE','FINISH'):raise PrinterError('プリンターが待機中ではありません。現在の状態を確認してください。')
    if state.get('print_error',0):raise PrinterError('プリンターにエラーが出ています。本体で確認してください。')
def status(profile):
    with MQTT(profile) as mqtt:return summarize(mqtt.snapshot())

def standard_speed(mqtt,state):
    """Verify fresh telemetry; command level 2 once if the printer needs it."""
    def verified(value):
        return value.get('spd_lvl')==2 and ('spd_mag' not in value or value['spd_mag']==100)
    if verified(state):return
    seq=str(secrets.randbelow(2_000_000_000))
    mqtt.publish({'print':dict(sequence_id=seq,command='print_speed',param='2')})
    end=time.monotonic()+6
    while time.monotonic()<end:
        message=(mqtt.read_json(1) or {}).get('print',{})
        state=state|message
        if str(message.get('sequence_id',''))==seq and 'result' in message and str(message['result']).lower() not in ('success','ok'):
            raise PrinterError('標準速度への設定が拒否されました。印刷は開始していません。')
        # A command ACK alone is insufficient: require a new speed report.
        if 'spd_lvl' in message and verified(state):return
    raise PrinterError('標準速度（100%）を確認できません。本体で速度を確認してください。印刷は開始していません。')

def send_print(profile,path,gcode_entry='Metadata/plate_1.gcode'):
    """Only called after a user presses the final print action. No retry."""
    with MQTT(profile) as mqtt:
        idle(mqtt.snapshot());remote,checksum=upload_verified(profile,path)
        state=mqtt.snapshot();idle(state);standard_speed(mqtt,state)
        seq=str(secrets.randbelow(2_000_000_000))
        payload={'print':dict(sequence_id=seq,command='project_file',param=gcode_entry,url='ftp:///'+remote,
            subtask_name=Path(remote).name,md5='',bed_type='auto',timelapse=False,flow_cali=True,bed_leveling=True,
            vibration_cali=True,layer_inspect=True,use_ams=False,ams_mapping=[],project_id='0',profile_id='0',task_id='0',subtask_id='0')}
        mqtt.publish(payload);ack=False;end=time.monotonic()+25
        while time.monotonic()<end:
            data=mqtt.read_json(1)
            p=(data or {}).get('print',{})
            if str(p.get('sequence_id',''))==seq and 'result' in p:
                if str(p['result']).lower() not in ('success','ok'):raise PrinterError('プリンターがジョブを拒否しました：'+str(p.get('reason','設定を確認してください。')))
                ack=True
            if mqtt.state.get('print_error',0):raise PrinterError('送信後にプリンターエラーが報告されました。本体を確認してください。再送信はしていません。')
            if mqtt.state.get('gcode_state') in ('PREPARE','RUNNING','SLICING'):
                return dict(started=True,acknowledged=ack,remote_file=remote,sha256=checksum,printer=summarize(mqtt.state))
        return dict(started=False,acknowledged=ack,unverified=True,remote_file=remote,sha256=checksum,
                    message='転送しましたが印刷開始は確認できません。本体を確認してください。自動再送はしません。')
