"""Authoritative six-step workshop clock and automatic geometry policy."""
import math,time
import geometry

STEP_KEYS=('body','head','limbs','tail','eyes','expression')
STEP_SECONDS=60
NOZZLE='0.6'
QUALITY='standard'
MAX_MODEL_SECONDS=300
START_SIZE=32
MIN_SIZE=25

def automatic_config(value):
    config=geometry.normalize_config(value)
    body=config['body'];tail=config['tail']
    config.update(size=START_SIZE,
        roundness={'dragon':1.0,'armored':1.02,'octopus':1.0,'slug':.95,'turtle':1.05,'axolotl':.95}[body],
        tail_length=1.1 if body=='dragon' and tail=='long' else .85 if tail=='fan' else .9 if tail in ('long','club','fork') else 1.0,
        eye_size={'one':1.0,'two':.95,'three':.85}[config['eyes']])
    return geometry.normalize_config(config)

def catalog_policy():
    return dict(step_keys=list(STEP_KEYS),step_seconds=STEP_SECONDS,maximum_selection_seconds=len(STEP_KEYS)*STEP_SECONDS,
                automatic_parameters=['size','roundness','tail_length','eye_size','back','texture'],
                print_settings=dict(nozzle=NOZZLE,quality=QUALITY,speed_percent=100,layer_height=.30))

def next_size(size,model_seconds):
    if size<=MIN_SIZE or model_seconds<=MAX_MODEL_SECONDS:return None
    proposed=math.floor(size*min(.94,max(.72,(285/model_seconds)**.85)))
    return max(MIN_SIZE,min(size-1,proposed))

class Session:
    def __init__(self,id,now=None):
        now=time.time() if now is None else float(now)
        self.id=id;self.started=now;self.index=0;self.deadline=now+STEP_SECONDS
        self.config=automatic_config(geometry.catalog()['default_config'])
        self.phase='selecting';self.completed_at=None;self.prepare_job_id=None;self.selections=[]
    def sync(self,now):
        while self.phase=='selecting' and now>=self.deadline:
            self._advance(self.deadline,'timeout')
    def _advance(self,when,reason):
        self.selections.append(dict(key=STEP_KEYS[self.index],value=self.config[STEP_KEYS[self.index]],reason=reason,finished_at=when))
        self.index+=1
        if self.index==len(STEP_KEYS):self.phase='complete';self.completed_at=when
        else:self.deadline=when+STEP_SECONDS
    def state(self,now=None):
        now=time.time() if now is None else float(now);self.sync(now)
        return dict(id=self.id,phase=self.phase,step_index=self.index,
                    step_key=STEP_KEYS[self.index] if self.phase=='selecting' else None,
                    deadline=self.deadline if self.phase=='selecting' else None,
                    remaining_seconds=max(0,self.deadline-now) if self.phase=='selecting' else 0,
                    server_time=now,started_at=self.started,completed_at=self.completed_at,
                    config=dict(self.config),selections=list(self.selections),prepare_job_id=self.prepare_job_id,
                    step_keys=list(STEP_KEYS),step_seconds=STEP_SECONDS)
    def choose(self,expected_index,key,value,now=None):
        now=time.time() if now is None else float(now);self.sync(now)
        if self.phase!='selecting' or expected_index!=self.index:return self.state(now)
        if key!=STEP_KEYS[self.index]:raise ValueError('いまのステップのパーツを選んでください。')
        candidate=dict(self.config)
        if key=='body':
            preset=next((p for p in geometry.catalog()['presets'] if p['id']==value),None)
            if preset is None:raise ValueError('この体は選べません。')
            candidate=dict(preset['config'])
        candidate[key]=value;self.config=automatic_config(candidate)
        return self.state(now)
    def advance(self,expected_index,now=None):
        now=time.time() if now is None else float(now);self.sync(now)
        if self.phase=='selecting' and expected_index==self.index:self._advance(now,'chosen')
        return self.state(now)
