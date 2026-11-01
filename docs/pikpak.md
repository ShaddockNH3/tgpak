# P 盘的限制

用的是 [pikpakapi](https://github.com/Quan666/PikPakAPI)，有几件事它没处理好，自己补。

## 空间只有 6GB

免费号 6GB，一期原档动辄几 GB。分批走：转存一批 → 下载 → 删云端 → 下一批。

```python
await cli.restore(sid, token, [f['id'] for f in batch])
await asyncio.sleep(8)                       # 等落盘，别急着查
pack = await find_pack_folder(cli)           # 转存落到 "Pack From Shared"
landed = await cli.file_list(parent_id=pack, size=100)
# 下完立刻
await cli.delete_forever([src['id']])
```

## file_list 最多 100，还静默截断

`file_list(parent_id=..., size=200)` 不报错，就是只给你 100 条。一批最多 90 个文件，
多了后面那几个永远下不到而且不报错。翻页要自己处理 `page_token`。

## 转存不一定马上落盘

`restore` 之后 `file_list` 里可能还有一部分没出现。不算失败，留到下一轮重试。
表现是日志里一堆「还没落盘」。

## 频率限制

跑太快会返回：

```
Aborted - Your operation is too frequent, please try again later
```

这时候重试没用，整个 API 都被限了，连 login 都会挂。只能停一会儿再来，
批量跑的时候一期之间隔一下。

## 断点

进度记在 `out/dl_progress.json`，key 是 `期数/文件名`，重跑跳过已完成的。
文件名用分享里的原名（`1 (23).jpg` 这种），自己改了就对不上进度。

## 下载链接

`get_download_url` 返回的是有时效的直链，拿到立刻下，别存。
