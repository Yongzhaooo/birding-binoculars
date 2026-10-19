"""Create the public catalog from private parameter/price exports; never copy raw offers."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

FIELDS = [
 ('F','magnification','倍率','基本规格'),('G','objective_mm','物镜口径(mm)','基本规格'),
 ('H','field_deg','真实视场(°)','光学参数'),('AM','field_m','千米视场(m)','光学参数'),
 ('I','close_focus_m','最近对焦(m)','光学参数'),('J','eyepiece_mm','目镜直径(mm)','光学参数'),
 ('K','eye_relief_mm','出瞳距(mm，标称或原图)','光学参数'),('L','usable_relief_mm','实测可用出瞳距(mm)','光学参数'),
 ('M','exit_pupil_mm','出瞳直径(mm，计算)','光学参数'),('N','eyecup','眼罩','结构与材料'),
 ('O','prism_design','棱镜结构','结构与材料'),('P','prism_material','棱镜材质','结构与材料'),
 ('Q','ed','ED/低色散配置','结构与材料'),('R','flat_field','平场','结构与材料'),
 ('S','phase_coating','相位膜','镀膜与透过率'),('T','reflective_coating','反射膜','镀膜与透过率'),
 ('U','coatings','透镜/棱镜镀膜原文','镀膜与透过率'),('V','transmission','透过率声明/口径','镀膜与透过率'),
 ('W','weight_g','净重/无配件(g)','携行与防护'),('X','dimensions','尺寸(mm)','携行与防护'),
 ('Y','weatherproof','防水/防雾','携行与防护'),
]


def public_url(value):
    if not isinstance(value, str):
        return None
    u = urlsplit(value)
    return value if u.scheme in ('https','http') and u.hostname and not u.username else None


def main():
    p=argparse.ArgumentParser()
    p.add_argument('parameters',type=Path)
    p.add_argument('prices',type=Path)
    p.add_argument('--output',type=Path,default=Path('data/catalog.json'))
    args=p.parse_args()
    raw=json.loads(args.parameters.read_text(encoding='utf-8'))
    prices={x['id']:x for x in json.loads(args.prices.read_text(encoding='utf-8'))}
    columns={x['source']:i for i,x in enumerate(raw['fields'])}
    models=[]
    for row in raw['rows']:
        value=lambda c:row['values'][columns[c]]
        record=prices[row['id']]
        brand=record['brand'].replace('Shuntu','').replace('BOSMA','').strip()
        if '萨伽' in brand: brand='萨伽'
        if '裕众' in brand or '天虎' in brand: brand='天虎/裕众'
        states={key:'accepted' if row['fills'][columns[col]]=='#E4F3E8' else 'unverified' if row['fills'][columns[col]]=='#FFF0D6' else 'retained' for col,key,_,_ in FIELDS}
        models.append({'id':row['id'],'brand':brand,'name':record['old_name'].replace('Shuntu ','').replace('BOSMA ',''),
          'spec':value('E'),'version':value('D'),'reference_price':record['price'],'price_asof':'2026-10-19' if record['price'] else None,
          'parameters':{key:value(col) for col,key,_,_ in FIELDS},'verification':states,
          'verification_note':value('AF'),'experience_note':value('AG'),
          'sources':list(dict.fromkeys(u for c in ('AI','AJ') if (u:=public_url(value(c)))))})
    catalog={'schema_version':1,'updated':'2026-10-19','purpose':'个人自用，公开分享','price_label':'参考入手价格',
      'price_note':'历史整理参考值，含不同成色，不代表实时售价或成交价。',
      'fields':[{'key':key,'label':label,'group':group,'numeric':key in {'magnification','objective_mm','field_deg','field_m','close_focus_m','eyepiece_mm','eye_relief_mm','usable_relief_mm','exit_pupil_mm','weight_g'}} for _,key,label,group in FIELDS],
      'models':models}
    text=json.dumps(catalog,ensure_ascii=False,indent=2)
    for banned in ('goofish.com','闲鱼','咸鱼','seller','item_id','会话附件','C:\\Users','E:\\Projects'):
        assert banned not in text,banned
    assert len(models)==len({x['id'] for x in models})==92
    assert sum(x['reference_price'] is not None for x in models)==61
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(text,encoding='utf-8')
    print('Public catalog: 92 models, 61 reference prices, no raw offers')


if __name__=='__main__': main()
