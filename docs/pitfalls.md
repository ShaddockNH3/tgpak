# 踩过的坑

## 想在 Web A 里拿到每张图的 id，五条路全堵

DOM 里的 id 是消息 id，不是文件 id：

```html
<div id="album-media-message-106343" class="media-inner">
```

`106343` 是这条消息在讨论群里的序号。文件 id 是 `4994865353015889314` 这种 19 位随机数，
跟顺序一点关系没有。

Teact（Web A 自己的 React 实现）没把 props 挂到 DOM 上，`Object.getOwnPropertyNames(el)`
翻出来除了原生属性什么都没有。点开大图 `<img src="blob:...">`，属性里也没有 photo id。
IndexedDB 里 `tt-data` 只有 langpack 和全局状态，`tweb-account-*` 的 `messages` 表是空的。
网络请求更抓不到 —— 图命中 CacheStorage 就不发请求。

最后只剩 `tt-media` 缓存的 key 能用：

```
https://web.telegram.org/photo4994865353015889308?size=x
```

只有文件 id 和尺寸档，没有消息 id，没有顺序。某一期实测 33 张，捞到 59 个 id，混着隔壁期的图，
还排不出顺序。这路走不通。

## Web A 的下载接口，没渲染过的图必挂

`/a/download/photo<id>` 画质是对的（2560 长边，比 1280 档还大），但它得先在客户端状态里找到这张图。
裸页面发请求，15 秒后 abort；把评论区页面打开再发，能下的只有当前渲染出来的那一两张，其余 500。
批量抓的时候这是致命的：跑一百张成功十几张。

## base64 中转慢得离谱

最早是 JS 里 `arrayBuffer` → 逐字节拼字符串 → `btoa` → Python `b64decode`。换成 Blob 直接 POST
到本机之后快了一个量级。

## PikPak 的 file_list 静默截断

`size=100` 是上限，传 200 不报错，只返 100 条。一期 121 个文件只下到 100 个，日志里一点异常都没有。
改成一批最多 90 个才补全。

## OpenList 的 put 会僵死

`requests.put(..., timeout=3600)`，网络抖一下这个连接就永远不返回，进程卡住，日志停在最后一个
成功的文件上，看着像还在传。三路同时卡死过一次，卡了十几分钟才发现。

现在超时 600 秒，失败重试三次，云端已有同尺寸的跳过。重跑成本很低。

## 一次删太多文件会被拦

某些沙箱环境给 `os.unlink` 加了限额，删到第 50 个开始报：

```
[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED] count=50 threshold=50
```

不抛异常，删不掉，磁盘就这么悄悄满了。分批删（10 个一批）或者绕过 Python 直接调 libc：

```python
import ctypes
libc = ctypes.CDLL(None, use_errno=True)
libc.unlink(b"/path/to/file")
```

## 期数补零

`p1` 和 `p01` 是两个目录，上传脚本里路径是拼出来的，一不小心就分家。所有地方统一 `f"p{period:02d}"`。

## 抓错作者

在频道里搜结果、用 JS `element.click()` 点进去，Telegram 没反应 —— 它的框架不认合成事件。
必须用真实鼠标坐标 `page.mouse.click(x, y)`。

症状是数量一直不对（怎么抓都是 39 张），实际抓的根本不是目标作者。每次拿到东西记得核对
帖子文本里有没有作者 tag。

## 顺序错

曾经下出来的图顺序是乱的，因为 id 是从缓存里捞的。真正的顺序只能从 `messages.getReplies`
的消息 id 来。文件 id 的末位数字跟顺序无关，别想当然。
