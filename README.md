# tgpak

> [!WARNING]
> 这个仓库大半是 AI 写的。接口是逆着 Telegram Web K 的前端扒出来的，前端一改就可能全废。
> 有纰漏很正常，别当成正经软件用。仓库里没有任何真实账号、频道名、分享链接。

把一个作者在 Telegram 频道里的图包，按相册原本的顺序收下来，存成 `001.jpg`、`002.jpg`……

此外还有两条路：从 PikPak 拿更清晰的原档，以及把结果传到网盘（OpenList）。

## 它要解决什么

频道里的图包大多发在帖子评论区。一期几十到上百个文件，前后掺着别的内容，
偶尔混进一张目录图或一个压缩包。

手动保存会遇到三个麻烦：

- 顺序是乱的，Telegram 给每个文件发随机 id，和相册里的位置无关
- 数量对不上，中间漏一张很难发现
- 视频和压缩包体积大，浏览器下载容易半路断掉

tgpak 把每一期当作一个整体处理：先认出是哪一期，再拉一份清单，最后严格按清单落盘。
清单是唯一依据，收完可以校验，少一个都会报出来。

## 为什么非得是 Web K

只有 Web K 拿得到「某一期的完整有序清单」。

Web A 有 `/a/download/photo<id>`，画质没问题，但要求客户端认识这张图 —— 没在界面上渲染过的，
请求会一直挂着然后 500。更要命的是 `<id>` 是 Telegram 给每个文件发的随机 64 位编号，跟顺序无关，
只能从浏览器缓存里捞，捞出来混着相邻消息和隔壁期的图。按这条路做，数量对不上，顺序也排不出来。

Web K 把内部 manager 挂在 window 上了：

```js
rootScope.managers.apiManager.invokeApi('messages.getReplies', {peer, msg_id})
```

一次拿回评论区（也就是相册本体）的全部消息，按 id 排好序，每张图带着 `photo.id`、尺寸列表、
`file_reference`。顺序、数量、文件 id 一次齐活。

调用姿势和踩过的坑在 `docs/` 里。

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

Telegram 里的图通常是压缩过的，想要原始尺寸得去 P 盘取分享里的原档。

免费号只有 6GB 空间，一期原档动辄几个 GB，所以只能分批：转存一批 → 下 → 删云端 → 下一批。
一批卡在 3.4GB / 90 个文件以内，超了转存会落不全，日志里能看到一串「还没落盘」。

```bash
uv run tgpak pikpak link --period 18 --url https://mypikpak.com/s/xxxx
uv run tgpak pikpak get --period 18
```

进度在 `out/dl_progress.json`，重跑接着下。转存之后要等它落盘，落盘速度不稳定，
所以要轮询而不是等固定几秒就去看。

免费号还有频率限制。转存、取直链、删除这些写操作打得太密，整个 API 会被限，
回 `Aborted - Your operation is too frequent, please try again later`，只能停手等。
一晚把三个号全跑限过，教训是：一期一停比连着刷快得多。

空间不足是另一个错误（`Insufficient cloud storage`）。下载失败的文件会留在云端吃配额，
攒多了就写不进新的，需要定期清 `Pack From Shared`。

## 传网盘

走 OpenList 的 HTTP API，rclone crypt 由它自己处理。传一个验一个，整期尺寸都对上才删本地。

```bash
uv run tgpak push --period 3
uv run tgpak push --period 3 --keep          # 传完留着本地
uv run tgpak push --period 3 --to /other/dir
uv run tgpak push --period 3 --force         # 云端已有也重传（覆盖用）
```

云端已有且尺寸一致的跳过，可以反复跑。token 会过期，返回 401 时要重新登录再传，
不然会一路空跑，看起来在动其实一个都没上去。

## 校验

```bash
uv run tgpak verify --periods 1-25
uv run tgpak verify --periods 1-25 --remote
```

取图那几期按 `media_pNN.json` 的文件名集合逐个对，多一个少一个都报。
P 盘那几期重新读一遍分享，比文件数和总字节。真值读不到会明说读不到，不会假装通过。

## 已知限制

- 频道得在你的对话列表里，`getDialogs` 才找得到。
- 只认评论区的相册。帖子本体不带评论区就没东西。
- 几个 GB 的压缩包，整个 Blob 先过一遍浏览器内存。
- 删本地默认 10 个一批，某些沙箱一次删几百个会被拦。
- 免费 P 盘号有频率限制，跑快了要等；这是账号层面的，换 IP 有时能绕过。
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
docs/
  k-api.md     Web K 内部 API 怎么用
  pikpak.md    P 盘的限制
  pitfalls.md  踩过的坑
```

## License

MIT
