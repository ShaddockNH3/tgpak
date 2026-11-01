# tgpak

> **Warning**
>
> 这个仓库绝大部分代码和文档是 AI 写的。接口全是逆着 Telegram Web K 的前端扒出来的，
> 对方改一版前端就可能全废。出问题先看 [`docs/pitfalls.md`](docs/pitfalls.md)，
> 那里面记的是踩过的坑。仓库里没有任何真实账号、频道名、分享链接。

把 Telegram 频道里某个作者的图包，按相册原始顺序抓下来，存成 `001.jpg`、`002.jpg`……
另外两条路径：从 PikPak 拿更清晰的原档，以及传到网盘（OpenList）。

## 为什么是 Web K

结论先说：**只有 Web K 能拿到「某一期的完整有序清单」**。

Web A（`web.telegram.org/a`）有个 `/a/download/photo<id>` 接口，画质没问题，但它要求客户端
「认识」这张图 —— 没在界面上渲染过的图，请求会一直挂着，最后 500。而且 `<id>` 是 Telegram 给每个
文件发的随机 64 位编号，跟相册顺序毫无关系，只能从浏览器缓存里捞，捞出来是一锅粥：混着相邻消息、
混着隔壁期的图。按这条路做，数量对不上、顺序也是乱的。

Web K 把内部 manager 挂在了 window 上：

```js
rootScope.managers.apiManager.invokeApi('messages.getReplies', {peer, msg_id})
```

一次调用就把评论区（也就是相册本体）的全部消息按 id 顺序拿回来，每张图带着自己的
`photo.id`、尺寸列表、`file_reference`。顺序、数量、文件 id 全齐。

细节和调用姿势见 [`docs/k-api.md`](docs/k-api.md)。

## 装

```bash
uv sync
uv run playwright install chrome
cp config.example.json config.json      # 填频道、tag、P 盘账号、网盘地址
```

`config.json` 里的 `telegram.profile` 是浏览器登录态目录，第一次要跑 `tgpak login` 扫码。

## 三条路径

### 一、取图

```bash
uv run tgpak login                    # 打开 K，登录完回车
uv run tgpak tg scan                  # 频道里搜 tag，认「第N期」，登记成 out/periods.json
uv run tgpak tg fetch --period 3      # 拉该期清单 → out/media_p03.json
uv run tgpak tg get --periods 2-17    # 按清单顺序下载 → staging/p02 … p17
```

`scan` 认不出期数的帖子会单独列出来（合集、别的作者），自己看着办。

命名：普通图片视频 `001.jpg` / `002.mp4`，带原始文件名的压缩包 `01-套图名.zip`。
重跑会跳过已存在的文件，断了接着跑就行。

### 二、P 盘原档

PikPak 免费号只有 6GB 空间，所以是「分批转存 → 立刻下载 → 立刻删云端」，一批控制在 3.4GB /
90 个文件以内。批次太大转存会落不全。

```bash
uv run tgpak pikpak link --period 18 --url https://mypikpak.com/s/xxxx
uv run tgpak pikpak get --period 18
```

进度存在 `out/dl_progress.json`，中断再跑会接着下。免费号有频率限制，跑太快会回
`Aborted - Your operation is too frequent`，等一会儿再来。

### 三、传网盘

走 OpenList 的 HTTP API。传一个验一个，整期尺寸都对上才删本地。

```bash
uv run tgpak push --period 3                 # 传到 config.upload.base/p03
uv run tgpak push --period 3 --keep          # 传完不删本地
uv run tgpak push --period 3 --to /other/dir # 临时换个远端目录
```

云端已有且尺寸一致的文件会跳过，可以反复跑。

## 校验

```bash
uv run tgpak verify --periods 1-25           # 看本地
uv run tgpak verify --periods 1-25 --remote  # 看云端
```

取图路径按 `media_pNN.json` 的文件名集合逐个对，多一个少一个都报出来。
P 盘路径会重新读一遍分享，比文件数和总字节。

## 已知限制

- 频道必须在你的对话列表里，`getDialogs` 才找得到。
- 只认评论区里的相册。频道帖子本体不带评论区的话，抓不到东西。
- 几 GB 的压缩包下载时整个 Blob 先进浏览器内存，内存小的机器注意。
- 删本地是 10 个一批。一次删几百个在某些沙箱环境会被拦，见 pitfalls。
- 没做并发。慢，但不容易把号跑死。

## 目录

```
src/tgpak/
  kapi.py       驱动 Web K：invokeApi 封装 + 下载
  sink.py       本机 HTTP 接收器，Blob 直接落盘（不走 base64）
  grab.py       取图：scan / fetch / get
  pikpak.py     P 盘：分享翻页、分批转存、下载
  push.py       传网盘：OpenList
  verify.py     完整性校验
  cli.py        命令行
docs/
  k-api.md      Web K 内部 API 的调用姿势
  pikpak.md     P 盘那套的限制
  pitfalls.md   一路踩过的坑
```

MIT
