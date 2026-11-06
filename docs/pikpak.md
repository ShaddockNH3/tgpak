# P 盘

用的是 [pikpakapi](https://github.com/Quan666/PikPakAPI)。有几件事它没处理，或者处理得不够，都在 `src/tgpak/pikpak.py` 里自己补的。

## 空间只有 6GB

免费号 6GB，一期原档动辄几 GB，只能分批走：转存一批 → 下载 → 删云端 → 下一批。

```python
await cli.restore(sid, token, [f['id'] for f in batch])
# 等落盘，别急着查，落盘时间不稳定
pack = await find_pack_folder(cli)           # 转存落到 "Pack From Shared"
landed = await cli.file_list(parent_id=pack, size=100)
# 下完立刻
await cli.delete_forever([src['id']])
```

单批上限卡在 3.4GB / 90 个文件，两个都会踩到。

## file_list 最多 100 条，还静默截断

`file_list(parent_id=..., size=200)` 不报错，就是只给你 100 条。一批超过 100 个文件，后面那几个永远下不到，日志里也没有异常。所以一批卡在 90 个以内，翻页要自己处理 `page_token`。

## 转存不一定马上落盘

`restore` 之后 `file_list` 里可能还有一部分没出现。这不算失败，留到下一轮。

原先转存完固定等 8 秒就去看，经常一次只能落几个。现在改成轮询：每隔十几秒查一次，最多等五分钟，落一个下一个，剩下没落的留给下一轮。日志里「还没落盘」会少很多。

## 频率限制

跑太快的返回：

```text
Aborted - Your operation is too frequent, please try again later
```

这时候重试没用，整个账号都被限了，连 `login` 都会挂。

起因是写操作打得太密。一次完整下载一个文件要三次写操作：转存、取直链、删除。一期一百个文件就是三百次，加上每次跑 CLI 都要重新 login，几期连下来就触发了。

实际经验是一期一停，中间隔十几分钟，比连着刷快得多。还有一个反直觉的地方：被限之后继续定时重试，会把冷却窗口一直往后推，越跑越锁死。停手才是最快的解法。

## 空间不足

```text
Insufficient cloud storage, continued use requires Premium
```

这是另一个错误，跟频率限制无关。转存了但没下载成功的文件会留在 `Pack From Shared` 里占配额，攒多了就写不进新的。需要定期清空那个目录。

## 断点

进度记在 `out/dl_progress.json`，key 是 `期数/文件名`，重跑跳过已完成的。

文件名用分享里的原名（`1 (23).jpg` 这种）。自己改了名就对不上进度，会重下。

## 下载直链

`get_download_url` 返回的是有时效的直链，拿到立刻下，不要存下来过一会儿再用。
