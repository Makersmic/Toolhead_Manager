import sys, subprocess, glob, os
from PIL import Image
a,b=int(sys.argv[1]),int(sys.argv[2]); cols=int(sys.argv[3]) if len(sys.argv)>3 else 4
os.makedirs('proof/hi',exist_ok=True)
for f in glob.glob('proof/hi/*'): os.remove(f)
subprocess.run(['pdftoppm','-r','55','-png','-f',str(a),'-l',str(b),'Rhino-User-Manual.pdf','proof/hi/p'],check=True)
fs=sorted(glob.glob('proof/hi/p-*.png')); ims=[Image.open(f) for f in fs]; w,h=ims[0].size
rows=(len(ims)+cols-1)//cols
s=Image.new('RGB',(cols*(w+6),rows*(h+6)),'#777')
for i,im in enumerate(ims): s.paste(im,((i%cols)*(w+6),(i//cols)*(h+6)))
s.save('proof/hs.png'); print(s.size)
