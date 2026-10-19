# VPS部署与审核

运行方式与个人留学案例库一致：Python、SQLite、systemd、Caddy。源码与运行数据分开。

## 目录

- `/opt/telescope-db/releases/<commit>/`：已提交版本的代码、公开目录、下载文件。
- `/opt/telescope-db/current`：当前版本符号链接。
- `/opt/telescope-db/venv/`：Python环境，安装根目录`requirements.txt`。
- `/var/lib/telescope-db/`：私有SQLite数据库、重新编码的投稿图片和请求签名密钥。由`telescope-db`用户持有，不进入Git。

初次部署安装Python 3.10+和venv，创建无登录服务用户。将发布包解压到新版本目录，代码归root只读，运行目录归服务用户且权限0700。安装`telescope-db.service`，启用服务。Caddy主配置只增加本项目片段的import，经`caddy validate`通过后reload。DNS的`wyj`记录须指向VPS，再检查HTTPS。

## 审核

在VPS执行，列出待审、读取完整投稿，再决定批准或拒绝。

```sh
cd /opt/telescope-db/current
sudo -u telescope-db env PYTHONPATH=/opt/telescope-db/current /opt/telescope-db/venv/bin/python -m telescope review --data-dir /var/lib/telescope-db
sudo -u telescope-db env PYTHONPATH=/opt/telescope-db/current /opt/telescope-db/venv/bin/python -m telescope review --data-dir /var/lib/telescope-db --show <投稿ID>
sudo -u telescope-db env PYTHONPATH=/opt/telescope-db/current /opt/telescope-db/venv/bin/python -m telescope review --data-dir /var/lib/telescope-db --approve <投稿ID>
```

`--show`含完整说明、来源、设备、拍摄条件和待审图片的服务器路径。需要查看图片时，通过已授权SSH身份读取该精确路径到本机后预览。不能为方便预览而把待审图片目录交给Caddy公开。`--reject`拒绝；重复审核返回失败。

参数批准后写入独立覆盖表，附带投稿来源。初始目录再次导入不覆盖这些用户补充。照片版权归作者，只按其展示授权使用。

## 备份和回退

首次部署不复制其他项目数据库。后续升级先停止本服务，使用SQLite backup API将当前数据库备份到私有备份位置，并把图片和请求密钥一并保存。确认备份可打开、图片数一致，再切换`current`并启动。只替换代码，不用旧数据库覆盖升级后接收的投稿。

故障时切回与数据库版本兼容的旧代码并重启。未知数据库版本会被拒绝，不强制降级。恢复数据前先保全故障后的当前数据库及图片，核对新增投稿，不能直接用备份覆盖。

公开接口健康检查为`/api/health`，目录为`/api/catalog`。核对匿名目录可读，投稿需要同源令牌，待审图片不可读。生产上不提交合成投稿；完整投稿测试在隔离测试目录中进行。
