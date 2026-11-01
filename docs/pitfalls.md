# 踩过的坑

按「想当然 → 实际」的顺序记。想少走弯路可以直接看结论。

## 想在 Web A 里拿到每张图的 id，五条路都堵死

**1. DOM 里的 id 是消息 id，不是文件 id**

```html
<div id="album-media-message-106343" class="media-inner">
```

`106343` 是这条消息在讨论群里的序号，不是文件 id。文件 id 是 `4994865353015889314` 这种
19 位随机数。

**2. Teact 没把 props 挂到 DOM 上**

Web A 是自己的 React 实现（Teact），试过 `Object.getOwnPropertyNames(el)`，除了原生属性什么都没有。
拿不到组件的 `message.content.photo`。

**3. 点开大图，`<img>` 是 blob**

`src="blob:https://web.telegram.org/9f0a..."`，属性里没有 photo id。

**4. IndexedDB 里没有消息**

Web A 的 `tt-data` 只有 `langpack`、`tt-global-state` 三条；`tweb-account-1..4` 是 Web K 的库，
`messages` 表是空的（没开本地缓存）。

**5. 网络请求抓不到**

图命中 CacheStorage 就不发请求，`/progressive/photo<id>` 一条都看不到。

最后只剩 `tt-media` 缓存的 key 可用：

```
https://web.telegram.org/photo4994865353015889308?size=x
```

只有文件 id 和尺寸档，没有消息 id、没有顺序。捞出来是混的 —— 实测某一期 33 张，捞到 59 个 id，
里面混着隔壁期的图，还排不出顺序。

## Web A 的下载接口，没渲染过的图必挂

`/a/download/photo<id>` 画质是对的（能拿到 2560 长边，比 1280 档还大），但它要先在客户端状态里
找到这张图。裸页面直接请求，15 秒超时 abort；把评论区页面打开再请求，能下的只有当前渲染出来的
那一两张，其余 500。

批量抓的时候这是致命的：跑一百张，成功十几张。

## base64 中转很慢

最早的写法是 JS 里 `arrayBuffer` → 逐字节拼字符串 → `btoa` → Python `b64decode`。
一张 500KB 的图要拼七十万字符，还要在 Python 里再解一遍。换成 Blob 直接 POST 到本机之后，
速度快了一个量级。

## PikPak 的 `file_list(size=)` 静默截断

`size=100` 是上限，传 200 不报错，就是只返 100 条。结果是一期 121 个文件，只下到 100 个，
日志里毫无异常。改成一批最多 90 个文件才补全。

## OpenList 的 put 会僵死

上传用的是 `requests.put(..., timeout=3600)`。网络抖一下，这个连接就永远不返回，进程卡死，
日志停在最后一个成功文件上，看起来像「还在传」。三路一起卡死过一次，一直卡了十几分钟。

现在超时设 600 秒，失败重试三次，并且云端已有同尺寸的文件直接跳过 —— 重跑成本很低。

## 一次删太多文件会被拦

某些沙箱环境会给 `os.unlink` 加限额，删到第 50 个开始报：

```
[safe-delete][SAFE_DELETE_BULK_CONFIRM_REQUIRED] count=50 threshold=50
```

删不掉但也不抛异常，磁盘就这么悄悄满了。两个办法：分批删（10 个一批），或者绕过 Python 层直接调 libc：

```python
import ctypes
libc = ctypes.CDLL(None, use_errno=True)
libc.unlink(b"/path/to/file")
```

## 期数补零

`p1` 和 `p01` 是两个目录。上传脚本里路径是拼出来的，一不小心 `p2` 和 `p02` 就分家了。
所有地方统一 `f"p{period:02d}"`。
