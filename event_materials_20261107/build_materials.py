from pathlib import Path
import json
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor,Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

R=Path(__file__).resolve().parent;APP=R.parent;OUT=R/'output/pdf';MM=72/25.4
OUT.mkdir(parents=True,exist_ok=True)
for key,weight in [('R','Regular'),('B','Bold'),('X','ExtraBold')]:pdfmetrics.registerFont(TTFont(key,str(R/'assets'/f'Rounded-{weight}.ttf')))
INK='#224D40';GREEN='#397D65';MINT='#E5EFDF';CREAM='#F8F6ED';YELLOW='#F3C961';MUTED='#56705D';WHITE='#FFFEF9'

class Page:
 def __init__(self,name,w,h):
  self.w=w;self.h=h;self.c=canvas.Canvas(str(OUT/name),pagesize=(w*MM,h*MM),pageCompression=1)
  self.c.setTitle('へんてこ生物研究所 '+('A3 フライヤー' if w==297 else 'A4 体験説明書'))
  self.c.setAuthor('へんてこ生物研究所');self.rect(0,0,w,h,CREAM)
 def rect(self,x,y,w,h,color,r=0,stroke=None):
  c=self.c;c.setFillColor(HexColor(color));c.setStrokeColor(HexColor(stroke or color));c.setLineWidth(.7)
  if r:c.roundRect(x*MM,(self.h-y-h)*MM,w*MM,h*MM,r*MM,fill=1,stroke=bool(stroke))
  else:c.rect(x*MM,(self.h-y-h)*MM,w*MM,h*MM,fill=1,stroke=bool(stroke))
 def text(self,x,y,s,size=12,color=INK,font='R',center=False):
  c=self.c;c.setFont(font,size);c.setFillColor(HexColor(color));px=x*MM
  if center:px-=pdfmetrics.stringWidth(s,font,size)/2
  assert px>=0 and px+pdfmetrics.stringWidth(s,font,size)<=self.w*MM+.1,(s,px)
  c.drawString(px,(self.h-y)*MM-size,s)
 def image(self,path,x,y,w,h):
  self.c.drawImage(ImageReader(str(path)),x*MM,(self.h-y-h)*MM,w*MM,h*MM,mask='auto',preserveAspectRatio=True,anchor='c')
 def ellipse(self,x,y,w,h,color):
  c=self.c;c.setFillColor(HexColor(color));c.ellipse(x*MM,(self.h-y-h)*MM,(x+w)*MM,(self.h-y)*MM,fill=1,stroke=0)
 def brand(self,x,y,small=False):
  sz=11 if small else 15;self.rect(x,y,sz,sz,GREEN,3)
  c=self.c;c.setStrokeColor(HexColor('#F8E7A2'));c.setLineWidth(1.2)
  c.circle((x+sz/2)*MM,(self.h-y-sz/2)*MM,sz*.31*MM,fill=0,stroke=1)
  self.ellipse(x+sz*.32,y+sz*.32,sz*.36,sz*.36,'#F8E7A2')
 def finish(self):self.c.showPage();self.c.save()

def poster():
 p=Page('へんてこ生物研究所_A3フライヤー.pdf',297,420)
 p.brand(16,16);p.text(38,15,'サイエンスパークまつり',12,GREEN,'B');p.text(38,23,'へんてこ生物研究所',25,INK,'X')
 p.text(16,53,'パーツをえらんで',29,INK,'B')
 p.rect(15,91,160,7,'#F5DE88',2)
 p.text(16,72,'きみだけの',51,INK,'X');p.text(16,96,'いきものをつくろう！',44,INK,'X')
 p.ellipse(13,129,269,139,MINT)
 p.ellipse(214,116,8,8,YELLOW);p.ellipse(26,256,5,5,YELLOW)
 p.image(R/'assets/01_dragon_modoki.png',8,124,166,114.4)
 p.image(R/'assets/03_octopus_modoki.png',171,129,116,79.9)
 p.image(R/'assets/05_turtle_modoki.png',151,204,111,76.5)
 for x,n,title,small in [(16,'01','えらぶ','iPadでパーツを組み合わせ'),(107,'02','3Dでみる','回して、できあがりを確認'),(198,'03','持ち帰る','3Dプリントした作品をゲット')]:
  p.rect(x,289,83,23,WHITE,5)
  p.text(x+5,292,n,10,GREEN,'B');p.text(x+19,290,title,18,INK,'B')
  p.text(x+5,302,small,9.5,MUTED)
 p.rect(16,320,265,37,WHITE,6,stroke='#D8E3D1')
 p.text(26,323,'参加費 1回',12,MUTED,'B');p.text(26,329,'500',46,GREEN,'X');p.text(59,338,'円',23,GREEN,'B')
 p.text(163,324,'所要時間のめやす',12,MUTED,'B');p.text(163,334,'約15分',31,GREEN,'X')
 p.text(148.5,360,'※選び方や印刷の状況によって、時間が前後することがあります。',10,MUTED,center=True)
 p.rect(16,376,265,24,GREEN,6);p.text(148.5,380,'つくった生物を持ち帰ろう！',25,WHITE,'X',center=True)
 p.text(148.5,405,'体験したい人は、スタッフに声をかけてね。',13,GREEN,'B',center=True)
 p.finish()

def heading(p,n,title,y):
 p.ellipse(13,y,10,10,GREEN);p.text(18,y+.5,str(n),16,WHITE,'X',center=True);p.text(27,y-.2,title,17,INK,'B')

def guide():
 p=Page('へんてこ生物研究所_A4体験説明書.pdf',210,297)
 p.brand(13,12,True);p.text(29,11,'へんてこ生物研究所',16,INK,'X');p.text(29,20,'参加費 1回500円   ／   めやす 約15分',11,GREEN,'B')
 p.text(13,32,'オリジナル生物のつくりかた',24,INK,'X')
 heading(p,1,'6つのパーツをえらぼう',54)
 p.text(13,68,'ひとつのパーツは1分まで。きまったら「これにする」をタップ。',10.6)
 p.text(13,75,'時間がくると、いま選んでいる形でつぎへすすむよ。',10.6)
 choices=[('からだ',R/'assets/03_octopus_modoki.png'),('あたま',APP/'frontend/thumbnails/head_ears.png'),('あし・うで',APP/'frontend/thumbnails/limbs_tentacles.png'),('しっぽ',APP/'frontend/thumbnails/tail_curl.png'),('めのかず',APP/'frontend/thumbnails/eyes_three.png'),('ひょうじょう',APP/'frontend/thumbnails/expression_fangs.png')]
 for i,(label,img) in enumerate(choices):
  x=13+i%3*63;y=87+i//3*35
  p.rect(x,y,58,31,WHITE,4,stroke='#DCE5D4');p.text(x+4,y+2,f'{i+1}  {label}',12,GREEN,'B');p.image(img,x+8,y+10,42,19)
 p.text(13,157,'大きさ・バランス・目と口の場所は、おまかせでぴったりに。',10.4,MUTED)
 heading(p,2,'3Dでたしかめよう',170)
 p.text(13,184,'指で回して、すきな角度から見てみよう。',11)
 p.text(13,191,'できたら、なまえをつけてスタッフに見せてね。',11)
 p.image(R/'assets/05_turtle_modoki.png',151,165,45,31)
 heading(p,3,'プリントして受け取ろう',207)
 p.text(13,221,'スタッフと印刷の確認をしたら、プリント開始！',11)
 p.text(13,228,'できあがるまで、動きを見て待ってみよう。',11)
 p.text(13,235,'作品はスタッフから受け取ってね。',11)
 p.rect(13,248,184,16,GREEN,4);p.text(105,251,'つくった生物は、お持ち帰りできます！',15,WHITE,'B',center=True)
 p.text(13,269,'プリンターにはさわらないでね。できたての作品は熱いことがあります。',9.4,MUTED)
 p.text(13,275,'小さな作品を口に入れないでね。時間は選び方や印刷の状況で前後します。',9.4,MUTED)
 p.finish()

if __name__=='__main__':
 poster();guide();print('TWO_PRINT_PDFS_READY')
