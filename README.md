# tgpak

把一个作者在 Telegram 频道里的图包，按相册原本的顺序存成 `001.jpg`、`002.jpg`……

另有两条路：从 PikPak 取更清晰的原档，以及把结果传到网盘（OpenList）。

图包一般发在帖子评论区，一期几十到上百个文件。手动存会遇到顺序乱、数量对不上、
大文件下到一半断掉这几件事，所以这里先认期、再拉清单、按清单落盘，收完可以核对。

## 安装

```bash
uv sync
uv run playwright install chrome
cp config.example.json config.json      # 频道、tag、P 盘账号、网盘地址
```

`telegram.profile` 是浏览器登录态目录，头一次跑 `uv run tgpak login` 扫码。

一个作者一个工作目录，各放一份 config：

```
染三ran3/config.json      tag #染三ran3, base /…/染三ran3
桜桃喵/config.json        tag #桜桃喵,   base /…/桜桃喵
```

跑的时候指过去就行：`tgpak -c 桜桃喵/config.json tg scan`。登录态可以共用同一个 profile 目录，
只要别同时开两个。

## 取图

```bash
uv run tgpak login
uv run tgpak tg scan                  # 搜 tag，认「第N期」，写进 out/periods.json
uv run tgpak tg fetch --period 3      # 拉清单 → out/media_p03.json
uv run tgpak tg get --periods 2-17    # 按清单顺序下到 staging/p02 … p17
```

`scan` 顺手把帖子里的 PikPak 链接存进 `out/links.json`。有些链接藏在一个 emoji 后面
（`messageEntityTextUrl`），正文里看不见，得读实体才拿得到。

认不出期数的帖子会单独列出来，合集之类自己 `tg add --period 1 --post 1167` 登记。

命名：图片视频 `001.jpg` / `002.mp4`，带原名的压缩包 `01-套图名.zip`。
重跑跳过已存在的，断了接着跑。

## P 盘原档

Telegram 里的图是压过的，想要原始尺寸得去 P 盘取分享里的原档。

免费号只有 6GB 空间，一期原档动辄几个 GB，所以分批：转存一批 → 下 → 删云端 → 下一批。
一批卡在 3.4GB / 90 个文件以内，超了转存会落不全。

```bash
uv run tgpak pikpak link --period 18 --url https://mypikpak.com/s/xxxx
uv run tgpak pikpak get --period 18
```

进度在 `out/dl_progress.json`，重跑接着下。免费号有频率限制，跑快了整个账号会被限，
回 `Aborted - Your operation is too frequent`。

## 传网盘

走 OpenList 的 HTTP API，rclone crypt 由它自己处理。传一个验一个，整期尺寸都对上才删本地。

```bash
uv run tgpak push --period 3
uv run tgpak push --period 3 --keep          # 传完留着本地
uv run tgpak push --period 3 --to /other/dir
uv run tgpak push --period 3 --force         # 云端已有也重传（覆盖用）
```

云端已有且尺寸一致的跳过，可以反复跑。

## 校验

```bash
uv run tgpak verify --periods 1-25
uv run tgpak verify --periods 1-25 --remote
```

取图那几期按 `media_pNN.json` 的文件名集合逐个对，多一个少一个都报。
P 盘那几期重新读一遍分享，比文件数和总字节。真值读不到会明说读不到，不会假装通过。

## 有限制的地方

- 频道得在你的对话列表里，`getDialogs` 才找得到。
- 只认评论区的相册。帖子本体不带评论区就没东西。
- 几个 GB 的压缩包，整个 Blob 先过一遍浏览器内存。
- 删本地默认 10 个一批，某些沙箱一次删几百个会被拦。
- 免费 P 盘号有频率限制，跑快了要等；换 IP 有时能绕过。
- 没做并发。慢，但不容易把号跑死。

## 目录

```
src/tgpak/
  kapi.py      Web K 驱动：invokeApi 封装 + 下载
  sink.py      本机 HTTP 接收器，Blob 直落盘，不走 base64
  grab.py      取图：scan / fetch / get
  pikpak.py    P 盘：分享翻页、分批转存、轮询落盘、下载
  push.py      传网盘：OpenList
  verify.py    校验
  cli.py       命令行
```

## 思路构建

这个仓库里最费时间的不是写代码，是把几条走不通的路走完，确认哪条能走。

- [Web K 内部 API](docs/k-api.md)：拿 peer、找帖子、取评论区、下载的调用姿势，以及四个必踩的坑
- [P 盘](docs/pikpak.md)：6GB 空间怎么分批、file_list 静默截断、落盘延迟、频率限制的成因
- [弯路记录](docs/pitfalls.md)：为什么最后没用 Web A、base64 中转、token 失效、批量删除被拦

MIT
