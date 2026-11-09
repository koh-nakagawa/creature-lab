from pathlib import Path
import plistlib,os
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parent
app=ROOT/'へんてこ生物研究所.app';contents=app/'Contents';(contents/'MacOS').mkdir(parents=True);(contents/'Resources').mkdir()
info={'CFBundleName':'へんてこ生物研究所','CFBundleDisplayName':'へんてこ生物研究所','CFBundleIdentifier':'jp.k0.creaturelab.local',
 'CFBundleVersion':'1','CFBundleShortVersionString':'1.0','CFBundlePackageType':'APPL','CFBundleExecutable':'CreatureLab',
 'CFBundleIconFile':'CreatureLab.icns','LSMinimumSystemVersion':'12.0','NSHighResolutionCapable':True}
with (contents/'Info.plist').open('xb') as out:plistlib.dump(info,out)
script='#!/bin/sh\nAPP_PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)"\nexec "${CREATURE_LAB_PYTHON:-$APP_PROJECT_DIR/.venv/bin/python}" "$APP_PROJECT_DIR/launch.py"\n'
target=contents/'MacOS/CreatureLab';target.write_text(script);target.chmod(0o755)
image=Image.new('RGBA',(1024,1024),(0,0,0,0));d=ImageDraw.Draw(image)
d.rounded_rectangle((40,40,984,984),radius=210,fill='#397d65');d.ellipse((165,225,859,835),fill='#b0d6ad')
for x in [365,665]:
 d.ellipse((x-84,375,x+84,543),fill='#fffbea');d.ellipse((x-35,415,x+35,485),fill='#253b35')
d.arc((365,560,665,730),0,180,fill='#253b35',width=36)
image.save(contents/'Resources/CreatureLab.icns',format='ICNS')
print('MAC_APP_READY',app)
