import asyncio
import datetime
import speedtest
from FileStream.utils.messages import LANG
from FileStream.utils.human_readable import humanbytes

def _run_speedtest():
    st = speedtest.Speedtest(secure=True)
    try:
        st.get_servers([])
    except Exception:
        pass

    try:
        st.get_best_server()
    except Exception:
        if getattr(st, "servers", None):
            for servers in st.servers.values():
                if servers:
                    st.best = servers[0]
                    break
        if not getattr(st, "best", None):
            raise

    st.download(threads=4)
    st.upload(pre_allocate=False, threads=4)

    try:
        share_url = st.results.share()
    except Exception:
        share_url = None

    results = st.results.dict()
    if share_url:
        results["share"] = share_url
    return results


async def run_speedtest(retries: int = 2, delay: int = 3):
    loop = asyncio.get_running_loop()
    last_error = None
    for _ in range(retries + 1):
        try:
            return await loop.run_in_executor(None, _run_speedtest)
        except Exception as e:
            last_error = e
            await asyncio.sleep(delay)
            continue
    raise last_error


def format_speedtest(result: dict) -> str:
    download_bps = result.get("download", 0) / 8
    upload_bps = result.get("upload", 0) / 8

    server = result.get("server", {}) or {}
    client = result.get("client", {}) or {}

    download_mbps = round(result.get("download", 0) / 1_000_000, 2)
    upload_mbps = round(result.get("upload", 0) / 1_000_000, 2)
    ping = round(result.get("ping", 0), 2)
    timestamp = result.get("timestamp") or datetime.datetime.utcnow().isoformat()
    bytes_sent = humanbytes(result.get("bytes_sent", 0))
    bytes_received = humanbytes(result.get("bytes_received", 0))

    return LANG.SPEEDTEST_RESULT.format(
        download_mbps=download_mbps,
        download_bps=humanbytes(download_bps),
        upload_mbps=upload_mbps,
        upload_bps=humanbytes(upload_bps),
        ping=ping,
        timestamp=timestamp,
        bytes_sent=bytes_sent,
        bytes_received=bytes_received,
        server_name=server.get("name", "N/A"),
        server_country=server.get("country", "N/A"),
        server_sponsor=server.get("sponsor", "N/A"),
        server_latency=server.get("latency", "N/A"),
        server_lat=server.get("lat", "N/A"),
        server_lon=server.get("lon", "N/A"),
        client_ip=client.get("ip", "N/A"),
        client_lat=client.get("lat", "N/A"),
        client_lon=client.get("lon", "N/A"),
        client_isp=client.get("isp", "N/A"),
        client_isprating=client.get("isprating", "N/A"),
        client_country=client.get("country", "N/A"),
    )
