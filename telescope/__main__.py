import argparse
import json
import os
from .storage import Store


def main():
    parser=argparse.ArgumentParser(description='望远镜数据库：公开查询与本机审核')
    sub=parser.add_subparsers(dest='command',required=True)
    run=sub.add_parser('serve')
    run.add_argument('--data-dir',default=os.environ.get('DATA_DIR','work'))
    run.add_argument('--host',default='127.0.0.1')
    run.add_argument('--port',type=int,default=8092)
    run.add_argument('--origin',default=os.environ.get('PUBLIC_ORIGIN'))
    run.add_argument('--trust-proxy',action='store_true')
    review=sub.add_parser('review')
    review.add_argument('--data-dir',default=os.environ.get('DATA_DIR','work'))
    group=review.add_mutually_exclusive_group()
    group.add_argument('--show')
    group.add_argument('--approve')
    group.add_argument('--reject')
    args=parser.parse_args()
    if args.command=='serve':
        from .server import serve
        serve(args.data_dir,args.host,args.port,args.origin,args.trust_proxy)
    else:
        try:
            result=Store(args.data_dir).review(args.show or args.approve or args.reject,
                'approved' if args.approve else 'rejected' if args.reject else None)
            print(json.dumps(result,ensure_ascii=False,indent=2))
        except ValueError as e: parser.exit(1,str(e)+'\n')


if __name__=='__main__': main()
