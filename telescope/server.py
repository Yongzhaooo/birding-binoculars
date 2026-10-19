"""Small HTTP API behind Caddy; moderation is available only through the local CLI."""
import base64
import hashlib
import hmac
import io
import json
import math
import os
import re
import secrets
import time
import uuid
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from PIL import Image, ImageOps, UnidentifiedImageError
from .storage import ROOT, Store

MAX_BODY=8*1024*1024
MAX_IMAGE=5*1024*1024
Image.MAX_IMAGE_PIXELS=40_000_000


def text(payload, key, maximum, required=False):
    value=payload.get(key,'')
    if not isinstance(value,str) or len(value)>maximum or '\x00' in value:
        raise ValueError(f'{key}格式或长度有误')
    value=value.strip()
    if required and not value: raise ValueError(f'请填写{key}')
    return value


def normalize_image(encoded):
    if not isinstance(encoded,str) or len(encoded)>7*1024*1024: raise ValueError('图片过大')
    try:
        raw=base64.b64decode(encoded,validate=True)
        if not raw or len(raw)>MAX_IMAGE: raise ValueError('图片上限5MiB')
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw),formats=['JPEG','PNG','WEBP']) as source:
                if source.width*source.height>40_000_000 or source.width<32 or source.height<32:
                    raise ValueError('图片需至少32×32像素，最多4000万像素')
                source.load()
                oriented=ImageOps.exif_transpose(source)
                oriented.thumbnail((2400,2400))
                # A fresh raster deliberately drops metadata, profiles and ancillary chunks.
                clean=Image.new('RGB',oriented.size,'white')
                rgba=oriented.convert('RGBA')
                clean.paste(rgba,mask=rgba.getchannel('A'))
                output=io.BytesIO()
                clean.save(output,'JPEG',quality=88,optimize=True)
                return output.getvalue()
    except (UnidentifiedImageError,OSError,SyntaxError,Image.DecompressionBombError,Image.DecompressionBombWarning) as e:
        raise ValueError('无法读取图片，请提供JPEG、PNG或WebP实拍图') from e


def validate(payload, store):
    if not isinstance(payload,dict): raise ValueError('请求必须为对象')
    if payload.get('consent') is not True: raise ValueError('请确认投稿及图片展示授权')
    if payload.get('website'): raise ValueError('提交无效')
    model_id=text(payload,'model_id',30,True)
    kind=text(payload,'kind',20,True)
    if kind not in ('photo','parameter','experience'): raise ValueError('投稿类型有误')
    result={k:text(payload,k,n,k=='credit') for k,n in [('credit',60),('note',2000),('equipment',300),('conditions',500),('source_url',500)]}
    url=result['source_url']
    if url:
        u=urlsplit(url)
        if u.scheme not in ('https','http') or not u.hostname or u.username or u.password: raise ValueError('来源链接需为http或https网页')
    image=None
    if kind=='photo':
        if not result['equipment'] or not result['conditions']: raise ValueError('实拍请填写拍摄设备和条件')
        image=normalize_image(payload.get('image_data'))
    elif kind=='parameter':
        field=text(payload,'field',60,True)
        if field not in store.fields and field!='reference_price': raise ValueError('参数字段无效')
        if field in ('field_m','exit_pupil_mm'): raise ValueError('此项为计算值，请修正原始倍率、物镜口径或视场角')
        v=payload.get('value')
        if field=='reference_price' or store.fields[field]['numeric']:
            if type(v) not in (int,float) or not math.isfinite(v) or v<=0 or v>1_000_000: raise ValueError('数值参数需为有限正数')
            if field=='field_deg' and v>=180: raise ValueError('视场角需小于180°')
        elif not isinstance(v,str) or not v.strip() or len(v)>400: raise ValueError('参数内容需为1至400字')
        result.update(field=field,value=v)
        if not url and len(result['note'])<10: raise ValueError('请提供来源链接，或至少10字的测量/核对说明')
    elif len(result['note'])<10:
        raise ValueError('体验说明请至少填写10字')
    return model_id,kind,result,image


class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,directory,origin=None,trust_proxy=False):
        self.store=Store(directory)
        secret_path=self.store.directory/'request-secret'
        try:
            fd=os.open(secret_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f: f.write(secrets.token_bytes(32))
        except FileExistsError: pass
        self.secret=secret_path.read_bytes()
        self.trust_proxy=trust_proxy
        super().__init__(address,Handler)
        self.origin=(origin or f'http://127.0.0.1:{self.server_address[1]}').rstrip('/')


class Handler(BaseHTTPRequestHandler):
    server_version='Telescope'
    sys_version=''
    def setup(self):
        super().setup()
        self.connection.settimeout(25)

    def log_message(self,fmt,*args):
        # Caddy handles access logs; never echo submitted content or request secrets.
        pass

    def respond(self,status,body,content_type='application/json; charset=utf-8',extra=None):
        if isinstance(body,(dict,list)): body=json.dumps(body,ensure_ascii=False).encode('utf-8')
        elif isinstance(body,str): body=body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','strict-origin-when-cross-origin')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header('Cache-Control','no-store' if content_type.startswith('application/json') else 'public, max-age=300')
        for k,v in (extra or {}).items(): self.send_header(k,v)
        self.end_headers()
        if self.command!='HEAD': self.wfile.write(body)

    def host_valid(self):
        return self.headers.get('Host','').lower()==urlsplit(self.server.origin).netloc.lower()

    def ip_key(self):
        ip=self.client_address[0]
        if self.server.trust_proxy and ip in ('127.0.0.1','::1'):
            ip=self.headers.get('X-Real-IP',ip)
        return hmac.new(self.server.secret,ip.encode(),hashlib.sha256).hexdigest()

    def csrf(self):
        data=f'{int(time.time())}:{secrets.token_hex(12)}'
        return data+':'+hmac.new(self.server.secret,(data+':'+self.ip_key()).encode(),hashlib.sha256).hexdigest()

    def csrf_valid(self):
        try:
            data,signature=self.headers.get('X-CSRF-Token','').rsplit(':',1)
            timestamp=int(data.split(':')[0])
            expected=hmac.new(self.server.secret,(data+':'+self.ip_key()).encode(),hashlib.sha256).hexdigest()
            return 0<=time.time()-timestamp<=1800 and hmac.compare_digest(signature,expected)
        except (ValueError,IndexError): return False

    def do_HEAD(self): self.do_GET()

    def do_GET(self):
        if not self.host_valid(): return self.respond(400,{'error':'Host无效'})
        path=urlsplit(self.path).path
        if path=='/api/session': return self.respond(200,{'token':self.csrf()})
        if path=='/api/catalog': return self.respond(200,self.server.store.public())
        if path=='/api/health': return self.respond(200,{'status':'ok','schema':1})
        assets={'/':('telescope/static/index.html','text/html; charset=utf-8'),
          '/app.js':('telescope/static/app.js','text/javascript; charset=utf-8'),
          '/style.css':('telescope/static/style.css','text/css; charset=utf-8'),
          '/downloads/telescopes.xlsx':('downloads/telescopes.xlsx','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
        if path in assets:
            file,mime=assets[path]
            return self.respond(200,(ROOT/file).read_bytes(),mime)
        if re.fullmatch(r'/media/[a-f0-9]{32}\.jpg',path):
            file=self.server.store.public_image(path.split('/')[-1])
            if file and file.is_file(): return self.respond(200,file.read_bytes(),'image/jpeg')
        return self.respond(404,{'error':'未找到'})

    def do_POST(self):
        if urlsplit(self.path).path!='/api/submissions': return self.respond(404,{'error':'未找到'})
        if not self.host_valid() or self.headers.get('Origin')!=self.server.origin or not self.csrf_valid():
            return self.respond(403,{'error':'页面已过期，请刷新后重新提交'})
        if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
            return self.respond(415,{'error':'需使用JSON提交'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=MAX_BODY: return self.respond(413,{'error':'请求超过大小限制'})
            raw=self.rfile.read(length)
            if len(raw)!=length: raise ValueError('请求内容不完整')
            model_id,kind,payload,image=validate(json.loads(raw),self.server.store)
            filename=None
            if image:
                if sum(p.stat().st_size for p in self.server.store.images.glob('*.jpg'))>2*1024**3:
                    return self.respond(503,{'error':'图片投稿暂满，请稍后再试'})
                filename=uuid.uuid4().hex+'.jpg'
                (self.server.store.images/filename).write_bytes(image)
            try: key=self.server.store.submit(model_id,kind,payload,filename,self.ip_key())
            except Exception:
                if filename: (self.server.store.images/filename).unlink(missing_ok=True)
                raise
            return self.respond(202,{'id':key,'status':'pending','message':'已收到，人工审核后展示。'})
        except OverflowError as e: return self.respond(429,{'error':str(e)})
        except (ValueError,TypeError,UnicodeDecodeError) as e: return self.respond(400,{'error':str(e)})


def serve(directory,host='127.0.0.1',port=8092,origin=None,trust_proxy=False):
    with Server((host,port),directory,origin,trust_proxy) as server:
        print(f'Local: http://{host}:{server.server_address[1]}',flush=True)
        server.serve_forever()
