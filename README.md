# 望远镜数据库

个人自用的观鸟望远镜参数与实拍资料库。公开分享整理资料，支持补充参数、实际拍摄图片和使用体验，投稿经人工审核后展示。

网站：<https://wyj.cangming.fyi>

## 资料范围

初始目录有92条型号规格记录，其中61条有参考入手价格。价格为2026-10-19整理的历史参考值，包含不同成色，不代表实时售价或成交价。参数保留来源和待核标记，厂商声明不能代替独立实测。

公开数据在`data/catalog.json`，Excel在`downloads/telescopes.xlsx`。下载表只含型号参数与参考入手价格，不含个人推荐首页、交易平台商品链接、卖家和采集明细。

## 运行

需要Python 3.10或更新版本。

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m telescope serve --data-dir ./work --port 8092
```

Windows使用`.venv/Scripts/python`。打开`http://127.0.0.1:8092`。服务启动时导入公开目录，运行数据库与图片保存在`--data-dir`，不提交Git。修改参数前先查看[架构](docs/architecture.md)。

## 投稿和审核

上传者须拥有照片的展示授权。图片重新编码，移除EXIF元数据，单张原图不超过5MiB。投稿不立即公开，不需要填写邮箱、电话或账号。

```sh
python -m telescope review --data-dir ./work
python -m telescope review --data-dir ./work --show <投稿ID>
python -m telescope review --data-dir ./work --approve <投稿ID>
python -m telescope review --data-dir ./work --reject <投稿ID>
```

VPS上使用`sudo -u telescope-db /opt/telescope-db/venv/bin/python -m telescope`执行同样命令，并设置`PYTHONPATH=/opt/telescope-db/current`。管理接口不对公网开放。照片版权归作者，本站仅按上传者同意的展示授权使用。

## 检查和部署

```sh
python -m unittest discover -s tests -v
```

部署、数据备份和回退见[运行说明](deployment/README.md)。初始数据不依赖私有原件即可运行。原始资料整理脚本、账号状态和旧交付表不在公开范围内。

## 许可

原创程序和整理部分采用[GNU GPL v3或更新版本](LICENSE)。这是个人自用项目的公开分享，“个人自用”是用途说明，不构成额外使用限制。第三方参数来源和照片的原有权利归各自权利人，照片不随程序改授GPL。
