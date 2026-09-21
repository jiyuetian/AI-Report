"""1.2 多 key 重试 fail-fast 行为模拟（不依赖项目重库，仅复刻控制流计时）。"""
import asyncio, time

async def simulate(max_retries, backoff_cap, n_providers_dead_before_ok=1):
    """模拟：前 n 个 provider 全挂，第 n+1 个成功。返回总耗时与总尝试次数。"""
    attempts = 0
    start = time.monotonic()
    # provider 循环（外层逐 provider）
    for prov in range(3):
        key_exhausted = False
        # 内层单 key 重试（MAX_RETRIES 次）
        for retry in range(max_retries + 1):
            attempts += 1
            # 模拟一次调用耗时（网络握手 ~0.05s）
            await asyncio.sleep(0.05)
            # 该 provider 是否挂：前 n_providers_dead_before_ok 个全挂
            if prov < n_providers_dead_before_ok:
                # 失败 → 是否重试
                if retry < max_retries:
                    await asyncio.sleep(min(2 ** retry, backoff_cap))
                    continue
                key_exhausted = True
                break
            else:
                # 成功
                return time.monotonic() - start, attempts
        if key_exhausted:
            continue
    return time.monotonic() - start, attempts

async def main():
    print("=== 旧配置 MAX_RETRIES=2, 退避 2**retry(1s/2s) ===")
    for n in (1, 2):
        dt, att = await simulate(2, 99, n_providers_dead_before_ok=n)
        print(f"  前 {n} 个 key 失效才成功: 耗时={dt:.2f}s 总尝试={att}次")

    print("=== 新配置 MAX_RETRIES=1, 退避封顶 0.5s ===")
    for n in (1, 2):
        dt, att = await simulate(1, 0.5, n_providers_dead_before_ok=n)
        print(f"  前 {n} 个 key 失效才成功: 耗时={dt:.2f}s 总尝试={att}次")

asyncio.run(main())
